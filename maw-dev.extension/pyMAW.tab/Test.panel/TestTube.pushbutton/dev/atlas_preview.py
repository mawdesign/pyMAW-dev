# -*- coding: utf-8 -*-
"""Dev tool (CPython 3 + numpy + Pillow + scipy): reference renderer for texture_atlas plans.

Mimics the GDI+ TextureBrush logic in render_atlas() so atlases can be inspected
without Revit. Writes the atlas, and a 2x2 tiled copy to check the seams.

Usage: python atlas_preview.py KEY out.png [--material brick] [--width 230 --height 76 --mortar 10
        --length 609.6] [--pits 2 --scratch 2] [--ppm 2] [--joint 0.5] [--seed 1] [--tile]
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import map_coordinates

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "Tools.panel", "Make Pattern.pulldown", "lib")
sys.path.insert(0, LIB)

import pattern_cells as pc  # noqa: E402
import texture_atlas as ta  # noqa: E402

_cache = {}


def sheet(name):
    if name not in _cache:
        im = Image.open(os.path.join(ta.TEXTURE_DIR, name + ".png"))
        _cache[name] = np.asarray(im.convert("RGBA" if "base" not in name else "L"), dtype=np.float32) / 255.0
    return _cache[name]


def render(plan, joint_level=0.5, ss=3, outline_px=0):
    w, h = plan.width_px, plan.height_px
    out = np.full((h, w), joint_level, np.float32)
    base = sheet(plan.base_name)
    n = base.shape[0]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)

    def sample(layer, ch, x0, x1, y0, y1, ang):
        """Sample sheet channel for atlas pixels in the bbox, replicating the GDI+ matrix T*R*S."""
        px, py = xx[y0:y1, x0:x1] + 0.5, yy[y0:y1, x0:x1] + 0.5
        dx, dy = px - layer.ox, py - layer.oy
        a = np.radians(ang + layer.rot180)
        c, s = np.cos(a), np.sin(a)
        u = c * dx + s * dy              # inverse rotation
        v = -s * dx + c * dy
        u /= plan.sheet_scale * layer.flip
        v /= plan.sheet_scale
        arr = sheet(layer.name)
        arr = arr if arr.ndim == 2 else arr[..., ch]
        return map_coordinates(arr, [v - 0.5, u - 0.5], order=1, mode="grid-wrap")

    flat = plan.flat_level is not None
    if plan.fill_background_with_base and flat:
        out[:] = plan.flat_level
    elif plan.fill_background_with_base:
        class L:  # whole-atlas base fill
            ox = oy = 0.0
            flip = 1
            rot180 = 0
            name = plan.base_name
        out[:] = sample(L, 0, 0, w, 0, h, 0.0)

    for job in plan.jobs:
        xs = [p[0] for p in job.points_px]
        ys = [p[1] for p in job.points_px]
        x0, x1 = max(0, int(min(xs)) - 1), min(w, int(max(xs)) + 2)
        y0, y1 = max(0, int(min(ys)) - 1), min(h, int(max(ys)) + 2)
        if x1 <= x0 or y1 <= y0:
            continue
        bw, bh = x1 - x0, y1 - y0
        m = Image.new("L", (bw * ss, bh * ss), 0)
        ImageDraw.Draw(m).polygon([((x - x0) * ss, (y - y0) * ss) for x, y in job.points_px], fill=255)
        cov = np.asarray(m.resize((bw, bh), Image.BOX), dtype=np.float32) / 255.0
        if flat:
            reg = out[y0:y1, x0:x1]
            out[y0:y1, x0:x1] = reg * (1 - cov) + plan.flat_level * cov
        for layer in job.layers:
            if "base" in layer.name:
                val = sample(layer, 0, x0, x1, y0, y1, job.angle_deg)
                a = cov
            else:
                val = 0.0
                a = cov * sample(layer, 3, x0, x1, y0, y1, job.angle_deg)
            reg = out[y0:y1, x0:x1]
            out[y0:y1, x0:x1] = reg * (1 - a) + val * a

    for width, value in ((plan.edge_joint_px, joint_level), (outline_px, 0.16)):
        if width <= 0:
            continue
        m = Image.new("L", (w * ss, h * ss), 0)
        d = ImageDraw.Draw(m)
        for job in plan.jobs:
            pts = [(x * ss, y * ss) for x, y in job.points_px]
            d.line(pts + [pts[0], pts[1]], fill=255, width=max(1, int(round(width * ss))), joint="curve")
        cov = np.asarray(m.resize((w, h), Image.BOX), dtype=np.float32) / 255.0
        out = out * (1 - cov) + value * cov
    return out


S0 = 0.525         # shade of flat brick face; keep in step with texture_atlas.SHADE_FLAT
DARK_GAIN, LIGHT_GAIN = 2.5, 2.0


def colour_map(plan, brick_rgb, mortar_rgb, ss=3):
    """Flat colours: mortar everywhere, brick colour inside the cells (edge joints in mortar)."""
    w, h = plan.width_px, plan.height_px
    m = Image.new("L", (w * ss, h * ss), 0)
    d = ImageDraw.Draw(m)
    for job in plan.jobs:
        d.polygon([(x * ss, y * ss) for x, y in job.points_px], fill=255)
    if plan.edge_joint_px > 0:
        m2 = Image.new("L", (w * ss, h * ss), 0)
        d2 = ImageDraw.Draw(m2)
        for job in plan.jobs:
            pts = [(x * ss, y * ss) for x, y in job.points_px]
            d2.line(pts + [pts[0], pts[1]], fill=255, width=max(1, int(round(plan.edge_joint_px * ss))), joint="curve")
        m = Image.fromarray(np.where(np.asarray(m2) > 0, 0, np.asarray(m)).astype(np.uint8))
    cov = np.asarray(m.resize((w, h), Image.BOX), dtype=np.float32)[..., None] / 255.0
    return cov * np.array(brick_rgb, np.float32) + (1 - cov) * np.array(mortar_rgb, np.float32)


def shade(h, plan, brick_rgb, mortar_rgb, strength=0.2):
    """numpy twin of texture_atlas.render_colour_preview (same steps as the GDI+ draws)."""
    hs = np.roll(np.roll(h, 1, 0), 1, 1)                               # shifted (+1, +1), wrapped
    d = 0.5 * h + 0.5 * (1 - hs)                                       # 0.5 + 0.5 (h - hs)
    k = 1.0 + 24.0 * strength
    e = np.clip(0.5 + k * (d - 0.5), 0, 1)
    sh = 0.8 * e + 0.2 * h
    c = colour_map(plan, brick_rgb, mortar_rgb)
    dark = np.clip(DARK_GAIN * (S0 - sh), 0, 1)[..., None]             # black overlay
    c = c * (1 - dark)
    light = np.clip(LIGHT_GAIN * (sh - S0), 0, 1)[..., None]           # white overlay
    return np.clip(c * (1 - light) + light, 0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("key")
    ap.add_argument("out")
    ap.add_argument("--material", default="brick")
    ap.add_argument("--width", type=float)
    ap.add_argument("--height", type=float)
    ap.add_argument("--mortar", type=float)
    ap.add_argument("--length", type=float)
    ap.add_argument("--pits", type=int, default=2)
    ap.add_argument("--scratch", type=int, default=2)
    ap.add_argument("--ppm", type=float, default=2.0)
    ap.add_argument("--joint", type=float, default=0.5)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--repeats", help="NXxNY whole bond repeats, e.g. 4x5 (default: at least 800 mm each way)")
    ap.add_argument("--outline", type=float, default=0, help="preview outline width in px")
    ap.add_argument("--colour", help="hex, writes a shaded colour preview too")
    ap.add_argument("--mortar-colour", default="#ECECEC")
    ap.add_argument("--strength", type=float, default=0.2)
    ap.add_argument("--tile", action="store_true", help="also write a 2x2 tiled copy")
    a = ap.parse_args()
    extra = {"length": a.length} if a.length else {}
    pat = pc.build_pattern(a.key, width=a.width, height=a.height, mortar=a.mortar, **extra)
    mortar = a.mortar if a.mortar is not None else pc.load_catalog()[a.key].get("params", {}).get("mortar", 0)
    reps = tuple(int(v) for v in a.repeats.split("x")) if a.repeats else None
    plan = ta.plan_atlas(pat, a.material, a.pits, a.scratch, a.ppm, seed=a.seed, mortar=mortar, repeats=reps)
    img = render(plan, a.joint, outline_px=a.outline)
    Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8), "L").save(a.out)
    if a.colour:
        c = a.colour.lstrip("#")
        rgb = [int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
        mort = [int(a.mortar_colour.lstrip('#')[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
        col = shade(img, plan, rgb, mort, a.strength)
        Image.fromarray((col * 255 + 0.5).astype(np.uint8), "RGB").save(a.out.replace(".png", "_colour.png"))
    wmm, hmm = plan.size_mm
    print("%s: %s repeats, %dx%d px, Revit size %.2f x %.2f mm, %d cell draws" % (a.key, plan.repeats, plan.width_px, plan.height_px, wmm, hmm, len(plan.jobs)))
    if a.tile:
        t = np.tile(img, (2, 2))
        Image.fromarray((np.clip(t, 0, 1) * 255 + 0.5).astype(np.uint8), "L").save(a.out.replace(".png", "_tiled.png"))


if __name__ == "__main__":
    main()
