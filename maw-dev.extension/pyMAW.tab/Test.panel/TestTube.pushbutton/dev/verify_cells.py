# -*- coding: utf-8 -*-
"""Dev tool (CPython 3 + shapely + pyyaml): verify lib/pattern_cells.yaml.

1. Self-consistency: cells (grown by mortar/2) tile the repeat with no overlap or gap.
2. Against the fill pattern lines: every cell outline lies on the .pat lines,
   and the .pat faces equal the grown cells (where the .pat closes into faces).

Usage: python verify_cells.py <brick-raw.pat> <parquet.pat>
"""
import math
import os
import sys

from shapely.affinity import translate
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))

import pat_faces as pf  # noqa: E402
import pattern_cells as pc  # noqa: E402

TOL = 0.05  # mm


def octagon_sl_pat(s, name="OCTAGONS_SL_FIXED"):
    """Corrected single-line octagon + square pattern (6 line families)."""
    a = s / (1 + math.sqrt(2))
    d = s / (2 + math.sqrt(2))
    k = s / math.sqrt(2)
    per = s * math.sqrt(2)
    fmt = lambda *v: ",".join("%.9f" % x for x in v)
    rows = [
        fmt(0, -a / 2, s / 2, 0, s, a, -(s - a)),
        fmt(90, s / 2, -a / 2, 0, -s, a, -(s - a)),
        fmt(135, s / 2 + d, s / 2, -k, -k, a, -(per - a)),
        fmt(135, s / 2, s / 2 - d, -k, -k, a, -(per - a)),
        fmt(45, s / 2 - d, s / 2, k, -k, a, -(per - a)),
        fmt(45, s / 2, s / 2 - d, k, -k, a, -(per - a)),
    ]
    return "*%s,fixed\n;%%TYPE=MODEL\n%s\n" % (name, "\n".join(rows))


def grown(cell, mortar):
    poly = Polygon(cell.points)
    if mortar > 0:
        poly = poly.buffer(mortar / 2.0, join_style=2)
    return poly


def self_check(key, catalog, **dims):
    pat = pc.build_pattern(key, catalog=catalog, **dims)
    mortar = dims.get("mortar", catalog[key].get("params", {}).get("mortar", 0))
    rect = box(0, 0, pat.repeat_w, pat.repeat_h)
    pieces = []
    for cell in pat.cells:
        bx0, by0, bx1, by1 = cell.bounds()
        nx = int(math.ceil((bx1 - bx0 + mortar) / pat.repeat_w)) + 1
        ny = int(math.ceil((by1 - by0 + mortar) / pat.repeat_h)) + 1
        for ky in range(-ny, ny + 1):
            for kx in range(-nx, nx + 1):
                g = grown(cell.moved(kx * pat.repeat_w, ky * pat.repeat_h), mortar).intersection(rect)
                if g.area > 1e-6:
                    pieces.append(g)
    total = sum(p.area for p in pieces)
    overlap = total - unary_union(pieces).area
    gap = rect.area - unary_union(pieces).area
    ok = abs(overlap) < 1e-3 * rect.area and abs(gap) < 1e-3 * rect.area
    print("  self-check %-14s %s  repeat %.2f x %.2f  overlap %.3f  gap %.3f" % (
        key + str(dims.get("width", "")), "OK  " if ok else "FAIL", pat.repeat_w, pat.repeat_h, overlap, gap))
    return ok


