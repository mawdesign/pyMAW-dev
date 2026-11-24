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
    def __init__(self, width_px, height_px, ppm, sheet_scale, jobs, fill_background_with_base, base_name):
        self.width_px = width_px
        self.height_px = height_px
        self.ppm = ppm                          # atlas pixels per mm actually used
        self.sheet_scale = sheet_scale          # atlas px per sheet px (1.0 = no resampling)
        self.jobs = jobs
        self.repeats = None
        self.fill_background_with_base = fill_background_with_base
        self.base_name = base_name

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

    rng = random.Random(seed)
    names = [("%s_base" % material)]
    if pit_level:
        names.append("%s_pits_%d" % (material, pit_level))
    if scratch_level:
        names.append("%s_scratch_%d" % (material, scratch_level))

    def px(point):
        return (point[0] * ppm, (pattern.repeat_h - point[1]) * ppm)

    jobs = []
    for cell in pattern.cells:
        base_layers = [LayerJob(n, round(rng.uniform(0, tile)), round(rng.uniform(0, tile)), rng.choice((1, -1)), rng.choice((0, 180)))
                       for n in names]
        for copy in pattern.wrapped_copies(cell):
            # the texture is anchored to the cell, so a wrapped copy carries its displacement
            shift_x = (copy.points[0][0] - cell.points[0][0]) * ppm
            shift_y = -(copy.points[0][1] - cell.points[0][1]) * ppm
            layers = [LayerJob(l.name, round(l.ox + shift_x), round(l.oy + shift_y), l.flip, l.rot180) for l in base_layers]
            jobs.append(CellJob([px(p) for p in copy.points], -cell.angle, layers))
    plan = AtlasPlan(w_px, h_px, ppm, scale, jobs, mortar <= 0, names[0])
    plan.repeats = (nx, ny)
    return plan


# --------------------------------------------------------------------- GDI+ renderer
def render_atlas(plan, joint_level=0.5, texture_dir=None):
    """Return a System.Drawing.Bitmap (32bpp ARGB, opaque) for the plan. IronPython only."""
    import clr

    clr.AddReference("System.Drawing")
    from System import Array
    from System.Drawing import Bitmap, Color, Graphics, GraphicsUnit, PointF, Rectangle, TextureBrush
    from System.Drawing.Drawing2D import CompositingMode, InterpolationMode, Matrix, PixelOffsetMode, SmoothingMode, WrapMode
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
    finally:
        g.Dispose()
        for b in brushes.values():
            b.Dispose()
        for s in sheets.values():
            s.Dispose()
    return bmp
