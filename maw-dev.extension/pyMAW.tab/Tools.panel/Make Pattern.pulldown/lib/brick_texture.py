# -*- coding: utf-8 -*-
"""Texture settings and rendering for the brick / tile pattern tools.

Glue between the pattern dialogs and the baked-texture composer:
  TextureSettings   what the user picks in the texture editor (stored in the pyRevit config)
  cell_pattern()    cell outlines for a brickpats.yaml entry at the user's dimensions
  render_bump()     the grey bump atlas (IronPython, System.Drawing)
  render_colour()   the same atlas shown on the brick and mortar colours
  to_wpf_image()    System.Drawing.Bitmap -> WPF image source
"""
from __future__ import division

import pattern_cells
import texture_atlas

MM_PER_FOOT = 304.8

# key matches the baked sheet names in lib/textures; level = grey of an undisturbed face
MATERIALS = [
    ("brick", "Clay brick"),
    ("concrete", "Concrete / precast"),
    ("block", "Concrete block (vertical drag)"),
]
FACE_LEVEL = {"brick": 0.62, "concrete": 0.66, "block": 0.66}

DEFAULT_BRICK_HEX = "#91412F"
DEFAULT_MORTAR_HEX = "#ECECEC"


def parse_hex(text):
    """'#RRGGBB' or 'RRGGBB' -> (r, g, b) as 0-1 floats, or None if it is not a colour."""
    text = (text or "").strip().lstrip("#")
    if len(text) == 8:
        text = text[2:]
    if len(text) != 6:
        return None
    try:
        return tuple(int(text[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return None


def normal_hex(text, default):
    """'abc123' / '#ABC123' / '#FFABC123' -> '#ABC123'; default when invalid."""
    return "#" + text.strip().lstrip("#")[-6:].upper() if parse_hex(text) else default


class TextureSettings(object):
    """Everything the texture editor changes. Colours are '#RRGGBB' strings."""

    def __init__(self):
        self.material = "brick"
        self.pits = 2
        self.scratch = 2
        self.joint_depth = 0.2      # 0 = joint flush with the face, 1 = black (deepest)
        self.seed = 1
        self.relief = 0.2           # strength of the preview lighting only; not saved in the bump map
        self.brick_hex = DEFAULT_BRICK_HEX
        self.mortar_hex = DEFAULT_MORTAR_HEX

    def copy(self):
        other = TextureSettings()
        other.__dict__.update(self.__dict__)
        return other

    @property
    def joint_level(self):
        return FACE_LEVEL[self.material] * (1.0 - self.joint_depth)

    @classmethod
    def load(cls, config):
        """Read from a pyRevit config section (BrickColor / MortarColor are the older option names)."""
        s = cls()

        def get(name, default, cast):
            try:
                return cast(config.get_option(name, default))
            except (TypeError, ValueError):
                return default

        material = get("TexMaterial", s.material, str)
        s.material = material if material in FACE_LEVEL else s.material
        s.pits = min(3, max(0, get("TexPits", s.pits, int)))
        s.scratch = min(3, max(0, get("TexScratch", s.scratch, int)))
        s.joint_depth = min(1.0, max(0.0, get("TexJointDepth", s.joint_depth, float)))
        s.seed = get("TexSeed", s.seed, int)
        s.relief = min(1.0, max(0.0, get("TexRelief", s.relief, float)))
        s.brick_hex = normal_hex(get("BrickColor", s.brick_hex, str), s.brick_hex)
        s.mortar_hex = normal_hex(get("MortarColor", s.mortar_hex, str), s.mortar_hex)
        return s

    def save(self, config):
        config.set_option("TexMaterial", self.material)
        config.set_option("TexPits", str(self.pits))
        config.set_option("TexScratch", str(self.scratch))
        config.set_option("TexJointDepth", "{:g}".format(self.joint_depth))
        config.set_option("TexSeed", str(self.seed))
        config.set_option("TexRelief", "{:g}".format(self.relief))
        config.set_option("BrickColor", self.brick_hex)
        config.set_option("MortarColor", self.mortar_hex)


# ------------------------------------------------------------------ cells
def cells_key(entry_key, entry):
    """Catalog key in pattern_cells.yaml for a brickpats.yaml entry: its `cells:` value, else its
    own key without the _SL (single line) suffix."""
    key = entry.get("cells") or entry_key
    if key.endswith("_SL") and key not in pattern_cells.load_catalog():
        key = key[:-3]
    return key


def has_cells(entry_key, entry):
    return cells_key(entry_key, entry) in pattern_cells.load_catalog()


def cell_pattern(entry_key, entry, width_mm, height_mm, mortar_mm):
    """pattern_cells.Pattern for a brickpats.yaml entry at the given dimensions (all mm).

    The entry may add `cells_args:` to feed other values to the cell catalog, each an
    expression in {width} {height} {mortar}, for example for a basketweave of 6-board blocks:
        cells: BASKETWEAVE
        cells_args: {width: "{height}", length: "{width}"}
    """
    dims = {"width": width_mm, "height": height_mm, "mortar": mortar_mm}
    args = dict(dims)
    for name, expr in (entry.get("cells_args") or {}).items():
        args[name] = pattern_cells.evaluate(expr, dims)
    return pattern_cells.build_pattern(cells_key(entry_key, entry), **args)


# ------------------------------------------------------------------ rendering
def _plan(pattern, settings, apply_texture, mortar_mm, ppm, max_px, min_size_mm):
    flat = None if apply_texture else FACE_LEVEL[settings.material]
    return texture_atlas.plan_atlas(
        pattern,
        settings.material,
        pit_level=settings.pits if apply_texture else 0,
        scratch_level=settings.scratch if apply_texture else 0,
        ppm=ppm,
        max_px=max_px,
        seed=settings.seed,
        mortar=mortar_mm,
        min_size_mm=min_size_mm,
        flat_level=flat,
    )


def make_plan(pattern, settings, apply_texture, mortar_mm, ppm=2.0, max_px=4096, min_size_mm=800.0):
    """AtlasPlan for the pattern. apply_texture False gives plain faces (joints only)."""
    return _plan(pattern, settings, apply_texture, mortar_mm, ppm, max_px, min_size_mm)


def render_bump(plan, settings, outline_px=0):
    """Grey bump atlas (System.Drawing.Bitmap) for the plan."""
    return texture_atlas.render_atlas(plan, joint_level=settings.joint_level, outline_px=outline_px)


def render_colour(plan, bump, settings):
    """The bump atlas shown on the brick and mortar colours (System.Drawing.Bitmap)."""
    brick = parse_hex(settings.brick_hex) or parse_hex(DEFAULT_BRICK_HEX)
    mortar = parse_hex(settings.mortar_hex) or parse_hex(DEFAULT_MORTAR_HEX)
    return texture_atlas.render_colour_preview(plan, bump, brick, mortar, settings.relief)


def render_thumbnail(pattern, settings, apply_texture, mortar_mm):
    """Small coloured, lit view of one atlas, quick enough to refresh as the dimensions change."""
    plan = _plan(pattern, settings, apply_texture, mortar_mm, 1.0, 500, 400.0)
    bump = render_bump(plan, settings)
    try:
        return render_colour(plan, bump, settings)
    finally:
        bump.Dispose()


def tile_2x2(bmp):
    """A new bitmap holding bmp tiled 2 x 2."""
    import clr

    clr.AddReference("System.Drawing")
    from System.Drawing import Bitmap, Graphics
    from System.Drawing.Imaging import PixelFormat

    out = Bitmap(bmp.Width * 2, bmp.Height * 2, PixelFormat.Format32bppArgb)
    g = Graphics.FromImage(out)
    for ty in (0, 1):
        for tx in (0, 1):
            g.DrawImage(bmp, tx * bmp.Width, ty * bmp.Height, bmp.Width, bmp.Height)
    g.Dispose()
    return out


def to_wpf_image(bmp):
    """System.Drawing.Bitmap -> frozen WPF BitmapImage."""
    import clr

    clr.AddReference("PresentationCore")
    from System.IO import MemoryStream, SeekOrigin
    from System.Windows.Media.Imaging import BitmapCacheOption, BitmapImage
    from System.Drawing.Imaging import ImageFormat

    ms = MemoryStream()
    bmp.Save(ms, ImageFormat.Png)
    ms.Seek(0, SeekOrigin.Begin)
    image = BitmapImage()
    image.BeginInit()
    image.StreamSource = ms
    image.CacheOption = BitmapCacheOption.OnLoad
    image.EndInit()
    image.Freeze()
    ms.Close()
    return image