def line_check(key, pat_text, pat_name, catalog, window=(-1800, -1800, 1800, 1800), **dims):
    pat = pc.build_pattern(key, catalog=catalog, **dims)
    mortar = dims.get("mortar", catalog[key].get("params", {}).get("mortar", 0))
    fams = pf.parse_pat_lines(pat_text, pat_name)
    segs = []
    for f in fams:
        segs.extend(pf.family_segments(f, window))
    union = unary_union(segs)
    near = union.buffer(TOL)
    faces = [f for f in pf.pat_faces(fams, window) if pf.inside(f, window, 20)]

    def coverage(shapes, tx, ty):
        tot = cov = 0.0
        for g in shapes:
            ring = translate(g, tx, ty).exterior
            tot += ring.length
            cov += ring.intersection(near).length
        return cov / tot if tot else 0.0

    base = [grown(c, mortar) for c in pat.cells]

    def all_copies(tx, ty):
        for c in pat.cells:
            for kx in range(-4, 5):
                for ky in range(-4, 5):
                    g = translate(grown(c.moved(kx * pat.repeat_w, ky * pat.repeat_h), mortar), tx, ty)
                    if pf.inside(g, window, 60):
                        yield g

    # candidate translations: put cell 0's first vertex on a pat line end point / face corner
    v0 = base[0].exterior.coords[0]
    ends = set()
    for s in segs:
        if abs(s.bounds[0]) < 1500 and abs(s.bounds[1]) < 1500:
            for p in (s.coords[0], s.coords[-1]):
                ends.add((round(p[0], 2), round(p[1], 2)))
    for f in faces:
        for p in f.exterior.coords:
            ends.add((round(p[0], 2), round(p[1], 2)))
    best = (0.0, None)
    for ex, ey in sorted(ends):
        tx, ty = ex - v0[0], ey - v0[1]
        c = coverage(base[:1], tx, ty)
        if c > best[0]:
            best = (c, (tx, ty))
        if c > 0.999:
            worst = min(coverage([g], 0, 0) for g in all_copies(tx, ty))
            if worst > 0.999:
                best = (worst, (tx, ty))
                break
            best = (max(best[0], worst * 0.999), best[1])
    cov, t = best
    if t is not None and os.environ.get("CELLS_OVERLAY"):
        from PIL import Image, ImageDraw
        from shapely.affinity import translate as _tr

        S = 1000.0 / (window[2] - window[0])
        img = Image.new("RGB", (1000, int((window[3] - window[1]) * S)), "white")
        d = ImageDraw.Draw(img)
        px = lambda x, y: ((x - window[0]) * S, (window[3] - y) * S)
        for s in segs:
            d.line([px(*s.coords[0]), px(*s.coords[-1])], fill="black", width=1)
        for c in pat.cells:
            for kx in range(-4, 5):
                for ky in range(-4, 5):
                    g = _tr(grown(c, mortar), t[0] + kx * pat.repeat_w, t[1] + ky * pat.repeat_h)
                    d.line([px(*q) for q in g.exterior.coords], fill=(255, 0, 0), width=1)
        img.save(os.environ["CELLS_OVERLAY"])
    # face equality, where the pattern closes into faces
    matched = total = 0
    if t is not None:
        for gg in all_copies(*t):
            total += 1
            cx, cy = gg.centroid.x, gg.centroid.y
            if any(f.bounds[0] <= cx <= f.bounds[2] and f.bounds[1] <= cy <= f.bounds[3]
                   and gg.symmetric_difference(f).area < 1e-3 * f.area for f in faces):
                matched += 1
    status = "OK  " if cov > 0.999 else "FAIL"
    print("  vs pat    %-14s %s  worst-cell edge coverage %.4f  translation %s  face match %d/%d (info)" % (
        key, status, cov, None if t is None else (round(t[0], 2), round(t[1], 2)), matched, total))
    return cov > 0.999


def main():
    brick_pat = open(sys.argv[1]).read()
    parquet_pat = open(sys.argv[2]).read()
    catalog = pc.load_catalog()
    ok = True
    print("Self-consistency")
    for key in catalog:
        ok &= self_check(key, catalog)
    for key, dims in (("STRETCHERHALF", dict(width=215, height=65, mortar=10)),
                      ("ENGLISH", dict(width=290, height=90, mortar=12)),
                      ("FLEMISH", dict(width=190, height=57, mortar=8)),
                      ("OCTAGONS", dict(width=200)),
                      ("BASKETWEAVE", dict(width=75, length=450)),
                      ("HERRINGBONE", dict(width=65, length=260))):
        ok &= self_check(key, catalog, **dims)
    print("Against fill pattern lines")
    for key, name in (("STACKED", "BRICK230X76X10STACKED_SL"), ("STRETCHERHALF", "BRICK230X76X10STRETCHERHALF_SL"),
                      ("STRETCHERTHIRD", "BRICK230X76X10STRETCHERTHIRD_SL"), ("ENGLISH", "BRICK230X76X10ENGLISH_SL"),
                      ("FLEMISH", "BRICK230X76X10FLEMISH_SL")):
        ok &= line_check(key, brick_pat, name, catalog)
    ok &= line_check("OCTAGONS", octagon_sl_pat(120.0), "OCTAGONS_SL_FIXED", catalog, width=120)
    ok &= line_check("OCTAGONS", octagon_sl_pat(200.0), "OCTAGONS_SL_FIXED", catalog, width=200)
    ok &= line_check("BASKETWEAVE", parquet_pat, None, catalog, width=101.6, length=609.6)
    print("ALL OK" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
