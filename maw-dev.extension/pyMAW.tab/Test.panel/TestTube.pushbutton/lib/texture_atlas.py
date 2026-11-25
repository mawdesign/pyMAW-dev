# -*- coding: utf-8 -*-
"""Compose a seamless bump-map atlas for a fill pattern from baked texture sheets.

Two halves:
  plan_atlas()  pure Python (IronPython 2.7 / CPython): decides pixel size, cell
                outlines in pixels, and the random texture offset/flip per cell
                and layer. No imaging, so it can be tested anywhere.
  render_atlas() IronPython + System.Drawing: fills each cell polygon with a
                wrap-around TextureBrush of the baked sheets (base, pits,
                scratches), so detail stays pixel-sharp and nothing is scaled
                unless the atlas had to be capped at max_px.
"""
from __future__ import division

import json
import math
import os
import random

TEXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "textures")


class LayerJob(object):
    def __init__(self, name, ox, oy, flip, rot180):
        self.name = name        # sheet file stem, e.g. "brick_pits_2"
        self.ox = ox            # texture offset in atlas pixels
        self.oy = oy
        self.flip = flip        # 1 or -1 (mirror across the texture's long axis)
        self.rot180 = rot180    # 0 or 180


class CellJob(object):
    def __init__(self, points_px, angle_deg, layers):
        self.points_px = points_px      # [(x, y)] atlas pixels, y down
        self.angle_deg = angle_deg      # device rotation of the texture (clockwise positive)
        self.layers = layers            # [LayerJob], drawn in order


class AtlasPlan(object):
    def __init__(self, width_px, height_px, ppm, sheet_scale, jobs, fill_background_with_base, base_name, edge_joint_px=0.0):
        self.width_px = width_px
        self.height_px = height_px
        self.ppm = ppm                          # atlas pixels per mm actually used
        self.sheet_scale = sheet_scale          # atlas px per sheet px (1.0 = no resampling)
        self.jobs = jobs
        self.repeats = None
        self.fill_background_with_base = fill_background_with_base
        self.base_name = base_name
        self.edge_joint_px = edge_joint_px      # joint width drawn on cell edges (touching cells only)

    @property
    def size_mm(self):
        """Real-world size to enter as the Revit bump map width/height (mm)."""
        return self.width_px / self.ppm, self.height_px / self.ppm


def load_sheet_info(texture_dir=None):
    with open(os.path.join(texture_dir or TEXTURE_DIR, "textures.json")) as fh:
        return json.load(fh)


def plan_atlas(pattern, material, pit_level=2, scratch_level=2, ppm=2.0, max_px=4096, seed=1,
               mortar=0.0, sheet_ppm=2.0, sheet_px=2048, repeats=None, min_size_mm=800.0):
    """Lay out one atlas for `pattern` (pattern_cells.Pattern).

    repeats: (nx, ny) whole bond repeats in the atlas; default is the smallest
    number giving at least min_size_mm each way, so the texture does not visibly
    repeat. pit_level / scratch_level: 0 (none) to 3. ppm: atlas pixels per mm;
    reduced if the atlas would exceed max_px on a side.
    """
    from pattern_cells import repeats_for_size, tiled_pattern

    nx, ny = repeats or repeats_for_size(pattern, min_size_mm, min_size_mm)
    pattern = tiled_pattern(pattern, nx, ny)
    longest = max(pattern.repeat_w, pattern.repeat_h)
    if longest * ppm > max_px:
        ppm = max_px / longest
    w_px = int(round(pattern.repeat_w * ppm))
    h_px = int(round(pattern.repeat_h * ppm))
    scale = ppm / sheet_ppm
    tile = sheet_px * scale          # one sheet tile in atlas pixels (offsets are drawn in this range)

    # one random stream per layer kind, so changing the pit or scratch level (or
    # switching either off) never moves the base or the other layer
    kinds = ["base"]
    names = ["%s_base" % material]
    if pit_level:
        kinds.append("pits")
        names.append("%s_pits_%d" % (material, pit_level))
    if scratch_level:
        kinds.append("scratch")
        names.append("%s_scratch_%d" % (material, scratch_level))
    streams = dict((k, random.Random("%s/%s" % (seed, k))) for k in kinds)

    def px(point):
        return (point[0] * ppm, (pattern.repeat_h - point[1]) * ppm)

    jobs = []
    for cell in pattern.cells:
        base_layers = []
        for kind, n in zip(kinds, names):
            rng = streams[kind]
            base_layers.append(LayerJob(n, round(rng.uniform(0, tile)), round(rng.uniform(0, tile)), rng.choice((1, -1)), rng.choice((0, 180))))
        for copy in pattern.wrapped_copies(cell):
            # the texture is anchored to the cell, so a wrapped copy carries its displacement
            shift_x = (copy.points[0][0] - cell.points[0][0]) * ppm
            shift_y = -(copy.points[0][1] - cell.points[0][1]) * ppm
            layers = [LayerJob(l.name, round(l.ox + shift_x), round(l.oy + shift_y), l.flip, l.rot180) for l in base_layers]
            jobs.append(CellJob([px(p) for p in copy.points], -cell.angle, layers))
    edge = pattern.edge_joint
    plan = AtlasPlan(w_px, h_px, ppm, scale, jobs, edge or mortar <= 0, names[0], mortar * ppm if edge else 0.0)
    plan.repeats = (nx, ny)
    return plan


