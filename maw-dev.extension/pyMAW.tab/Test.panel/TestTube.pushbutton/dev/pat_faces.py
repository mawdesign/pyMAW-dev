# -*- coding: utf-8 -*-
"""Dev tool (CPython 3 + shapely): turn AutoCAD .pat line families into faces.

Used to verify hand-written cell outlines against the real fill pattern lines.
Not shipped to Revit (needs shapely).
"""
import math
import re

import shapely
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union

GRID = 1e-3  # mm; snaps nodes so shapely can node the crossings


def parse_pat_lines(text, name=None):
    """Return [(angle, x, y, dx, dy, [dashes])] for one pattern in .pat text."""
    current = None
    lines = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith(";"):
            continue
        if s.startswith("*"):
            current = s[1:].split(",")[0].strip()
            continue
        if name is not None and current != name:
            continue
        vals = [float(v) for v in s.split(",") if v.strip()]
        lines.append((vals[0], vals[1], vals[2], vals[3], vals[4], vals[5:]))
    return lines


def family_segments(fam, window, max_lines=400):
    """Yield LineStrings for one line family clipped to window = (xmin,ymin,xmax,ymax)."""
    ang, x0, y0, dx, dy, dashes = fam
    th = math.radians(ang)
    u = (math.cos(th), math.sin(th))
    v = (-math.sin(th), math.cos(th))
    xmin, ymin, xmax, ymax = window
    corners = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
    # perpendicular extent of the window relative to the family origin
    perp = [(cx - x0) * v[0] + (cy - y0) * v[1] for cx, cy in corners]
    if abs(dy) < 1e-9:
        n_range = [0]
    else:
        # line n has perpendicular offset n*dy + n*dx*0 (shift is along the line)
        lo, hi = min(perp), max(perp)
        n0, n1 = sorted((lo / dy, hi / dy))
        n_range = range(int(math.floor(n0)) - 1, int(math.ceil(n1)) + 2)
    out = []
    diag = math.hypot(xmax - xmin, ymax - ymin)
    for n in list(n_range)[:max_lines]:
        ox = x0 + n * (dx * u[0] + dy * v[0])
        oy = y0 + n * (dx * u[1] + dy * v[1])
        # along-line extent of window
        along = [(cx - ox) * u[0] + (cy - oy) * u[1] for cx, cy in corners]
        t_lo, t_hi = min(along) - 1, max(along) + 1
        if not dashes:
            out.append(LineString([(ox + t_lo * u[0], oy + t_lo * u[1]),
                                   (ox + t_hi * u[0], oy + t_hi * u[1])]))
            continue
        period = sum(abs(d) for d in dashes)
        k0 = int(math.floor(t_lo / period)) - 1
        t = k0 * period
        while t < t_hi:
            pos = t
            for d in dashes:
                if d > 0:
                    a, b = pos, pos + d
                    if b > t_lo and a < t_hi:
                        out.append(LineString([(ox + a * u[0], oy + a * u[1]),
                                               (ox + b * u[0], oy + b * u[1])]))
                pos += abs(d)
            t += period
    return out


def pat_faces(fams, window):
    segs = []
    for f in fams:
        segs.extend(family_segments(f, window))
    merged = unary_union([shapely.set_precision(s, GRID) for s in segs])
    merged = shapely.set_precision(merged, GRID)
    return list(polygonize(merged))


def inside(poly, window, margin):
    xmin, ymin, xmax, ymax = window
    bx0, by0, bx1, by1 = poly.bounds
    return (bx0 > xmin + margin and by0 > ymin + margin
            and bx1 < xmax - margin and by1 < ymax - margin)


if __name__ == "__main__":
    import sys
    text = open(sys.argv[1]).read()
    name = sys.argv[2] if len(sys.argv) > 2 else None
    fams = parse_pat_lines(text, name)
    win = (-1500, -1500, 1500, 1500)
    faces = [f for f in pat_faces(fams, win) if inside(f, win, 50)]
    print("faces fully inside window:", len(faces))
    shapes = {}
    for f in faces:
        key = (round(f.area, 1), len(f.exterior.coords) - 1)
        shapes.setdefault(key, []).append(f)
    for (a, n), fs in sorted(shapes.items()):
        print("area %.1f  verts %d  count %d  e.g. bounds %s" % (a, n, len(fs), [round(b, 1) for b in fs[0].bounds]))
