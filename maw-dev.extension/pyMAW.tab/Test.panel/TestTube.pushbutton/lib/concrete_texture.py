import math
import random
import clr

# -------------------- .NET Imports --------------------
import System
from System import Array, Byte, Int32
from System.Runtime.InteropServices import Marshal

# Try importing System.Drawing (Standard for pyRevit/IronPython)
try:
    clr.AddReference("System.Drawing")
    from System.Drawing import (
        Bitmap,
        Graphics,
        Color,
        Rectangle,
        Imaging
    )
    from System.Drawing.Imaging import ImageLockMode, PixelFormat
except ImportError:
    pass

class ConcreteGenerator:
    """
    A class to generate procedural concrete textures (Bump and Normal maps).
    Uses System.Drawing.Bitmap with LockBits/Marshal.Copy for performance in IronPython.
    """

    # -------------------- Math Helpers --------------------
    
    @staticmethod
    def _smoother_step(t):
        return t * t * t * (t * (t * 6 - 15) + 10)

    @staticmethod
    def _lerp(a, b, t):
        return a + t * (b - a)

    @staticmethod
    def _clamp01(v):
        return max(0.0, min(1.0, v))

    # -------------------- Noise Generation --------------------

    @staticmethod
    def _periodic_value_noise(w, h, cells_x, cells_y, seed):
        rng = random.Random(seed)
        g = [[rng.random() for _ in range(cells_x)] for _ in range(cells_y)]
        out_img = [[0.0] * w for _ in range(h)]

        for y in range(h):
            fy = float(y) / h * cells_y
            yi = int(math.floor(fy))
            ty = ConcreteGenerator._smoother_step(fy - yi)
            yi0 = yi % cells_y
            yi1 = (yi + 1) % cells_y

            for x in range(w):
                fx = float(x) / w * cells_x
                xi = int(math.floor(fx))
                tx = ConcreteGenerator._smoother_step(fx - xi)
                xi0 = xi % cells_x
                xi1 = (xi + 1) % cells_x

                v00 = g[yi0][xi0]
                v10 = g[yi0][xi1]
                v01 = g[yi1][xi0]
                v11 = g[yi1][xi1]

                a = ConcreteGenerator._lerp(v00, v10, tx)
                b = ConcreteGenerator._lerp(v01, v11, tx)
                out_img[y][x] = ConcreteGenerator._lerp(a, b, ty)
        return out_img

    @staticmethod
    def _periodic_fbm(w, h, octaves, base_cells_x, base_cells_y, lacunarity, gain, seed):
        total = [[0.0] * w for _ in range(h)]
        amp = 1.0
        norm = 0.0

        for i in range(octaves):
            cx = max(1, int(base_cells_x * math.pow(lacunarity, i)))
            cy = max(1, int(base_cells_y * math.pow(lacunarity, i)))
            n = ConcreteGenerator._periodic_value_noise(w, h, cx, cy, seed + i * 31)
            for y in range(h):
                for x in range(w):
                    total[y][x] += amp * n[y][x]
            norm += amp
            amp *= gain

        div = max(norm, 1e-6)
        for y in range(h):
            for x in range(w):
                total[y][x] /= div
        return total

    @staticmethod
    def _box_blur(img, radius, passes):
        if radius <= 0 or passes <= 0:
            return img
        h = len(img)
        w = len(img[0])
        tmp = [row[:] for row in img]
        out_img = [[0.0] * w for _ in range(h)]

        for p in range(passes):
            for y in range(h):
                for x in range(w):
                    sum_val = 0.0
                    count = 0
                    for k in range(-radius, radius + 1):
                        xi = (x + k) % w
                        sum_val += tmp[y][xi]
                        count += 1
                    out_img[y][x] = sum_val / count
            for y in range(h):
                for x in range(w):
                    sum_val = 0.0
                    count = 0
                    for k in range(-radius, radius + 1):
                        yi = (y + k) % h
                        sum_val += out_img[yi][x]
                        count += 1
                    tmp[y][x] = sum_val / count
        return tmp

    # -------------------- Main Generation Logic --------------------

    @staticmethod
    def generate_bump_array(w, h, seed, 
                            pit_density=0.97, 
                            pit_depth=0.20,
                            grain_strength=0.35,
                            base_scale=5.0,
                            base_depth=0.55,
                            trowel_strength=0.0):
        """
        Generates the raw float array [h][w].
        
        Args:
            trowel_strength (float): 0.0 to 2.0.
                                     Boosts the surface height and clamps it at 1.0.
                                     This creates flat "troweled" tops.
        """
        
        # 1. Base Layer (Main undulation)
        base_cx = int(8 * base_scale)
        base_cy = int(8 * base_scale)
        base_layer = ConcreteGenerator._periodic_fbm(w, h, 4, base_cx, base_cy, 2.0, 0.55, seed)
        
        # 2. Grain (Fine Aggregate)
        grain_cx = int(32 * base_scale)
        grain_cy = int(32 * base_scale)
        grain = ConcreteGenerator._periodic_fbm(w, h, 5, grain_cx, grain_cy, 2.0, 0.55, seed + 101)
        
        # 3. Pits
        pits_noise = ConcreteGenerator._periodic_fbm(w, h, 1, 128, 128, 2.0, 1.0, seed + 202)
        
        # 4. Stains
        stains = ConcreteGenerator._periodic_fbm(w, h, 3, 4, 4, 2.0, 0.6, seed + 303)

        final_bump = [[0.0] * w for _ in range(h)]

        # Trowel logic: We boost the signal to push it over 1.0, then clamp it.
        # This flattens the peaks.
        trowel_mult = 1.0 + (trowel_strength * 2.0) # Map 0..1 slider to 1.0..3.0 multiplier

        for y in range(h):
            for x in range(w):
                # Calculate Layers
                is_pit = 1.0 if pits_noise[y][x] > pit_density else 0.0
                stain_val = ConcreteGenerator._clamp01(0.8 + 0.2 * stains[y][x])

                # Compose Surface (Base + Grain)
                surface = (base_depth * base_layer[y][x]) + \
                          (grain_strength * grain[y][x])
                
                # Apply Trowel Flattening
                # Boost height then clamp at 1.0 (White)
                if trowel_strength > 0:
                    surface = surface * trowel_mult
                    if surface > 1.0:
                        surface = 1.0
                
                # Subtract Pits
                # We subtract pits *after* clamping so they dig into the flat surface
                val = surface - (pit_depth * is_pit)
                
                # Apply stain
                final_bump[y][x] = val * stain_val

        final_bump = ConcreteGenerator._box_blur(final_bump, 1, 1)
        return final_bump

    # -------------------- Optimized Bitmap Output --------------------

    @staticmethod
    def array_to_bitmap_fast(data):
        h = len(data)
        w = len(data[0])
        bmp = Bitmap(w, h, PixelFormat.Format24bppRgb)
        rect = Rectangle(0, 0, w, h)
        bmp_data = bmp.LockBits(rect, ImageLockMode.WriteOnly, bmp.PixelFormat)
        
        # Determine normalization range
        min_v = float('inf')
        max_v = float('-inf')
        for row in data:
            for v in row:
                if v < min_v: min_v = v
                if v > max_v: max_v = v
        
        # Avoid division by zero
        dist = max(max_v - min_v, 1e-6)

        stride = bmp_data.Stride
        total_bytes = abs(stride) * h
        pixel_bytes = [0] * total_bytes 
        
        for y in range(h):
            row_offset = y * stride
            for x in range(w):
                # Normalize value to 0-1 range
                val = (data[y][x] - min_v) / dist
                byte_val = int(ConcreteGenerator._clamp01(val) * 255)
                
                idx = row_offset + (x * 3)
                pixel_bytes[idx]     = byte_val
                pixel_bytes[idx + 1] = byte_val
                pixel_bytes[idx + 2] = byte_val

        net_array = Array[Byte](pixel_bytes)
        Marshal.Copy(net_array, 0, bmp_data.Scan0, total_bytes)
        bmp.UnlockBits(bmp_data)
        return bmp

    @staticmethod
    def bump_to_normal_map_fast(bump_data, strength=3.0, invert_y=True):
        h = len(bump_data)
        w = len(bump_data[0])
        bmp = Bitmap(w, h, PixelFormat.Format24bppRgb)
        rect = Rectangle(0, 0, w, h)
        bmp_data = bmp.LockBits(rect, ImageLockMode.WriteOnly, bmp.PixelFormat)
        
        stride = bmp_data.Stride
        total_bytes = abs(stride) * h
        pixel_bytes = [0] * total_bytes

        for y in range(h):
            row_offset = y * stride
            up = (y - 1) % h
            down = (y + 1) % h
            for x in range(w):
                left = (x - 1) % w
                right = (x + 1) % w

                dx = (bump_data[y][right] - bump_data[y][left]) * 0.5 * strength
                dy = (bump_data[down][x] - bump_data[up][x]) * 0.5 * strength

                nx = -dx
                ny = -dy if invert_y else dy
                nz = 1.0

                length = math.sqrt(nx*nx + ny*ny + nz*nz)
                
                r = int(ConcreteGenerator._clamp01((nx / length) * 0.5 + 0.5) * 255)
                g = int(ConcreteGenerator._clamp01((ny / length) * 0.5 + 0.5) * 255)
                b = int(ConcreteGenerator._clamp01((nz / length) * 0.5 + 0.5) * 255)

                idx = row_offset + (x * 3)
                pixel_bytes[idx]     = b
                pixel_bytes[idx + 1] = g
                pixel_bytes[idx + 2] = r

        net_array = Array[Byte](pixel_bytes)
        Marshal.Copy(net_array, 0, bmp_data.Scan0, total_bytes)
        bmp.UnlockBits(bmp_data)
        return bmp

# -------------------- Public API --------------------

def create_concrete_textures(width, height, seed=1337, 
                             normal_strength=3.0,
                             pit_density=0.97,
                             pit_depth=0.20,
                             grain_strength=0.35,
                             base_scale=5.0,
                             base_depth=0.55,
                             trowel_strength=0.0):
    """
    Returns tuple: (bump_bitmap, normal_bitmap, raw_bump_data)
    """
    
    bump_data = ConcreteGenerator.generate_bump_array(
        width, height, seed,
        pit_density=pit_density,
        pit_depth=pit_depth,
        grain_strength=grain_strength,
        base_scale=base_scale,
        base_depth=base_depth,
        trowel_strength=trowel_strength
    )
    
    bump_bmp = ConcreteGenerator.array_to_bitmap_fast(bump_data)
    
    normal_bmp = ConcreteGenerator.bump_to_normal_map_fast(
        bump_data, 
        strength=normal_strength
    )
    
    return bump_bmp, normal_bmp, bump_data