# --------------------------------------------------------------------- GDI+ renderer
def render_atlas(plan, joint_level=0.5, texture_dir=None, outline_px=0):
    """Return a System.Drawing.Bitmap (32bpp ARGB, opaque) for the plan. IronPython only.

    outline_px > 0 also draws every cell outline that wide in a dark line (preview aid only).
    """
    import clr

    clr.AddReference("System.Drawing")
    from System import Array
    from System.Drawing import Bitmap, Color, Graphics, GraphicsUnit, Pen, PointF, Rectangle, TextureBrush
    from System.Drawing.Drawing2D import CompositingMode, LineJoin, InterpolationMode, Matrix, PixelOffsetMode, SmoothingMode, WrapMode
    from System.Drawing.Imaging import PixelFormat

    texture_dir = texture_dir or TEXTURE_DIR
    sheets = {}

    def sheet(name):
        if name not in sheets:
            src = Bitmap(os.path.join(texture_dir, name + ".png"))
            argb = Bitmap(src.Width, src.Height, PixelFormat.Format32bppArgb)
            g2 = Graphics.FromImage(argb)
            g2.CompositingMode = CompositingMode.SourceCopy
            g2.DrawImage(src, Rectangle(0, 0, src.Width, src.Height), 0, 0, src.Width, src.Height, GraphicsUnit.Pixel)
            g2.Dispose()
            src.Dispose()
            sheets[name] = argb
        return sheets[name]

    brushes = {}  # one brush per sheet: creating a TextureBrush copies the whole image

    def brush_for(layer, angle):
        brush = brushes.get(layer.name)
        if brush is None:
            brush = brushes[layer.name] = TextureBrush(sheet(layer.name), WrapMode.Tile)
        m = Matrix()
        m.Translate(layer.ox, layer.oy)
        m.Rotate(angle + layer.rot180)
        m.Scale(plan.sheet_scale * layer.flip, plan.sheet_scale)
        brush.Transform = m
        return brush

    bmp = Bitmap(plan.width_px, plan.height_px, PixelFormat.Format32bppArgb)
    g = Graphics.FromImage(bmp)
    try:
        g.PixelOffsetMode = PixelOffsetMode.Half
        level = int(round(joint_level * 255))
        g.Clear(Color.FromArgb(255, level, level, level))
        g.SmoothingMode = getattr(SmoothingMode, "None")  # keyword in Python 3
        if plan.fill_background_with_base:
            bg = TextureBrush(sheet(plan.base_name), WrapMode.Tile)
            bm = Matrix()
            bm.Scale(plan.sheet_scale, plan.sheet_scale)
            bg.Transform = bm
            g.FillRectangle(bg, 0, 0, plan.width_px, plan.height_px)
            bg.Dispose()
        g.SmoothingMode = SmoothingMode.AntiAlias
        exact_scale = abs(plan.sheet_scale - 1.0) < 1e-9
        for job in plan.jobs:
            pts = Array[PointF]([PointF(x, y) for x, y in job.points_px])
            exact = exact_scale and (job.angle_deg % 90.0) == 0.0
            g.InterpolationMode = InterpolationMode.NearestNeighbor if exact else InterpolationMode.HighQualityBilinear
            for layer in job.layers:
                g.FillPolygon(brush_for(layer, job.angle_deg), pts)
        g.InterpolationMode = InterpolationMode.HighQualityBilinear
        passes = []
        if plan.edge_joint_px > 0:
            passes.append((plan.edge_joint_px, Color.FromArgb(255, level, level, level)))
        if outline_px > 0:
            passes.append((outline_px, Color.FromArgb(255, 40, 40, 40)))
        for width, color in passes:
            pen = Pen(color, width)
            pen.LineJoin = LineJoin.Miter
            for job in plan.jobs:
                g.DrawPolygon(pen, Array[PointF]([PointF(x, y) for x, y in job.points_px]))
            pen.Dispose()
    finally:
        g.Dispose()
        for b in brushes.values():
            b.Dispose()
        for s in sheets.values():
            s.Dispose()
    return bmp


