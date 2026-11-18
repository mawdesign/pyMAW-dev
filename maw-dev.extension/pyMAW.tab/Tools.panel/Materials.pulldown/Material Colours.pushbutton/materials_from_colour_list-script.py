# -*- coding: utf-8 -*-
"""Materials From Colour List."""

# # -------------- Standard Library Imports --------------
# import os
# import sys
# import wpf
import re
import traceback
import clr

# # -------------------- .NET Imports --------------------
# clr.AddReference("System.Drawing")
# clr.AddReference("PresentationFramework")
# clr.AddReference("PresentationCore")
# clr.AddReference("WindowsBase")
clr.AddReference("Microsoft.Office.Interop.Excel")
from Microsoft.Office.Interop import Excel

# # ------------------ pyRevit Imports -------------------
from pyrevit import forms  # , script
from pyrevit import revit
from pyrevit import DB  # , UI


# ----------------------------------------------------------
# Helpers
# ----------------------------------------------------------

doc = revit.doc


class MaterialOption(forms.TemplateListItem):
    @property
    def name(self):
        return self.item.Name


def sanitise_material_name(text, space_replacement=None, ignore_tokens=None):
    """Cleans up the material name based on defined rules.

    Args:
        text (str):
            String to sanitise.
        ignore_tokens (list[str], optional):
            Strings to preserve during sanitisation. These are replaced
            with placeholders, sanitised around, then restored using
            str.format().
        space_replacement (str, optional):
            String to replace spaces with. If None, spaces are retained.

    Returns:
        str
    """
    space_replacement = space_replacement or " "
    ignore_tokens = ignore_tokens or []

    # Replace ignored strings with format placeholders
    placeholder_values = {}
    working = text

    for i, token in enumerate(ignore_tokens):
        placeholder = "..PLACEHOLDER.{i}..".format(i=i)
        placeholder_values[placeholder] = token
        working = working.replace(token, placeholder)

    # Replace bracket types
    working = (
        working.replace("{", "(").replace("}", ")").replace("[", "(").replace("]", ")")
    )

    # This regex replaces characters that aren't letters, numbers, hyphens, underscores, brackets, or periods
    re.sub(r"[^\w\s\-\.\(\)]", "_", working)

    # Space replacement
    working = re.sub(r"\s+", space_replacement, working)

    # Collapse repeated replacement strings
    working = re.sub(
        re.escape(space_replacement) + r"+",
        space_replacement,
        working,
    )

    # Collapse multiple underscores
    working = re.sub(r"_{2,}", "_", working)

    # Remove underscores adjacent to separators
    working = re.sub(r"([()\-])_+", r"\1", working)
    working = re.sub(r"_+([()\-])", r"\1", working)

    # Strip any leading or trailing punctuation/spaces
    working = working.strip(" _")
    # Restore placeholder markers that were sanitised above

    for placeholder, token in placeholder_values.items():
        working = working.replace(placeholder, token)

    return working


def get_materials():
    return sorted(
        DB.FilteredElementCollector(doc).OfClass(DB.Material).ToElements(),
        key=lambda x: x.Name,
    )


def read_sheet_names(path):
    app = Excel.ApplicationClass()
    app.Visible = False

    wb = app.Workbooks.Open(path)

    names = []

    try:
        for sheet in wb.Worksheets:
            names.append(sheet.Name)
    finally:
        wb.Close(False)
        app.Quit()

    return names


def load_colour_rows(path, sheet_name):

    app = Excel.ApplicationClass()
    app.Visible = False

    wb = app.Workbooks.Open(path)
    ws = wb.Worksheets[sheet_name]

    colours = []

    try:
        used = ws.UsedRange

        header_map = {}

        for col in range(1, used.Columns.Count + 1):
            value = used.Cells(1, col).Value2

            if value:
                header_map[str(value).strip().lower()] = col

        name_col = header_map.get("colour name")
        r_col = header_map.get("r")
        g_col = header_map.get("g")
        b_col = header_map.get("b")
        lrv_col = header_map.get("lrv")

        if not all([name_col, r_col, g_col, b_col]):
            raise Exception("Worksheet must contain columns: Colour Name, R, G, B")

        for row in range(2, used.Rows.Count + 1):
            colour_name = ws.Cells(row, name_col).Value2
            if not colour_name:
                continue

            colour_lrv = int(ws.Cells(row, lrv_col).Value2) if lrv_col else None

            colours.append(
                {
                    "name": str(colour_name).strip(),
                    "r": int(ws.Cells(row, r_col).Value2),
                    "g": int(ws.Cells(row, g_col).Value2),
                    "b": int(ws.Cells(row, b_col).Value2),
                    "lrv": colour_lrv,
                }
            )

    finally:
        wb.Close(False)
        app.Quit()

    return colours


def duplicate_appearance_asset(material, asset_name):

    asset_id = material.AppearanceAssetId

    if asset_id == DB.ElementId.InvalidElementId:
        return None

    asset_elem = doc.GetElement(asset_id)

    try:
        new_asset = asset_elem.Duplicate(asset_name)
        return new_asset
    except:
        return None


