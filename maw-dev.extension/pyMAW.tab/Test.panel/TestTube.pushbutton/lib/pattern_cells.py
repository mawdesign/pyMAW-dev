# -*- coding: utf-8 -*-
"""Evaluate pattern_cells.yaml into polygons for a given set of dimensions.

Pure Python, runs in IronPython 2.7 and CPython 3 (no .NET, no numpy), so the
cell maths can be tested outside Revit.
"""
from __future__ import division

import math
import os

_EVAL_NAMES = {"sqrt": math.sqrt, "pi": math.pi, "round": round, "min": min, "max": max}
_DEFAULT_CATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pattern_cells.yaml")


class Cell(object):
    """One unit outline. points are world mm; angle is the texture direction in degrees."""

    def __init__(self, points, angle):
        self.points = points
        self.angle = angle

    def bounds(self):
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return min(xs), min(ys), max(xs), max(ys)

    def moved(self, dx, dy):
        return Cell([(x + dx, y + dy) for x, y in self.points], self.angle)


class Pattern(object):
    def __init__(self, name, repeat_w, repeat_h, cells):
        self.name = name
        self.repeat_w = repeat_w
        self.repeat_h = repeat_h
        self.cells = cells

    def wrapped_copies(self, cell):
        """Yield cell translated by whole repeats so every copy touching [0,w]x[0,h] is drawn."""
        bx0, by0, bx1, by1 = cell.bounds()
        w, h = self.repeat_w, self.repeat_h
        kx0 = int(math.floor(-bx1 / w)) + 1
        kx1 = int(math.ceil((w - bx0) / w)) - 1
        ky0 = int(math.floor(-by1 / h)) + 1
        ky1 = int(math.ceil((h - by0) / h)) - 1
        for ky in range(ky0, ky1 + 1):
            for kx in range(kx0, kx1 + 1):
                yield cell.moved(kx * w, ky * h)


def tiled_pattern(pattern, nx, ny):
    """The pattern repeated nx by ny times as one larger pattern (every cell unique)."""
    cells = []
    for j in range(ny):
        for i in range(nx):
            cells.extend(c.moved(i * pattern.repeat_w, j * pattern.repeat_h) for c in pattern.cells)
    return Pattern(pattern.name, pattern.repeat_w * nx, pattern.repeat_h * ny, cells)


def repeats_for_size(pattern, min_w_mm=800.0, min_h_mm=800.0):
    """Smallest whole number of repeats (nx, ny) giving at least the requested size."""
    return (max(1, int(math.ceil(min_w_mm / pattern.repeat_w - 1e-9))),
            max(1, int(math.ceil(min_h_mm / pattern.repeat_h - 1e-9))))


def load_catalog(path=None):
    path = path or _DEFAULT_CATALOG
    try:
        from pyrevit.coreutils import yaml as pyr_yaml

        return pyr_yaml.load_as_dict(path)
    except ImportError:
        import yaml

        with open(path) as fh:
            return yaml.safe_load(fh)


def _num(value, params):
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).format(**params)
    return float(eval(text, {"__builtins__": {}}, _EVAL_NAMES))


def build_pattern(key, width=None, height=None, mortar=None, catalog=None, **extra):
    """Evaluate the catalog entry `key` with the given dimensions (mm)."""
    catalog = catalog or load_catalog()
    spec = catalog[key]
    params = dict((k, float(v)) for k, v in spec.get("params", {}).items())
    for k, v in (("width", width), ("height", height), ("mortar", mortar)):
        if v is not None:
            params[k] = float(v)
    for k, v in extra.items():
        params[k] = float(v)

    rotate = float(spec.get("rotate", 0.0))
    cos_r = math.cos(math.radians(rotate))
    sin_r = math.sin(math.radians(rotate))

    cells = []
    for entry in spec["cells"]:
        count = int(_num(entry["count"], params)) if "count" in entry else 1
        for i in range(count):
            p = dict(params)
            p["i"] = float(i)
            if "rect" in entry:
                x, y, w, h = [_num(v, p) for v in entry["rect"]]
                pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
            else:
                pts = [(_num(px, p), _num(py, p)) for px, py in entry["poly"]]
            if rotate:
                pts = [(x * cos_r - y * sin_r, x * sin_r + y * cos_r) for x, y in pts]
            cells.append(Cell(pts, float(entry.get("angle", 0.0)) + rotate))

    rw, rh = [_num(v, params) for v in spec["repeat"]]
    return Pattern(spec.get("name", key), rw, rh, cells)
