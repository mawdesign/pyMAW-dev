# -*- coding: utf-8 -*-
"""Dev tool (CPython 3 + numpy + Pillow): bake seamless bump-map sheets.

Writes into ../textures/ :
    <material>_base.png          8-bit grey, opaque, seamless
    <material>_pits_<1-3>.png    black + alpha (depth), seamless, nested levels
    <material>_scratch_<1-3>.png black + alpha (depth), seamless, nested levels
    textures.json                sheet size and pixels per mm

Everything is wrap-around (FFT filtering, wrapped stamping) so each sheet tiles.
Levels are nested: level 1 features are a subset of level 2, which are a subset of 3.

Usage: python bake_textures.py [brick|concrete|block|all] [--size 2048] [--seed 7]
"""
import argparse
import json
import os

import numpy as np
from PIL import Image

PPM = 2.0  # sheet pixels per millimetre
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "textures")


# ------------------------------------------------------------------ filters
def blur(a, sx, sy=None):
    """Wrap-around gaussian blur via FFT, sigma in pixels (x, y)."""
    sy = sx if sy is None else sy
    n_y, n_x = a.shape
    fx = np.fft.fftfreq(n_x)[None, :]
    fy = np.fft.fftfreq(n_y)[:, None]
    k = np.exp(-2.0 * (np.pi ** 2) * ((sx * fx) ** 2 + (sy * fy) ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * k))


def noise(rng, n, sx, sy=None):
    out = blur(rng.standard_normal((n, n)), sx, sy)
    return (out - out.mean()) / out.std()


# ------------------------------------------------------------------ stamping
def stamp_max(layer, cx, cy, patch):
    """Max-combine a small patch centred on (cx, cy) into layer with wrap-around."""
    n = layer.shape[0]
    h, w = patch.shape
    ys = (np.arange(h) + cy - h // 2) % n
    xs = (np.arange(w) + cx - w // 2) % n
    ix = np.ix_(ys, xs)
    layer[ix] = np.maximum(layer[ix], patch)


def pit_patch(rx, ry, angle, depth):
    r = int(np.ceil(max(rx, ry) * 1.3)) + 1
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1].astype(float)
    c, s = np.cos(angle), np.sin(angle)
    u = (xx * c + yy * s) / rx
    v = (-xx * s + yy * c) / ry
    q = np.clip(1.0 - (u * u + v * v), 0.0, 1.0)
    return depth * q ** 1.4


def stroke_patch(length, width, angle, depth, rng):
    """Thin tapered scratch, centred on its midpoint."""
    r = int(np.ceil(length / 2 + width * 3)) + 2
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1].astype(float)
    c, s = np.cos(angle), np.sin(angle)
    t = xx * c + yy * s                       # along the stroke
    d = -xx * s + yy * c                      # across the stroke
    wobble = 0.35 * width * np.sin(t / max(length, 1.0) * np.pi * rng.uniform(1.0, 3.0))
    taper = np.clip(1.0 - (np.abs(t) / (length / 2.0)) ** 2.5, 0.0, 1.0)
    return depth * taper * np.exp(-(((d - wobble) / width) ** 2))


def nested_levels(n, counts, make_feature, rng):
    """Build one RGBA-ready alpha layer per level; level k uses the first counts[k] features."""
    feats = [make_feature(rng) for _ in range(counts[-1])]
    layers = []
    for count in counts:
        layer = np.zeros((n, n))
        for f in feats[:count]:
            stamp_max(layer, *f)
        layers.append(layer)
    return layers


# ------------------------------------------------------------------ materials
def feature_factory(n, kind, spec):
    def make(rng):
        cx, cy = int(rng.integers(0, n)), int(rng.integers(0, n))
        if kind == "pit":
            r = float(np.exp(rng.normal(np.log(spec["r_med"] * PPM), spec["r_sigma"])))
            r = float(np.clip(r, 0.6, spec["r_max"] * PPM))
            aspect = rng.uniform(1.0, spec["aspect"])
            ang = spec.get("angle0", 0.0) + rng.normal(0.0, 0.25) if spec["aligned"] else rng.uniform(0, np.pi)
            return cx, cy, pit_patch(r * aspect, r, ang, rng.uniform(*spec["depth"]))
        length = float(np.clip(np.exp(rng.normal(np.log(spec["len_med"] * PPM), 0.6)), 6, spec["len_max"] * PPM))
        width = rng.uniform(*spec["width"]) * PPM
        ang = spec.get("angle0", 0.0) + rng.normal(0.0, np.radians(spec["ang_sd"])) if spec["aligned"] else rng.uniform(0, np.pi)
        return cx, cy, stroke_patch(length, width, ang, rng.uniform(*spec["depth"]), rng)
    return make