def set_asset_colour(asset_id, revit_colour):
    if not asset_id:
        return

    edit_scope = DB.Visual.AppearanceAssetEditScope(doc)

    try:
        asset = edit_scope.Start(asset_id)

        try:
            prop = asset.FindByName(DB.Visual.Generic.GenericDiffuse)
            if prop:
                prop.SetValueAsColor(revit_colour)

        except Exception as e:
            print(str(e))

        edit_scope.Commit(True)

    except Exception as e:
        print(str(e))
        try:
            edit_scope.Cancel()
        except:
            pass


def build_name(pattern, material_name, colour_name, lrv_val, parent_name=None):
    if not parent_name:
        parent_name = material_name

    return pattern.format(
        material=material_name,
        colour=colour_name,
        lrv=lrv_val,
        new_mat_name=parent_name,
    )


# ----------------------------------------------------------
# Main
# ----------------------------------------------------------


def materials_from_colour_list():

    materials = get_materials()

    selected_materials = forms.SelectFromList.show(
        [MaterialOption(x) for x in materials],
        multiselect=True,
        title="Select Template Materials",
        button_name="Continue",
    )

    if not selected_materials:
        return

    excel_path = forms.pick_file(file_ext="xlsx", title="Select Colour Workbook")

    if not excel_path:
        return

    sheets = read_sheet_names(excel_path)

    sheet_name = forms.SelectFromList.show(sheets, title="Select Worksheet")

    if not sheet_name:
        return

    material_pattern = forms.ask_for_string(
        default="{material}_{colour}",
        prompt=(
            "Material naming pattern\n\n"
            "Available:\n"
            "{material}: Original material name\n"
            "{colour}:   Colour name from spreadsheet\n"
            "{lrv}:      Light reflectance value (if provided in spreadsheet)\n"
        ),
        title="Material Name Pattern",
    )
    material_pattern = sanitise_material_name(
        material_pattern, ignore_tokens=["{material}", "{colour}", "{lrv}"]
    )

    if not material_pattern:
        return

    asset_pattern = forms.ask_for_string(
        default="{material}_{colour}",
        prompt=(
            "Appearance Asset Naming Pattern\n\n"
            "Available:\n"
            "{material}: Original material name\n"
            "{colour}:   Colour name from spreadsheet\n"
            "{lrv}:      Light reflectance value (if provided in spreadsheet)\n"
            "{new_mat_name}: New material name\n"
        ),
        title="Asset Name Pattern",
    )
    asset_pattern = sanitise_material_name(
        asset_pattern,
        ignore_tokens=["{material}", "{colour}", "{lrv}", "{new_mat_name}"],
    )

    if not asset_pattern:
        return

    colours = load_colour_rows(excel_path, sheet_name)

    existing_names = set(x.Name for x in materials)

    total = len(selected_materials) * len(colours)
    count_success = 0

    with forms.ProgressBar(title="Creating Materials") as pb:
        count = 0

        with revit.Transaction("Create Materials From Colour List"):
            for template in selected_materials:
                for colour_data in colours:
                    count += 1

                    pb.update_progress(count, total)

                    colour_name = colour_data["name"]
                    lrv_val = colour_data["lrv"]

                    rgb = (colour_data["r"], colour_data["g"], colour_data["b"])

                    new_material_name = build_name(
                        material_pattern,
                        template.Name,
                        colour_name,
                        lrv_val,
                    )

                    if new_material_name in existing_names:
                        print("Already exists -> SKIPPING")
                        continue

                    try:
                        new_mat = template.Duplicate(new_material_name)

                        revit_colour = DB.Color(rgb[0], rgb[1], rgb[2])

                        new_mat.UseRenderAppearanceForShading = False
                        new_mat.Color = revit_colour

                        # try:
                        # new_mat.SurfaceForegroundPatternColor = revit_colour
                        # except:
                        # print("Forground colour not set")
                        # pass

                        # try:
                        # new_mat.CutForegroundPatternColor = revit_colour
                        # except:
                        # print("Background colour not set")
                        # pass

                        # try:
                        # new_mat.UseRenderAppearanceForShading = True
                        # except:
                        # print("Render appearance not set")
                        # pass

                        asset_name = build_name(
                            asset_pattern,
                            template.Name,
                            colour_name,
                            lrv_val,
                            parent_name=new_material_name,
                        )

                        new_asset = duplicate_appearance_asset(new_mat, asset_name)

                        if new_asset:
                            new_mat.AppearanceAssetId = new_asset.Id
                            set_asset_colour(new_asset.Id, revit_colour)

                        existing_names.add(new_material_name)

                        count_success += 1

                    except Exception:
                        print("Failed: {}".format(new_material_name))

                        print(traceback.format_exc())

    forms.alert(
        "Material generation complete.\n{}\\{} materials made.".format(
            count_success, count
        ),
        title="Materials From Colour List",
    )


if __name__ == "__main__":
    try:
        materials_from_colour_list()

    except Exception:
        print(traceback.format_exc())
