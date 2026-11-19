# -*- coding: utf-8 -*-
"""Colour conversion helpers.

Colours move between four representations:

* ``DB.Color`` (Revit)
* ``(r, g, b)`` tuple of ints 0-255
* ``"(r,g,b)"`` string
* ``"#RRGGBB"`` string

Every conversion has a reciprocal, e.g. ``colour_to_rgb_string`` and
``rgb_string_to_colour``. ``parse_colour`` accepts either string format.
The tuple-based functions need no Revit API.
"""

# # -------------- Standard Library Imports --------------
import re
from collections import namedtuple

# # ------------------ pyRevit Imports -------------------
from pyrevit import DB

RGB_STRING_RE = re.compile(r"^\s*\(?\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)?\s*$")
HEX_RE = re.compile(r"^\s*#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\s*$")

ColourInfo = namedtuple("ColourInfo", "rgb_string hex text_hex lrv")
EMPTY_COLOUR_INFO = ColourInfo("", "", "", "")


# ----------------------------------------------------------------------
# (r, g, b) tuples
# ----------------------------------------------------------------------
def rgb_to_rgb_string(rgb):
    """(255, 128, 0) -> "(255,128,0)"."""
    return "({0},{1},{2})".format(*rgb)


def rgb_string_to_rgb(text):
    """Reciprocal of rgb_to_rgb_string. Returns None if not parseable."""
    match = RGB_STRING_RE.match(str(text)) if text else None
    if not match:
        return None
    rgb = tuple(int(g) for g in match.groups())
    return rgb if all(0 <= c <= 255 for c in rgb) else None


def rgb_to_hex(rgb):
    """(255, 128, 0) -> "#FF8000"."""
    return "#{0:02X}{1:02X}{2:02X}".format(*rgb)


def hex_to_rgb(text):
    """Reciprocal of rgb_to_hex. Accepts 3 or 6 digits, # optional."""
    match = HEX_RE.match(str(text)) if text else None
    if not match:
        return None
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))


def parse_rgb(text):
    """Parse "(r,g,b)" or "#RRGGBB" text to an (r, g, b) tuple, else None."""
    return rgb_string_to_rgb(text) or hex_to_rgb(text)


def rgb_to_lrv(rgb):
    """Light reflectance value (0-1) from sRGB, using relative luminance."""

    def linearise(c):
        c = c / 255.0
        if c <= 0.04045:
            return c / 12.92
        return ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linearise(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_rgb(rgb, threshold=0.4):
    """White for dark colours, black for light ones."""
    return (255, 255, 255) if rgb_to_lrv(rgb) < threshold else (0, 0, 0)


# ----------------------------------------------------------------------
# DB.Color
# ----------------------------------------------------------------------
def colour_to_rgb(colour):
    """DB.Color -> (r, g, b); None if colour is None/invalid."""
    if colour is None or not colour.IsValid:
        return None
    return (int(colour.Red), int(colour.Green), int(colour.Blue))


def rgb_to_colour(rgb):
    """(r, g, b) -> DB.Color. Reciprocal of colour_to_rgb."""
    return DB.Color(*rgb)


def colour_to_rgb_string(colour):
    """DB.Color -> "(r,g,b)"; "" if no colour."""
    rgb = colour_to_rgb(colour)
    return rgb_to_rgb_string(rgb) if rgb else ""


def rgb_string_to_colour(text):
    """"(r,g,b)" -> DB.Color; None if not parseable."""
    rgb = rgb_string_to_rgb(text)
    return rgb_to_colour(rgb) if rgb else None


def colour_to_hex(colour):
    """DB.Color -> "#RRGGBB"; "" if no colour."""
    rgb = colour_to_rgb(colour)
    return rgb_to_hex(rgb) if rgb else ""


def hex_to_colour(text):
    """"#RRGGBB" -> DB.Color; None if not parseable."""
    rgb = hex_to_rgb(text)
    return rgb_to_colour(rgb) if rgb else None


def colour_to_lrv(colour):
    """DB.Color -> light reflectance value (0-1); None if no colour."""
    rgb = colour_to_rgb(colour)
    return rgb_to_lrv(rgb) if rgb else None


def parse_colour(text):
    """Either string format -> DB.Color; None if not parseable."""
    rgb = parse_rgb(text)
    return rgb_to_colour(rgb) if rgb else None


def describe_colour(colour):
    """All the string forms of a colour in one ColourInfo.

    text_hex is a legible text colour (black/white) to put on top of it.
    """
    rgb = colour_to_rgb(colour)
    if not rgb:
        return EMPTY_COLOUR_INFO
    return ColourInfo(
        rgb_to_rgb_string(rgb),
        rgb_to_hex(rgb),
        rgb_to_hex(contrast_rgb(rgb)),
        rgb_to_lrv(rgb),
    )