# --------------------------------------------------------------------- colour preview
def shade_preview(bump, rgb, strength=0.4):
    """Approximate how the bump map looks on a surface of colour rgb (0-1 each). IronPython only.

    Not the Revit renderer: a relief shade lit from the top left, built from GDI+
    draws with colour matrices (no per-pixel loops). The result wraps at the edges,
    so tiling it shows the same seams as the bump map. Returns a new Bitmap.
    """
    import clr

    clr.AddReference("System.Drawing")
    from System import Array, Single
    from System.Drawing import Bitmap, Graphics, GraphicsUnit, Rectangle
    from System.Drawing.Drawing2D import CompositingMode, InterpolationMode, PixelOffsetMode
    from System.Drawing.Imaging import ColorMatrix, ImageAttributes, PixelFormat

    w, h = bump.Width, bump.Height

    def attrs(diag, offset=(0, 0, 0), alpha=1.0):
        rows = [[diag[0], 0, 0, 0, 0], [0, diag[1], 0, 0, 0], [0, 0, diag[2], 0, 0], [0, 0, 0, alpha, 0],
                [offset[0], offset[1], offset[2], 0, 1]]
        matrix = ColorMatrix(Array[Array[Single]]([Array[Single]([float(v) for v in row]) for row in rows]))
        ia = ImageAttributes()
        ia.SetColorMatrix(matrix)
        return ia

    def draw(g, image, ia, dx=0, dy=0):
        g.DrawImage(image, Rectangle(dx, dy, w, h), 0, 0, w, h, GraphicsUnit.Pixel, ia)

    def canvas():
        bmp = Bitmap(w, h, PixelFormat.Format32bppArgb)
        g = Graphics.FromImage(bmp)
        g.InterpolationMode = InterpolationMode.NearestNeighbor
        g.PixelOffsetMode = PixelOffsetMode.Half
        return bmp, g

    # d = 0.5 + 0.5 * (height - height shifted by one pixel down-right), wrapped
    d, g = canvas()
    g.CompositingMode = CompositingMode.SourceCopy
    draw(g, bump, attrs((1, 1, 1)))
    g.CompositingMode = CompositingMode.SourceOver
    inverted = attrs((-1, -1, -1), (1, 1, 1), 0.5)
    for dx, dy in ((1, 1), (1 - w, 1), (1, 1 - h), (1 - w, 1 - h)):
        draw(g, bump, inverted, dx, dy)
    g.Dispose()

    # e = 0.5 + k * (d - 0.5): stretch the relief
    k = 1.0 + 24.0 * strength
    e, g = canvas()
    g.CompositingMode = CompositingMode.SourceCopy
    draw(g, d, attrs((k, k, k), (0.5 * (1 - k),) * 3))
    # shade = 0.7 e + 0.3 height, so pits and joints also darken
    g.CompositingMode = CompositingMode.SourceOver
    draw(g, bump, attrs((1, 1, 1), alpha=0.3))
    g.Dispose()
    d.Dispose()

    # tint: flat areas (shade about 0.55) come out as the chosen colour
    gain = 1.0 / 0.55
    out, g = canvas()
    g.CompositingMode = CompositingMode.SourceCopy
    draw(g, e, attrs((rgb[0] * gain, rgb[1] * gain, rgb[2] * gain)))
    g.Dispose()
    e.Dispose()
    return out
