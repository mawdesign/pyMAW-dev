
using System;
using System.Drawing;
using System.Drawing.Imaging;

class Program
{
    // -------------------- Math helpers --------------------
    static float SmootherStep(float t) => t * t * t * (t * (t * 6 - 15) + 10);

    // -------------------- Periodic (tileable) value noise --------------------
    // Generates a tileable noise field: the pattern repeats every image width/height.
    static float[,] PeriodicValueNoise(int w, int h, int cellsX, int cellsY, int seed)
    {
        var rng = new Random(seed);
        // Random grid values for the period
        float[,] g = new float[cellsY, cellsX];
        for (int y = 0; y < cellsY; y++)
            for (int x = 0; x < cellsX; x++)
                g[y, x] = (float)rng.NextDouble();

        float[,] outImg = new float[h, w];
        for (int y = 0; y < h; y++)
        {
            // Map image y to grid coordinates so we have exactly cellsY cells over height
            float fy = (float)y / h * cellsY;
            int yi = (int)Math.Floor(fy);
            float ty = SmootherStep(fy - yi);

            int yi0 = Mod(yi, cellsY);
            int yi1 = Mod(yi + 1, cellsY);

            for (int x = 0; x < w; x++)
            {
                float fx = (float)x / w * cellsX;
                int xi = (int)Math.Floor(fx);
                float tx = SmootherStep(fx - xi);

                int xi0 = Mod(xi, cellsX);
                int xi1 = Mod(xi + 1, cellsX);

                float v00 = g[yi0, xi0];
                float v10 = g[yi0, xi1];
                float v01 = g[yi1, xi0];
                float v11 = g[yi1, xi1];

                float a = Lerp(v00, v10, tx);
                float b = Lerp(v01, v11, tx);
                outImg[y, x] = Lerp(a, b, ty);
            }
        }
        return outImg;
    }

