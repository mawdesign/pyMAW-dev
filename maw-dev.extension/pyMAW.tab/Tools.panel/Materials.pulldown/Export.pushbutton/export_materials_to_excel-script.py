# -*- coding: utf-8 -*-
"""Export Materials To Excel."""

# # -------------- Standard Library Imports --------------
# import os
import traceback

# import timeit
from collections import defaultdict

# # ----------------- 3rd Party Imports ------------------
try:
    import xlsxwriter
except ImportError:
    pass  # Handled gracefully in script

# # ------------------ pyRevit Imports -------------------
from pyrevit import forms
from pyrevit import revit
from pyrevit import DB

# # ------------------- module imports -------------------
import revitmaterials


def rgb_to_lrv(r, g, b):
    def linearise(c):
        c = c / 255.0

        if c <= 0.04045:
            return c / 12.92
        else:
            return ((c + 0.055) / 1.055) ** 2.4

    r_lin = linearise(r)
    g_lin = linearise(g)
    b_lin = linearise(b)

    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def rgb_to_string(colour):
    if colour:
        r, g, b = colour.Red, colour.Green, colour.Blue
        luminance = rgb_to_lrv(r, g, b)
        if luminance < 0.4:
            tr, tg, tb = 255, 255, 255
        else:
            tr, tg, tb = 0, 0, 0
        return (
            "({0},{1},{2})".format(r, g, b),
            "#%02X%02X%02X" % (r, g, b),
            "#%02X%02X%02X" % (tr, tg, tb),
            luminance,
        )
    return "", "", "", ""


