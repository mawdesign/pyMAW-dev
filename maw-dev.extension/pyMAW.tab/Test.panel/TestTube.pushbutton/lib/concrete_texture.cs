
using System;
using System.Drawing;
using System.Drawing.Imaging;

class Program
{
    // -------------------- Math helpers --------------------
    static float SmootherStep(float t) => t * t * t * (t * (t * 6 - 15) + 10);
    static float Lerp(float a, float b, float t) => a + t * (b - a);
    static int Mod(int a, int m) { int r = a % m; return r < 0 ? r + m : r; }
    static float Clamp01(float v) => v < 0 ? 0 : (v > 1 ? 1 : v);

    // -------------------- Periodic (tileable) value noise --------------------
    static float[,] PeriodicValueNoise(int w, int h, int cellsX, int cellsY, int seed)
    {
        var rng = new Random(seed);
        float[,] g = new float[cellsY, cellsX];
        for (int y = 0; y < cellsY; y++)
            for (int x = 0; x < cellsX; x++)
                g[y, x] = (float)rng.NextDouble();

        float[,] outImg = new float[h, w];
        for (int y = 0; y < h; y++)
        {
            float fy = (float)y / h * cellsY;
            int yi = (int)Math.Floor(fy);
            float ty = SmootherStep(fy - yi);
            int yi0 = Mod(yi, cellsY), yi1 = Mod(yi + 1, cellsY);

            for (int x = 0; x < w; x++)
            {
                float fx = (float)x / w * cellsX;
                int xi = (int)Math.Floor(fx);
                float tx = SmootherStep(fx - xi);
                int xi0 = Mod(xi, cellsX), xi1 = Mod(xi + 1, cellsX);

                float v00 = g[yi0, xi0], v10 = g[yi0, xi1];
                float v01 = g[yi1, xi0], v11 = g[yi1, xi1];

                float a = Lerp(v00, v10, tx);
                float b = Lerp(v01, v11, tx);
                outImg[y, x] = Lerp(a, b, ty);
            }
        }
        return outImg;
    }

    // -------------------- Tileable fBm --------------------
    static float[,] PeriodicFBM(int w, int h, int octaves, int baseCellsX, int baseCellsY, float lacunarity, float gain, int seed)
    {
        float[,] total = new float[h, w];
        float amp = 1f, norm = 0f;

        for (int i = 0; i < octaves; i++)
        {
            int cx = Math.Max(1, (int)(baseCellsX * Math.Pow(lacunarity, i)));
            int cy = Math.Max(1, (int)(baseCellsY * Math.Pow(lacunarity, i)));
            var n = PeriodicValueNoise(w, h, cx, cy, seed + i * 31);

            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++)
                    total[y, x] += amp * n[y, x];

            norm += amp;
            amp *= gain;
        }

        // normalize to [0,1]
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
                total[y, x] = total[y, x] / Math.Max(norm, 1e-6f);