    // -------------------- Tileable fBm (fractional Brownian motion) --------------------
    static float[,] PeriodicFBM(int w, int h, int octaves, int baseCellsX, int baseCellsY, float lacunarity, float gain, int seed)
    {
        float[,] total = new float[h, w];
        float amp = 1f, norm = 0f;

        for (int i = 0; i < octaves; i++)
        {
            int cx = Math.Max(1, (int)(baseCellsX * Math.Pow(lacunarity, i)));
            int cy = Math.Max(1, (int)(baseCellsY * Math.Pow(lacunarity, i)));
            var n = PeriodicValueNoise(w, h, cx, cy, seed + i * 31);

            // accumulate
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

    // -------------------- Simple separable box blur (tile-aware) --------------------
    static float[,] BoxBlur(float[,] img, int radius, int passes)
    {
        if (radius <= 0 || passes <= 0) return img;
        int h = img.GetLength(0);
        int w = img.GetLength(1);
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
                    int count = 0;
                    for (int k = -radius; k <= radius; k++)
                    {
                        int xi = Mod(x + k, w);
                        sum += tmp[y, xi];
                        count++;
                    }
                    outImg[y, x] = sum / count;
                }
            }
            // Vertical
            for (int y = 0; y < h; y++)
            {
                for (int x = 0; x < w; x++)
                {
                    float sum = 0f;
                    int count = 0;
                    for (int k = -radius; k <= radius; k++)
                    {
                        int yi = Mod(y + k, h);
                        sum += outImg[yi, x];
                        count++;
                    }
                    tmp[y, x] = sum / count;
                }
            }
        }
        return tmp;
    }

    // -------------------- Bump -> Normal map (wrapped gradients for tiling) --------------------
    static Bitmap BumpToNormal(float[,] bump, float strength = 3.0f, bool invertY = false)
    {
        int h = bump.GetLength(0);
        int w = bump.GetLength(1);
        Bitmap normal = new Bitmap(w, h, PixelFormat.Format24bppRgb);

        for (int y = 0; y < h; y++)
        {
            int up = Mod(y - 1, h);
            int down = Mod(y + 1, h);
            for (int x = 0; x < w; x++)
            {
                int left = Mod(x - 1, w);
                int right = Mod(x + 1, w);

                float dx = (bump[y, right] - bump[y, left]) * 0.5f * strength;
                float dy = (bump[down, x] - bump[up, x]) * 0.5f * strength;

                // Image coordinates y grows downward; adjust Y to chosen convention
                float nx = -dx;
                float ny = invertY ? -dy : dy; // flip for DirectX if desired
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

    // -------------------- Utilities --------------------
    static float Lerp(float a, float b, float t) => a + t * (b - a);
    static int Mod(int a, int m) { int r = a % m; return r < 0 ? r + m : r; }
    static float Clamp01(float v) => v < 0 ? 0 : (v > 1 ? 1 : v);

    static Bitmap SaveGrayscale24(float[,] img, string path)
    {
        int h = img.GetLength(0);
        int w = img.GetLength(1);

        // Normalize to [0,1] using min/max
        float min = float.MaxValue, max = float.MinValue;
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
            { float v = img[y, x]; if (v < min) min = v; if (v > max) max = v; }

        Bitmap bmp = new Bitmap(w, h, PixelFormat.Format24bppRgb);
        for (int y = 0; y < h; y++)
        {
            for (int x = 0; x < w; x++)
            {
                float v = (img[y, x] - min) / Math.Max(max - min, 1e-6f);
                byte g = (byte)(Clamp01(v) * 255f);
                bmp.SetPixel(x, y, Color.FromArgb(g, g, g));
            }
        }
        bmp.Save(path, ImageFormat.Png);
        return bmp;
    }

    // -------------------- Concrete bump synthesis (tileable) --------------------
    static float[,] MakeConcreteBumpTile(int w, int h, int seed)
    {
        // Low-frequency undulation (few cells across image)
        var baseLayer = PeriodicFBM(w, h, octaves: 4, baseCellsX: 8, baseCellsY: 8, lacunarity: 2.0f, gain: 0.55f, seed: seed);

        // Mid-frequency aggregate/grain
        var grain = PeriodicFBM(w, h, octaves: 5, baseCellsX: 32, baseCellsY: 32, lacunarity: 2.0f, gain: 0.55f, seed: seed + 101);

        // High-frequency pits from thresholded noise (tileable)
        var pitsNoise = PeriodicFBM(w, h, octaves: 1, baseCellsX: 128, baseCellsY: 128, lacunarity: 2.0f, gain: 1.0f, seed: seed + 202);
        float[,] pitsMask = new float[h, w];
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
                pitsMask[y, x] = pitsNoise[y, x] > 0.97f ? 1f : 0f; // sparse pits

        // Stain mask (large blobs, multiplicative)
        var stains = PeriodicFBM(w, h, octaves: 3, baseCellsX: 4, baseCellsY: 4, lacunarity: 2.0f, gain: 0.6f, seed: seed + 303);
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
                stains[y, x] = Clamp01(0.8f + 0.2f * stains[y, x]);

        // Combine layers
        float[,] bump = new float[h, w];
        for (int y = 0; y < h; y++)
        {
            for (int x = 0; x < w; x++)
            {
                float v = 0.55f * baseLayer[y, x]
                        + 0.35f * grain[y, x]
                        - 0.20f * pitsMask[y, x]; // pits as depressions
                bump[y, x] = v * stains[y, x];
            }
        }

        // Subtle box blur to avoid harsh pixels (tile-aware)
        bump = BoxBlur(bump, radius: 1, passes: 1);

        // Optional: expand contrast (simple min/max normalization happens in SaveGrayscale24)
        return bump;
    }

    static void Main()
    {
        int W = 1024, H = 1024, seed = 1337;

        // Generate tileable bump
        var bump = MakeConcreteBumpTile(W, H, seed);

        // Save bump as grayscale PNG
        var bumpBmp = SaveGrayscale24(bump, "concrete_bump_tile.png");

        // Create and save normal map (set invertY to true for DirectX/Unity)
        bool invertY = true;          // flip green for DirectX-style normals; set false for OpenGL
        float strength = 3.0f;        // adjust normal intensity
        var normalBmp = BumpToNormal(bump, strength, invertY);
        normalBmp.Save("concrete_normal_tile.png", ImageFormat.Png);

        Console.WriteLine("Done. Saved concrete_bump_tile.png and concrete_normal_tile.png");
    }
