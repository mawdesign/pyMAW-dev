# -*- coding: utf-8 -*-
"""Export Materials To Excel."""

# # -------------- Standard Library Imports --------------
import traceback

# # ------------------ pyRevit Imports -------------------
from pyrevit import forms
from pyrevit import revit
from pyrevit import DB

# # ------------------- module imports -------------------
import revitcolour
import revitexcel
import revitmaterials
import revitmaterialconfig

xlsxwriter = revitexcel.xlsxwriter

# Pattern + colour column pairs: (label, pattern property, colour property)
PATTERN_FIELDS = [
    ("Surface FG", "SurfaceForegroundPatternId", "SurfaceForegroundPatternColor"),
    ("Surface BG", "SurfaceBackgroundPatternId", "SurfaceBackgroundPatternColor"),
    ("Cut FG", "CutForegroundPatternId", "CutForegroundPatternColor"),
    ("Cut BG", "CutBackgroundPatternId", "CutBackgroundPatternColor"),
]

# Colour columns take two cells: the "(r,g,b)" text and a "#RRGGBB" swatch.
# Blank headers keep the swatch column unlabelled; the importer ignores them.
HEADERS = (
    ["Material Name", "Class", "Description", "Keynote", "Comments"]
    + ["Shading Colour", "", "LRV", "Transparency"]
    + [
        h
        for label, _, _ in PATTERN_FIELDS
        for h in ("{} Pattern".format(label), "{} Colour".format(label), "")
    ]
    + ["Appearance Asset", "Count", "Area", "Volume"]
)

BITMAP_HEADERS = [
    "Material Name",
    "Property",
    "Image Path",
    "Resolved Path",
    "Method",
    "Search Time (ms)",
]


def write_colour(ws, row, col, colour, formats):
    """Write "(r,g,b)" at col and a filled hex swatch at col + 1."""
    info = revitcolour.describe_colour(colour)
    ws.write(row, col, info.rgb_string)
    if info.hex:
        ws.write(row, col + 1, info.hex, formats.get(info.hex, info.text_hex))
    else:
        ws.write(row, col + 1, "")
    return info


def write_material(ws, row, doc, mat, formats, styles):
    """Write one material to a row of the Materials sheet."""
    bip = DB.BuiltInParameter
    ws.write(row, 0, mat.Name)
    ws.write(row, 1, mat.MaterialClass)
    ws.write(row, 2, revitmaterials.get_material_text(mat, bip.ALL_MODEL_DESCRIPTION))
    ws.write(row, 3, revitmaterials.get_material_text(mat, bip.KEYNOTE_PARAM))
    ws.write(
        row, 4, revitmaterials.get_material_text(mat, bip.ALL_MODEL_INSTANCE_COMMENTS)
    )

    info = write_colour(ws, row, 5, mat.Color, formats)
    ws.write(row, 7, info.lrv, styles["pct"])
    ws.write(row, 8, revitmaterials.get_transparency(mat), styles["pct"])

    col = 9
    for _, pattern_prop, colour_prop in PATTERN_FIELDS:
        pattern_name = revitmaterials.get_pattern_name(doc, getattr(mat, pattern_prop))
        if pattern_name == revitmaterials.NO_PATTERN:
            ws.write(row, col, pattern_name, styles["none"])
        else:
            ws.write(row, col, pattern_name)
        write_colour(ws, row, col + 1, getattr(mat, colour_prop), formats)
        col += 3

    ws.write(row, col, revitmaterials.get_asset(doc, mat)["name"])
    count, area, volume = revitmaterials.get_material_usage(mat)
    ws.write(row, col + 1, count)
    ws.write(row, col + 2, round(area, 1))
    ws.write(row, col + 3, round(volume, 2))


def write_materials_sheet(workbook, doc, materials, styles):
    """Write the Materials sheet. Returns (rows written, bitmap path records)."""
    ws = workbook.add_worksheet("Materials")
    formats = revitexcel.ColourFormats(workbook)
    texture_paths = revitmaterials.get_material_search_paths()
    fallback_roots = revitmaterialconfig.get_texture_fallback_paths()

    for col, header in enumerate(HEADERS):
        ws.write(0, col, header, styles["header"])

    row = 1
    bitmaps = []
    for mat in materials:
        try:
            write_material(ws, row, doc, mat, formats, styles)
            for path_data in revitmaterials.get_material_texture_paths(
                mat, doc, texture_paths=texture_paths, fallback_roots=fallback_roots
            ):
                bitmaps.append(path_data)
            row += 1
        except Exception as ex:
            print("Failed on material: {} | {}".format(mat.Name, ex))

    ws.autofilter(0, 0, row - 1, len(HEADERS) - 1)

    for col in range(len(HEADERS)):
        ws.set_column(col, col, 25)
    ws.set_column(0, 0, 50)
    for col in [5, 10, 13, 16, 19]:
        ws.set_column(col, col, 15)
        ws.set_column(col + 1, col + 1, 10)
    for col in [7, 8, 22, 23, 24]:
        ws.set_column(col, col, 10)

    return row - 1, bitmaps


def write_bitmaps_sheet(workbook, bitmaps, styles):
    """Write the Bitmap Paths sheet."""
    wm = workbook.add_worksheet("Bitmap Paths")

    for col, header in enumerate(BITMAP_HEADERS):
        wm.write(0, col, header, styles["header"])

    for row, item in enumerate(bitmaps, 1):
        wm.write(row, 0, item["material_name"])
        wm.write(row, 1, item["usage"])
        wm.write(row, 2, item["path"])
        if item["resolved_path"] == "<not found>":
            wm.write(row, 3, item["resolved_path"], styles["none"])
        else:
            wm.write(row, 3, item["resolved_path"])
        wm.write(row, 4, item["method"], styles["error"] if item["method"] == "Missing" else None)
        wm.write(row, 5, item["time"])

    wm.set_column(0, 1, 50)
    wm.set_column(2, 3, 100)
    wm.set_column(4, 5, 25)


def export_materials_to_excel():
    doc = revit.doc

    output_file = forms.save_file(
        file_ext="xlsx", default_name="Revit_Materials.xlsx", title="Save Material List"
    )

    if not output_file:
        forms.alert("No output file selected", title="No Output File", warn_icon=True)
        return

    materials = revitmaterials.get_materials(doc)
    revitmaterials.build_usage_cache(doc)

    try:
        workbook = xlsxwriter.Workbook(output_file)
        styles = {
            "header": workbook.add_format(
                {"bold": True, "bg_color": "#C5D9F1", "bottom": 1}
            ),
            "none": workbook.add_format({"font_color": "#C0C0C0"}),
            "error": workbook.add_format(
                {"font_color": "#9C0006", "bg_color": "#FFC7CE"}
            ),
            "pct": workbook.add_format({"num_format": 9}),  # 0%
        }

        count, bitmaps = write_materials_sheet(workbook, doc, materials, styles)
        write_bitmaps_sheet(workbook, bitmaps, styles)
        workbook.close()

        forms.alert(
            "Exported {} materials to {}".format(count, output_file),
            title="Export Complete",
        )

    except Exception as e:
        forms.alert(
            "Failed to save the Excel file. Please ensure the file is not currently open."
            "\n\nError: {}".format(e),
            title="Export Failed",
            warn_icon=True,
        )


if __name__ == "__main__":
    try:
        export_materials_to_excel()
    except Exception:
        print(traceback.format_exc())