MATERIALS = {
    "brick": dict(
        grain=[(0.8, 0.8, 0.55), (2.5, 2.5, 0.35), (40.0, 1.2, 0.50), (12.0, 0.8, 0.30), (60.0, 60.0, 0.30)],
        mean=0.62, std=0.085,
        pit=dict(r_med=0.75, r_sigma=0.5, r_max=3.5, aspect=2.2, aligned=True, depth=(0.45, 0.9)),
        pit_counts=[360, 1200, 3600],
        scratch=dict(len_med=7.0, len_max=45.0, width=(0.3, 0.7), ang_sd=1.5, aligned=True, depth=(0.15, 0.6)),
        scratch_counts=[480, 1500, 4200],
    ),
    "concrete": dict(
        grain=[(0.7, 0.7, 0.60), (2.0, 2.0, 0.50), (30.0, 30.0, 0.25), (110.0, 110.0, 0.20)],
        mean=0.66, std=0.055,
        pit=dict(r_med=0.9, r_sigma=0.55, r_max=3.0, aspect=1.3, aligned=False, depth=(0.35, 0.8)),
        pit_counts=[600, 2000, 6000],
        scratch=dict(len_med=9.0, len_max=40.0, width=(0.4, 0.9), ang_sd=0.0, aligned=False, depth=(0.30, 0.70)),
        scratch_counts=[300, 900, 2500],
    ),
    # concrete block: form-release drag runs vertically (texture angle 0 = horizontal, so 90 deg here)
    "block": dict(
        grain=[(0.7, 0.7, 0.55), (2.0, 2.0, 0.45), (1.0, 35.0, 0.55), (0.8, 12.0, 0.30), (30.0, 30.0, 0.25), (110.0, 110.0, 0.20)],
        mean=0.66, std=0.06,
        pit=dict(r_med=0.9, r_sigma=0.55, r_max=3.0, aspect=2.0, aligned=True, angle0=np.pi / 2, depth=(0.35, 0.8)),
        pit_counts=[600, 2000, 6000],
        scratch=dict(len_med=18.0, len_max=90.0, width=(0.4, 1.0), ang_sd=1.5, aligned=True, angle0=np.pi / 2, depth=(0.25, 0.65)),
        scratch_counts=[300, 900, 2500],
    ),
}


def bake(material, n, seed, out_dir):
    spec = MATERIALS[material]
    rng = np.random.default_rng(seed)
    base = np.zeros((n, n))
    for sx, sy, w in spec["grain"]:
        base += w * noise(rng, n, sx, sy)
    base = (base - base.mean()) / base.std()
    grey = np.clip(spec["mean"] + spec["std"] * base, 0.0, 1.0)
    Image.fromarray((grey * 255 + 0.5).astype(np.uint8), "L").save(os.path.join(out_dir, "%s_base.png" % material), optimize=True)

    for kind, key in (("pit", "pits"), ("scratch", "scratch")):
        layers = nested_levels(n, spec["%s_counts" % kind], feature_factory(n, kind, spec[kind]), rng)
        for level, alpha in enumerate(layers, 1):
            rgba = np.zeros((n, n, 4), np.uint8)
            rgba[..., 3] = (np.clip(alpha, 0, 1) * 255 + 0.5).astype(np.uint8)
            Image.fromarray(rgba, "RGBA").save(os.path.join(out_dir, "%s_%s_%d.png" % (material, key, level)), optimize=True)
    print("baked", material)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("material", nargs="?", default="all")
    ap.add_argument("--size", type=int, default=2048)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for m in (list(MATERIALS) if a.material == "all" else [a.material]):
        bake(m, a.size, a.seed + list(MATERIALS).index(m) * 101, a.out)
    with open(os.path.join(a.out, "textures.json"), "w") as fh:
        json.dump({"size": a.size, "ppm": PPM, "materials": sorted(MATERIALS), "levels": 3}, fh, indent=2)


if __name__ == "__main__":
    main()
