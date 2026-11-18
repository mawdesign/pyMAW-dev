# -*- coding: utf-8 -*-
"""Colour Palette Creator.

Places filled regions with color names and configurable sizes.
"""

# # -------------- Standard Library Imports --------------
import System.Drawing

# # ------------------ pyRevit Imports -------------------
from pyrevit import revit
from pyrevit import DB

# --- CONFIGURATION ---
BOX_SIZE_MM = 20  # Set your box size in mm here
SPACING_MM = 20  # Set spacing between boxes in mm (center to center)
TEXT_OFFSET_MM = 10  # Offset for the text label from the box

# Data based on the palette
COLOR_PALETTE = [
    (
        "1. Cool White RGBW(78%, 86%, 100%, 100%)\nHigh kelvin (6500K+) equivalent",
        "#E2EDFF",
    ),
    ("2. White RGBW(50%, 50%, 50%, 100%)\nNeutral daylight (5000K)", "#FFFFFF"),
    ("3. Warm White RGBW(100%, 82%, 62%, 75%)\nIncandescent feel (2700K)", "#FFE4C7"),
    (
        "4. Candle Light RGBW(100%, 58%, 16%, 50%)\nDeep warm amber-white (1900K)",
        "#FFB770",
    ),
    ("5. Amber RGBW(100%, 47%, 0%, 20%)\nPure saturated amber", "#FF8E2A"),
    ("6. Yellow RGBW(100%, 100%, 0%, 50%)\nStandard bright yellow", "#FFFF55"),
    ("7.  RGBW(100%, 50%, 0%, 30%)", "#FF9C3A"),
    ("8. Red RGBW(100%, 0%, 0%, 10%)\nPure red", "#FE1717"),
    ("9. Pink RGBW(100%, 35%, 35%, 35%)\nSoft pastel pink", "#FE8484"),
    ("10. Red RGBW(100%, 30%, 50%, 20%)", "#FF6A94"),
    ("11.  RGBW(100%, 15%, 55%, 10%)", "#FE3996"),
    ("12. Magenta RGBW(100%, 10%, 100%, 0%)\nVibrant magenta", "#FF19FF"),
    ("13. Violet RGBW(75%, 0%, 100%, 0%)\nStandard violet", "#BF00FF"),
    ("14. Indego RGBW(40%, 0%, 100%, 10%)\nDeep blue-purple", "#7317FE"),
    ("15. Blue RGBW(0%, 0%, 100%, 10%)\nPure blue", "#1717FE"),
    ("16.  RGBW(0%, 50%, 100%, 12%)", "#1B8DFF"),
    ("17. Cyan RGBW(0%, 100%, 100%, 15%)\nElectric cyan", "#21FFFF"),
    ("18.  RGBW(8%, 100%, 55%, 12%)", "#2DFF98"),
    ("19. Green RGBW(15%, 100%, 10%, 10%)\nPure green", "#39FE2E"),
    ("20. Leaf Green RGBW(25%, 100%, 30%, 10%)\nNatural foliage green", "#51FE5C"),
]


def mm_to_ft(mm):
    """Converts millimeters to decimal feet for Revit internal units."""
    return mm / 304.8


def hex_to_revit_color(hex_string):
    """Converts a hex string (e.g., 'FF0000') to a Revit DB.Color object."""
    sys_color = System.Drawing.ColorTranslator.FromHtml(hex_string)
    return DB.Color(sys_color.R, sys_color.G, sys_color.B)


def get_invisible_line_style_id(doc):
    """Finds the ID of the 'Invisible lines' graphic style."""
    lines_cat = doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Lines)
    sub_cats = lines_cat.SubCategories
    for sub_cat in sub_cats:
        if "<Invisible" in sub_cat.Name:
            return sub_cat.Id
    return None


def colour_palette_creator(
    doc, view, color_name, hex_val, offset_x_ft, size_ft, invisible_style_id
):
    """Creates a square filled region and a text label."""
    # 1. Define the square geometry
    p1 = DB.XYZ(offset_x_ft, 0, 0)
    p2 = DB.XYZ(offset_x_ft + size_ft, 0, 0)
    p3 = DB.XYZ(offset_x_ft + size_ft, size_ft, 0)
    p4 = DB.XYZ(offset_x_ft, size_ft, 0)

    curve_loop = DB.CurveLoop()
    curve_loop.Append(DB.Line.CreateBound(p1, p2))
    curve_loop.Append(DB.Line.CreateBound(p2, p3))
    curve_loop.Append(DB.Line.CreateBound(p3, p4))
    curve_loop.Append(DB.Line.CreateBound(p4, p1))

    # 2. Find Types
    # Get a default Filled Region Type
    fr_type = (
        DB.FilteredElementCollector(doc).OfClass(DB.FilledRegionType).FirstElement()
    )
    # Get a Solid Fill Pattern
    fill_patterns = DB.FilteredElementCollector(doc).OfClass(DB.FillPatternElement)
    solid_pattern = next(
        (fp for fp in fill_patterns if fp.GetFillPattern().IsSolidFill), None
    )
    # Get a Text Note Type
    text_type = DB.FilteredElementCollector(doc).OfClass(DB.TextNoteType).FirstElement()

    # 3. Create the Filled Region
    region = DB.FilledRegion.Create(doc, fr_type.Id, view.Id, [curve_loop])

    # 4. Set Line Style to Invisible
    if invisible_style_id:
        region.SetLineStyleId(invisible_style_id)

    # 5. Apply Overrides
    og_settings = DB.OverrideGraphicSettings()
    revit_color = hex_to_revit_color(hex_val)

    if solid_pattern:
        og_settings.SetSurfaceForegroundPatternId(solid_pattern.Id)
        og_settings.SetSurfaceForegroundPatternColor(revit_color)

    view.SetElementOverrides(region.Id, og_settings)

    # 6. Create Text Label
    # Place text slightly above the box
    text_pos = DB.XYZ(offset_x_ft, size_ft + mm_to_ft(TEXT_OFFSET_MM), 0)
    DB.TextNote.Create(doc, view.Id, text_pos, color_name, text_type.Id)


if __name__ == "__main__":
    # Main Execution
    doc = revit.doc
    view = revit.active_view

    # Convert config to feet
    size_ft = mm_to_ft(BOX_SIZE_MM)
    spacing_ft = mm_to_ft(SPACING_MM)

    # Get the invisible line style once
    inv_id = get_invisible_line_style_id(doc)

    with revit.Transaction("Place Colored Regions with Labels"):
        for i, color_data in enumerate(COLOR_PALETTE):
            name, hex_code = color_data
            colour_palette_creator(
                doc, view, name, hex_code, i * spacing_ft, size_ft, inv_id
            )

    print(
        "Placed {0} regions with labels using a {1}mm box size.".format(
            len(COLOR_PALETTE), BOX_SIZE_MM
        )
    )