        return total;
    }

    // -------------------- Box blur (tile-aware) --------------------
    static float[,] BoxBlur(float[,] img, int radius, int passes)
    {
        if (radius <= 0 || passes <= 0) return img;
        int h = img.GetLength(0), w = img.GetLength(1);
        float[,] tmp = (float[,])img.Clone();
        float[,] outImg = new float[h, w];

        for (int p = 0; p < passes; p++)
        {
            // Horizontal
            for (int y = 0; y < h; y++)
            {
                for (int x = 0; x < w; x++)
                {
                    float sum = 0f;
                    for (int k = -radius; k <= radius; k++)
                        sum += tmp[y, Mod(x + k, w)];
                    outImg[y, x] = sum / (2 * radius + 1);
                }
            }
            // Vertical
            for (int y = 0; y < h; y++)
            {
                for (int x = 0; x < w; x++)
                {
                    float sum = 0f;
                    for (int k = -radius; k <= radius; k++)
                        sum += outImg[Mod(y + k, h), x];
                    tmp[y, x] = sum / (2 * radius + 1);
                }
            }
        }
        return tmp;
    }

    // -------------------- High-pass (Difference of Gaussian) --------------------
    static float[,] HighPassDoG(float[,] img, int radiusSmall = 1, int radiusLarge = 4)
    {
        var blurSmall = BoxBlur(img, radiusSmall, passes: 1);
        var blurLarge = BoxBlur(img, radiusLarge, passes: 1);
        int h = img.GetLength(0), w = img.GetLength(1);
        float[,] outImg = new float[h, w];

        // DoG: small - large (emphasize mid/high)
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
                outImg[y, x] = blurSmall[y, x] - blurLarge[y, x];

        // Zero-center and normalize to [-1,1]
        ZeroCenter(outImg);
        NormalizeAbs(outImg);
        return outImg;
    }

    static void ZeroCenter(float[,] img)
    {
        int h = img.GetLength(0), w = img.GetLength(1);
        double sum = 0;
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
                sum += img[y, x];
        float mean = (float)(sum / (h * w));
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
                img[y, x] -= mean;
    }

    static void NormalizeAbs(float[,] img)
    {
        int h = img.GetLength(0), w = img.GetLength(1);
        float maxAbs = 1e-6f;
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
            {
                float a = Math.Abs(img[y, x]);
                if (a > maxAbs) maxAbs = a;
            }
        float inv = 1f / maxAbs;
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
                img[y, x] *= inv; // now roughly in [-1,1]
    }

    static void Normalize01(float[,] img)
    {
        int h = img.GetLength(0), w = img.GetLength(1);
        float min = float.MaxValue, max = float.MinValue;
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
            { float v = img[y, x]; if (v < min) min = v; if (v > max) max = v; }
        float range = Math.Max(max - min, 1e-6f);
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
                img[y, x] = (img[y, x] - min) / range;
    }

    // -------------------- Concrete micro-detail (tileable, band-limited) --------------------
    static float[,] GenerateConcreteDetailLayer(int w, int h, int seed,
                                                int grainCells = 64, int pitsCells = 128,
                                                float pitsDensity = 0.02f,
                                                int hpSmall = 1, int hpLarge = 4)
    {
        // Fine/mid grain
        var grain = PeriodicFBM(w, h, octaves: 5, baseCellsX: grainCells, baseCellsY: grainCells,
                                lacunarity: 2.0f, gain: 0.55f, seed: seed + 101);
        Normalize01(grain);

        // Sparse pits as depressions
        var pitsNoise = PeriodicFBM(w, h, octaves: 2, baseCellsX: pitsCells, baseCellsY: pitsCells,
                                    lacunarity: 2.0f, gain: 0.6f, seed: seed + 202);
        Normalize01(pitsNoise);

        float threshold = 1f - pitsDensity; // e.g., 0.98 -> 2% pits
        int hh = h, ww = w;
        float[,] pits = new float[hh, ww];
        for (int y = 0; y < hh; y++)
            for (int x = 0; x < ww; x++)
                pits[y, x] = (pitsNoise[y, x] > threshold) ? -1f : 0f; // depressions only

        // Combine micro sources
        float[,] detail = new float[hh, ww];
        for (int y = 0; y < hh; y++)
            for (int x = 0; x < ww; x++)
                detail[y, x] = 0.8f * (grain[y, x] - 0.5f) + 0.2f * pits[y, x]; // zero-mean-ish

        // High-pass to eliminate any drift and lock to micro
        detail = HighPassDoG(detail, radiusSmall: hpSmall, radiusLarge: hpLarge); // output ~[-1,1]
        return detail;
    }

    // -------------------- Blend modes --------------------
    enum BlendMode { Add, Multiply }

    static float[,] BlendBump(float[,] baseBump01, float[,] detailMinus1To1, BlendMode mode, float strength)
    {
        int h = baseBump01.GetLength(0), w = baseBump01.GetLength(1);
        float[,] outImg = new float[h, w];

        for (int y = 0; y < h; y++)
        {
            for (int x = 0; x < w; x++)
            {
                float orig = baseBump01[y, x];
                float d = detailMinus1To1[y, x];

                float v;
                if (mode == BlendMode.Add)
                    v = orig + strength * d;                    // additive micro relief
                else // Multiply
                    v = orig * (1.0f + strength * d);           // amplitude modulation

                outImg[y, x] = Clamp01(v);
            }
        }
        return outImg;
    }

    // -------------------- Bump -> Normal (wrapped gradients for tiling) --------------------
    static Bitmap BumpToNormal(float[,] bump01, float strength = 3.0f, bool invertY = true)
    {
        int h = bump01.GetLength(0), w = bump01.GetLength(1);
        Bitmap normal = new Bitmap(w, h, PixelFormat.Format24bppRgb);

        for (int y = 0; y < h; y++)
        {
            int up = Mod(y - 1, h);
            int down = Mod(y + 1, h);
            for (int x = 0; x < w; x++)
            {
                int left = Mod(x - 1, w);
                int right = Mod(x + 1, w);

                float dx = (bump01[y, right] - bump01[y, left]) * 0.5f * strength;
                float dy = (bump01[down, x] - bump01[up, x]) * 0.5f * strength;

                float nx = -dx;
                float ny = invertY ? -dy : dy;   // DirectX/Unity (true) vs OpenGL (false)
                float nz = 1.0f;

                float len = (float)Math.Sqrt(nx * nx + ny * ny + nz * nz);
                nx /= len; ny /= len; nz /= len;

                byte r = (byte)(Clamp01(nx * 0.5f + 0.5f) * 255f);
                byte g = (byte)(Clamp01(ny * 0.5f + 0.5f) * 255f);
                byte b = (byte)(Clamp01(nz * 0.5f + 0.5f) * 255f);

                normal.SetPixel(x, y, Color.FromArgb(r, g, b));
            }
        }
        return normal;
    }

    // -------------------- Bitmap <-> float utilities --------------------
    static float[,] BitmapToFloat01(Bitmap bmp)
    {
        int w = bmp.Width, h = bmp.Height;
        float[,] img = new float[h, w];
        for (int y = 0; y < h; y++)
        {
            for (int x = 0; x < w; x++)
            {
                var c = bmp.GetPixel(x, y);
                float v = (0.2126f * c.R + 0.7152f * c.G + 0.0722f * c.B) / 255f; // luminance
                img[y, x] = v;
            }
        }
        Normalize01(img);
        return img;
    }

    static Bitmap SaveGrayscale24(float[,] img01, string path)
    {
        int h = img01.GetLength(0), w = img01.GetLength(1);
        Bitmap bmp = new Bitmap(w, h, PixelFormat.Format24bppRgb);
        for (int y = 0; y < h; y++)
        {
            for (int x = 0; x < w; x++)
            {
                byte g = (byte)(Clamp01(img01[y, x]) * 255f);
                bmp.SetPixel(x, y, Color.FromArgb(g, g, g));
            }
        }
        bmp.Save(path, ImageFormat.Png);
        return bmp;
    }

    // -------------------- Make existing bump seamless (optional) --------------------
    static float[,] MakeSeamlessByEdgeBlend(float[,] img01, int margin)
    {
        int h = img01.GetLength(0), w = img01.GetLength(1);
        margin = Math.Max(1, Math.Min(margin, Math.Min(w, h) / 2));
        float[,] outImg = (float[,])img01.Clone();

        // Horizontal blend left/right
        for (int y = 0; y < h; y++)
        {
            for (int x = 0; x < margin; x++)
            {
                float t = (float)x / margin;
                float vLeft = img01[y, x];
                float vRightOpp = img01[y, w - 1 - x];
                outImg[y, x] = Lerp(vLeft, vRightOpp, t);
                outImg[y, w - 1 - x] = Lerp(vRightOpp, vLeft, t);
            }
        }
        // Vertical blend top/bottom
        for (int y = 0; y < margin; y++)
        {
            float t = (float)y / margin;
            for (int x = 0; x < w; x++)
            {
                float vTop = outImg[y, x];
                float vBottomOpp = outImg[h - 1 - y, x];
                outImg[y, x] = Lerp(vTop, vBottomOpp, t);
                outImg[h - 1 - y, x] = Lerp(vBottomOpp, vTop, t);
            }
        }

        outImg = BoxBlur(outImg, radius: 1, passes: 1);
        Normalize01(outImg);
        return outImg;
    }

    // -------------------- Procedural base bump (optional; not used for augmentation, but kept) --------------------
    static float[,] MakeConcreteBumpTile(int w, int h, int seed)
    {
        var baseLayer = PeriodicFBM(w, h, 4, 8, 8, 2.0f, 0.55f, seed);
        var grain     = PeriodicFBM(w, h, 5, 32, 32, 2.0f, 0.55f, seed + 101);
        var pitsNoise = PeriodicFBM(w, h, 2, 128, 128, 2.0f, 0.6f, seed + 202);

        Normalize01(baseLayer); Normalize01(grain); Normalize01(pitsNoise);

        int hh = h, ww = w;
        float[,] pits = new float[hh, ww];
        for (int y = 0; y < hh; y++)
            for (int x = 0; x < ww; x++)
                pits[y, x] = (pitsNoise[y, x] > 0.98f) ? -0.2f : 0f;

        float[,] bump = new float[hh, ww];
        for (int y = 0; y < hh; y++)
            for (int x = 0; x < ww; x++)
                bump[y, x] = (0.55f * baseLayer[y, x] + 0.35f * grain[y, x]) + pits[y, x];

        bump = BoxBlur(bump, radius: 1, passes: 1);
        Normalize01(bump);
        return bump;
    }

    // -------------------- Entry: augment existing bump with concrete detail --------------------
    static void AugmentBumpWithConcrete(Bitmap existingBumpOrNull,
                                        int targetW = 1024, int targetH = 1024,
                                        bool makeExistingSeamless = false, int margin = 24,
                                        BlendMode mode = BlendMode.Multiply,
                                        float microStrength = 0.25f,
                                        int grainCells = 64, int pitsCells = 128,
                                        float pitsDensity = 0.02f,
                                        int hpSmall = 1, int hpLarge = 4,
                                        float normalStrength = 3.0f, bool invertY = true,
                                        int seed = 1337)
    {
        // Source bump (01)
        float[,] baseBump01;
        if (existingBumpOrNull != null)
        {
            Bitmap src = existingBumpOrNull;
            if (src.Width != targetW || src.Height != targetH)
                src = new Bitmap(src, new Size(targetW, targetH));

            baseBump01 = BitmapToFloat01(src);
            if (makeExistingSeamless)
                baseBump01 = MakeSeamlessByEdgeBlend(baseBump01, margin);
            Console.WriteLine("Loaded existing bump and prepared for tiling.");
        }
        else
        {
            baseBump01 = MakeConcreteBumpTile(targetW, targetH, seed);
            Console.WriteLine("No bump supplied: generated a procedural concrete base.");
        }

        // Tileable micro-detail layer (~[-1,1]) with high-pass
        var detail = GenerateConcreteDetailLayer(targetW, targetH, seed,
                                                grainCells, pitsCells, pitsDensity,
                                                hpSmall, hpLarge);

        // Blend detail into the base bump
        var outBump01 = BlendBump(baseBump01, detail, mode, microStrength);

        // Save bump + normal (tile-friendly)
        var bumpBmp = SaveGrayscale24(outBump01, "concrete_bump_augmented.png");
        var normalBmp = BumpToNormal(outBump01, strength: normalStrength, invertY: invertY);
        normalBmp.Save("concrete_normal_augmented.png", ImageFormat.Png);

        Console.WriteLine("Done. Saved concrete_bump_augmented.png and concrete_normal_augmented.png");
    }

    static void Main()
    {
        // Option A: augment supplied bump
        /*
        using var inputBump = (Bitmap)Image.FromFile("your_bump_input.png");
        AugmentBumpWithConcrete(existingBumpOrNull: inputBump,
                                targetW: 1024, targetH: 1024,
                                makeExistingSeamless: true, margin: 32,
                                mode: BlendMode.Multiply, microStrength: 0.3f,
                                grainCells: 64, pitsCells: 128, pitsDensity: 0.02f,
                                hpSmall: 1, hpLarge: 4,
                                normalStrength: 3.0f, invertY: true,
                                seed: 1337);
        */

        // Option B: no input -> generate base, then augment anyway (shows pipeline)
        AugmentBumpWithConcrete(existingBumpOrNull: null,
                                targetW: 1024, targetH: 1024,
                                makeExistingSeamless: true, margin: 24,
                                mode: BlendMode.Multiply, microStrength: 0.25f,
                                grainCells: 64, pitsCells: 128, pitsDensity: 0.02f,
                                hpSmall: 1, hpLarge: 4,
                                normalStrength: 3.0f, invertY: true,
                                seed: 1337);
    }
}