def export_materials_to_excel():

    doc = revit.doc
    colour_dict = {}

    output_file = forms.save_file(
        file_ext="xlsx", default_name="Revit_Materials.xlsx", title="Save Material List"
    )

    if not output_file:
        forms.alert("No output file selected", title="No Output File", warn_icon=True)
        return

    materials = revitmaterials.get_materials(doc)
    if materials is None:
        return

    # 1. Verify xlsxwriter availability
    try:
        xlsxwriter
    except NameError:
        forms.alert(
            "The xlsxwriter module is missing from your pyRevit environment.",
            title="Missing Dependency",
            warn_icon=True,
        )
        return

    try:
        workbook = xlsxwriter.Workbook(output_file)

        ws = workbook.add_worksheet("Materials")

        header_format = workbook.add_format(
            {"bold": True, "bg_color": "#C5D9F1", "bottom": 1}
        )
        none_format = workbook.add_format({"font_color": "#C0C0C0"})
        error_format = workbook.add_format(
            {"font_color": "#9C0006", "bg_color": "#FFC7CE"}
        )
        pct_format = workbook.add_format()
        pct_format.set_num_format(9)  # 0%

        headers = [
            "Material Name",
            "Class",
            "Description",
            "Keynote",
            "Comments",
            "Shading Colour",
            "",
            "LRV",
            "Transparency",
            "Surface FG Pattern",
            "Surface FG Colour",
            "",
            "Surface BG Pattern",
            "Surface BG Colour",
            "",
            "Cut FG Pattern",
            "Cut FG Colour",
            "",
            "Cut BG Pattern",
            "Cut BG Colour",
            "",
            "Appearance Asset",
            "Count",
            "Area",
            "Volume",
        ]

        for col, header in enumerate(headers):
            ws.write(0, col, header, header_format)

        row = 1

        image_paths = defaultdict(lambda: {"material": "", "usage": "", "path": ""})

        for mat in sorted(materials, key=lambda x: x.Name):
            try:
                ws.write(row, 0, mat.Name)
                ws.write(row, 1, mat.MaterialClass)
                ws.write(
                    row,
                    2,
                    mat.get_Parameter(
                        DB.BuiltInParameter.ALL_MODEL_DESCRIPTION
                    ).AsString(),
                )
                ws.write(
                    row,
                    3,
                    mat.get_Parameter(DB.BuiltInParameter.KEYNOTE_PARAM).AsString(),
                )
                ws.write(
                    row,
                    4,
                    mat.get_Parameter(
                        DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS
                    ).AsString(),
                )

                colour_int, colour_hex, colour_text, lrv = rgb_to_string(mat.Color)
                ws.write(row, 5, colour_int)
                if "colour_{}".format(colour_hex) not in colour_dict:
                    colour_dict["colour_{}".format(colour_hex)] = workbook.add_format(
                        {"bg_color": colour_hex, "font_color": colour_text}
                    )
                ws.write(
                    row, 6, colour_hex, colour_dict["colour_{}".format(colour_hex)]
                )
                ws.write(row, 7, lrv, pct_format)
                ws.write(
                    row,
                    8,
                    float(
                        mat.get_Parameter(
                            DB.BuiltInParameter.MATERIAL_PARAM_TRANSPARENCY
                        ).AsInteger()
                        / 100
                    ),
                    pct_format,
                )

                pattern_name = revitmaterials.get_pattern_name(
                    doc, mat.SurfaceForegroundPatternId
                )
                if pattern_name == "<none>":
                    ws.write(row, 9, pattern_name, none_format)
                else:
                    ws.write(row, 9, pattern_name)

                colour_int, colour_hex, colour_text, _ = rgb_to_string(
                    mat.SurfaceForegroundPatternColor
                )
                ws.write(row, 10, colour_int)
                if "colour_{}".format(colour_hex) not in colour_dict:
                    colour_dict["colour_{}".format(colour_hex)] = workbook.add_format(
                        {"bg_color": colour_hex, "font_color": colour_text}
                    )
                ws.write(
                    row, 11, colour_hex, colour_dict["colour_{}".format(colour_hex)]
                )

                pattern_name = revitmaterials.get_pattern_name(
                    doc, mat.SurfaceBackgroundPatternId
                )
                if pattern_name == "<none>":
                    ws.write(row, 12, pattern_name, none_format)
                else:
                    ws.write(row, 12, pattern_name)

                colour_int, colour_hex, colour_text, _ = rgb_to_string(
                    mat.SurfaceBackgroundPatternColor
                )
                ws.write(row, 13, colour_int)
                if "colour_{}".format(colour_hex) not in colour_dict:
                    colour_dict["colour_{}".format(colour_hex)] = workbook.add_format(
                        {"bg_color": colour_hex, "font_color": colour_text}
                    )
                ws.write(
                    row, 14, colour_hex, colour_dict["colour_{}".format(colour_hex)]
                )

                pattern_name = revitmaterials.get_pattern_name(
                    doc, mat.CutForegroundPatternId
                )
                if pattern_name == "<none>":
                    ws.write(row, 15, pattern_name, none_format)
                else:
                    ws.write(row, 15, pattern_name)

                colour_int, colour_hex, colour_text, _ = rgb_to_string(
                    mat.CutForegroundPatternColor
                )
                ws.write(row, 16, colour_int)
                if "colour_{}".format(colour_hex) not in colour_dict:
                    colour_dict["colour_{}".format(colour_hex)] = workbook.add_format(
                        {"bg_color": colour_hex, "font_color": colour_text}
                    )
                ws.write(
                    row, 17, colour_hex, colour_dict["colour_{}".format(colour_hex)]
                )

                pattern_name = revitmaterials.get_pattern_name(
                    doc, mat.CutBackgroundPatternId
                )
                if pattern_name == "<none>":
                    ws.write(row, 18, pattern_name, none_format)
                else:
                    ws.write(row, 18, pattern_name)

                colour_int, colour_hex, colour_text, _ = rgb_to_string(
                    mat.CutBackgroundPatternColor
                )
                ws.write(row, 19, colour_int)
                if "colour_{}".format(colour_hex) not in colour_dict:
                    colour_dict["colour_{}".format(colour_hex)] = workbook.add_format(
                        {"bg_color": colour_hex, "font_color": colour_text}
                    )
                ws.write(
                    row, 20, colour_hex, colour_dict["colour_{}".format(colour_hex)]
                )

                ws.write(row, 21, revitmaterials.get_asset(doc, mat)["name"])

                mat_count, mat_area, mat_volume = revitmaterials.get_material_usage(mat)
                ws.write(row, 22, mat_count)
                ws.write(row, 23, round(mat_area, 1))
                ws.write(row, 24, round(mat_volume, 2))

                paths = revitmaterials.get_material_texture_paths(mat, doc)
                i = 0
                for p in paths:
                    if p != "":
                        p["material"] = mat.Name
                        image_paths[10000 * mat.Id.IntegerValue + 100 * row + i] = p
                        i += 1

                row += 1

            except Exception as ex:
                print("Failed on material: {} | {}".format(mat.Name, ex))

        ws.autofilter(0, 0, row - 1, len(headers) - 1)

        for col in range(len(headers)):
            ws.set_column(col, col, 25)
        ws.set_column(0, 0, 50)
        for col in [5, 10, 13, 16, 19]:
            ws.set_column(col, col, 15)
            ws.set_column(col + 1, col + 1, 10)
        for col in [7, 8, 22, 23, 24]:
            ws.set_column(col, col, 10)
        # ws.autofit() # doesn't work with ver of xlsxwriter in ironpython

        wm = workbook.add_worksheet("Bitmap Paths")

        headers = [
            "Material Name",
            "Property",
            "Image Path",
            "Resolved Path",
            "Method",
            "Search Time (ms)",
        ]

        for col, header in enumerate(headers):
            wm.write(0, col, header, header_format)

        mat_row = 1
        for im in image_paths:
            wm.write(mat_row, 0, image_paths.get(im, "-")["material"])
            wm.write(mat_row, 1, image_paths.get(im, "-")["usage"])
            wm.write(mat_row, 2, image_paths.get(im, "-")["path"])
            resolved_path = image_paths.get(im, "-")["resolved_path"]
            if resolved_path == "<not found>":
                wm.write(mat_row, 3, resolved_path, none_format)
            else:
                wm.write(mat_row, 3, resolved_path)
            method = image_paths.get(im, "-")["method"]
            if method == "Missing":
                wm.write(mat_row, 4, method, error_format)
            else:
                wm.write(mat_row, 4, method)
            wm.write(mat_row, 5, image_paths.get(im, "-")["time"])
            mat_row += 1

        wm.set_column(0, 1, 50)
        wm.set_column(2, 3, 100)
        wm.set_column(4, 5, 25)

        workbook.close()

        forms.alert(
            "Exported {} materials to {}".format(row - 1, output_file),
            title="Export Complete",
        )

    except Exception as e:
        forms.alert(
            "Failed to save the Excel file. Please ensure the file is not currently open.\n\nError: {}".format(
                e
            ),
            title="Export Failed",
            warn_icon=True,
        )


if __name__ == "__main__":
    try:
        export_materials_to_excel()
    except Exception:
        print(traceback.format_exc())
