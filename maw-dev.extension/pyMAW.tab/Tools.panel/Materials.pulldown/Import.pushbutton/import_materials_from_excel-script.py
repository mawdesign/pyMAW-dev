# -*- coding: utf-8 -*-
"""
Import Materials From Excel
Round-trip companion to Export Materials To Excel
"""
# # -------------- Standard Library Imports --------------
# import os
import traceback
import re
import clr

# # -------------------- .NET Imports --------------------
clr.AddReference("Microsoft.Office.Interop.Excel")
from Microsoft.Office.Interop import Excel

# # ------------------ pyRevit Imports -------------------
from pyrevit import forms
from pyrevit import revit
from pyrevit import DB

# # ------------------- module imports -------------------
import revitmaterials


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def string_to_rgb(value):
    """
    Converts '(255,128,64)' -> DB.Color
    """
    if not value:
        return None

    # Try (R, G, B) format first
    match = re.match(
        r"\s*\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s*",
        str(value)
    )

    if match:
        return DB.Color(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3))
        )

    # Try Hex format
    match = re.match(
        r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$",
        str(value)
    )

    if match:
        clean_str = hex_str.lstrip('#')
        # Expand 3 digit to 6 digit
        if len(clean_str) == 3:
            clean_str = "".join(char * 2 for char in clean_str)
        return DB.Color(
            int(clean_str[0:2],16),
            int(clean_str[2:4],16),
            int(clean_str[4:6],16)
        )

    return None


def safe_string(value):
    if value is None:
        return ""

    text = str(value).strip()

    if text.lower() == "none":
        return ""

    return text


def get_materials_by_name(doc):
    materials = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.Material)
        .ToElements()
    )

    return { m.Name: m for m in materials }


def get_fill_patterns_by_name(doc):
    patterns = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.FillPatternElement)
        .ToElements()
    )

    return { p.Name: p.Id for p in patterns }


def set_parameter(material, bip, value):
    param = material.get_Parameter(bip)

    if not param:
        return

    try:
        param.Set(value)
    except Exception:
        pass


def set_pattern(pattern_name, pattern_dict):
    if not pattern_name:
        return DB.ElementId.InvalidElementId

    if pattern_name == "<none>":
        return DB.ElementId.InvalidElementId

    return pattern_dict.get(
        pattern_name,
        DB.ElementId.InvalidElementId
    )


def get_row_data(ws, row, headers):
    return {
        header: safe_string(ws.Cells(row, col).Value2)
        for header, col in headers.items()
    }

# ----------------------------------------------------------------------
# Material Handling
# ----------------------------------------------------------------------

def add_material(
        doc,
        data,
        pattern_lookup,
        material_lookup):

    material_name = data.get("material name")

    if material_name in material_lookup:
        raise Exception( "Material already exists: {}".format(material_name) )

    material_id = DB.Material.Create(doc, material_name)

    material = doc.GetElement(material_id)
    material_lookup[material_name] = material

    update_material_properties(
        material,
        data,
        pattern_lookup
    )

    return material


def rename_material(
        data,
        pattern_lookup,
        material_lookup):

    old_name = data.get("old material name")
    new_name = data.get("material name")
    material = material_lookup.get(old_name)

    if not material:
        raise Exception( "Material not found: {}".format(old_name) )

    if old_name != new_name:

        material.Name = new_name

        material_lookup.pop(old_name, None)
        material_lookup[new_name] = material

    update_material_properties(
        material,
        data,
        pattern_lookup
    )

    return material


def update_material(
        data,
        pattern_lookup,
        material_lookup):

    material_name = data.get("material name")
    material = material_lookup.get(material_name)

    if not material:
        raise Exception( "Material not found: {}".format(material_name) )

    update_material_properties(
        material,
        data,
        pattern_lookup
    )

    return material


def delete_material(
        data,
        material_lookup):

    material_name = data.get("old material name")
    material = material_lookup.get(material_name)

    if not material:
        raise Exception("Material not found: {}".format( material_name ))


from pyrevit import revit, DB

doc = revit.doc


def get_material_usage(doc, material, limit=5):
    """Returns up to `limit` ElementIds using the material.

    Checks both model instances and element types, stopping early.
    """
    target_id = material.Id
    found_ids = []

    # 1. Check all placed model instances (geometry, layers, and painted faces)
    instances = DB.FilteredElementCollector(doc).WhereElementIsNotElementType()
    for el in instances:
        if not el.Category:
            continue

        if target_id in el.GetMaterialIds(
            False
        ) or target_id in el.GetMaterialIds(True):
            found_ids.append(el.Id)
            if len(found_ids) >= limit:
                return found_ids

    # 2. Check ElementTypes (in case a WallType/FamilyType uses it, even if unplaced)
    element_types = DB.FilteredElementCollector(doc).WhereElementIsElementType()
    for el_type in element_types:
        if target_id in el_type.GetMaterialIds(False):
            found_ids.append(el_type.Id)
            if len(found_ids) >= limit:
                return found_ids

    return found_ids


# --- Example Usage ---
# Replace with your material lookup
target_mat = (
    DB.FilteredElementCollector(doc).OfClass(DB.Material).FirstElement()
)

if target_mat:
    sample_ids = get_material_usage(doc, target_mat, limit=5)

    if sample_ids:
        print(
            "Material '{}' IS in use. Sample ElementIds: {}".format(
                target_mat.Name, [x.IntegerValue for x in sample_ids]•  If you are running Revit 2024 or newer, replace x.IntegerValue with x.Value when printing the IDs, as IntegerValue was deprecated in the Revit 2024 API.
            )
        )
    else:
        print(
            "Material '{}' is NOT used and is safe to delete.".format(
                target_mat.Name
            )
        )




    # dependents = material.GetDependentElements(
        # DB.ElementClassFilter(DB.Element)
    # )

    # if dependents.Count > 0:

        # sample_ids = [
            # str(id.IntegerValue)
            # for id in list(dependents)[:5]
        # ]

        # raise Exception(
            # "Material '{}' is in use by {} element{}. Sample IDs: {}{}".format(
                # material_name,
                # dependents.Count,
                # "s" if dependents.Count > 1 else "",
                # ", ".join(sample_ids),
                # ",..." if dependents.Count > 5 else ""
            # )
        # )

    doc.Delete(material.Id)

    material_lookup.pop(old_name, None)


def update_material_properties(
        material,
        data,
        pattern_lookup):

    # Class
    if "class" in data:
        material.MaterialClass = data["class"]

    # Description
    if "description" in data:
        set_parameter(
            material,
            DB.BuiltInParameter.ALL_MODEL_DESCRIPTION,
            data["description"]
        )

    # Keynote
    if "keynote" in data:
        set_parameter(
            material,
            DB.BuiltInParameter.KEYNOTE_PARAM,
            data["keynote"]
        )

    # Comments
    if "comments" in data:
        set_parameter(
            material,
            DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS,
            data["comments"]
        )

    # Shading Colour
    if "shading colour" in data:
        colour = string_to_rgb(data["shading colour"])
        if colour:
            material.Color = colour

    # Transparency
    if "transparency" in data:
        value = data["transparency"]
        if value is not None:
            transparency = int(round(float(value) * 100))
            set_parameter(
                material,
                DB.BuiltInParameter.MATERIAL_PARAM_TRANSPARENCY,
                transparency
            )

    # Surface Foreground
    if "surface fg pattern" in data:
        material.SurfaceForegroundPatternId = set_pattern(
            data["surface fg pattern"],
            pattern_lookup
        )

    if "surface fg colour" in data:
        colour = string_to_rgb(data["surface fg colour"])
        if colour:
            material.SurfaceForegroundPatternColor = colour

    # Surface Background
    if "surface bg pattern" in data:
        material.SurfaceBackgroundPatternId = set_pattern(
            data["surface bg pattern"],
            pattern_lookup
        )

    if "surface bg colour" in data:
        colour = string_to_rgb(data["surface bg colour"])
        if colour:
            material.SurfaceBackgroundPatternColor = colour

    # Cut Foreground
    if "cut fg pattern" in data:
        material.CutForegroundPatternId = set_pattern(
            data["cut fg pattern"],
            pattern_lookup
        )

    if "cut fg colour" in data:
        colour = string_to_rgb(data["cut fg colour"])
        if colour:
            material.CutForegroundPatternColor = colour

    # Cut Background
    if "cut bg pattern" in data:
        material.CutBackgroundPatternId = set_pattern(
            data["cut bg pattern"],
            pattern_lookup
        )

    if "cut bg colour" in data:
        colour = string_to_rgb(data["cut bg colour"])
        if colour:
            material.CutBackgroundPatternColor = colour


# ----------------------------------------------------------------------
# Excel Import
# ----------------------------------------------------------------------

def import_materials():

    doc = revit.doc

    filepath = forms.pick_file(
        file_ext="xlsx",
        title="Select Material Spreadsheet"
    )

    if not filepath:
        return

    app = Excel.ApplicationClass()
    app.Visible = False

    wb = app.Workbooks.Open(filepath)

    names = []

    try:
        for sheet in wb.Worksheets:
            names.append(sheet.Name)
    except Exception as e:
        forms.alert("Excel document couldn't be opened\n" + str(e),
            title="Import Failed.",
            warn_icon=True
        )
        wb.Close(False)
        app.Quit()

    if "Materials" not in names:
        forms.alert(
            "Materials worksheet not found.",
            title="Import Failed",
            warn_icon=True
        )
        return

    ws = wb.Worksheets["Materials"]
    used = ws.UsedRange

    headers = {}

    try:
        for col in range(1, used.Columns.Count + 1):
            value = used.Cells(1, col).Value2
            if value:
                headers[str(value).strip().lower()] = col

        material_name_col = headers.get("material name")

        if not material_name_col:
            forms.alert(
                "Material Name column not found.",
                title="Import Failed",
                warn_icon=True
            )
            return
    except:
        pass

    material_lookup = get_materials_by_name(doc)
    pattern_lookup = get_fill_patterns_by_name(doc)

    added = renamed = updated = deleted = skipped = 0
    errors = []

    with revit.Transaction("Import Materials"):
        with forms.ProgressBar( title='Materials ({value}/{max_value})', cancellable=True) as pb:

            rows = range(2, used.Rows.Count + 1)
            total = len(rows)

            for i, row in enumerate(rows, 1):

                if pb.cancelled:
                    forms.alert("Import cancelled.")
                    return

                try:
                    row_data = get_row_data(ws, row, headers)
                    material_name = row_data.get("material name")
                    old_name = ""

                    if "old material name" in row_data:
                        old_name = row_data.get("old material name")

                    if "action" in row_data:
                        action = row_data.get("action").lower()
                    elif material_name and old_name:
                        action = "rename" # if no action column, but has old name column assume rename
                    elif material_lookup.get(material_name):
                        action = "update" # else if no old name column and material exists then assume update
                    else:
                        action = "add"

                    pb.update_progress(i, total)
                    pb.title = ( "{}: {} ({}/{})".format(
                        (action.upper() if action else "SKIPPING"), 
                        (material_name if material_name else old_name), 
                        i, 
                        total
                    ))

                    if action == "":
                        skipped += 1
                        continue

                    elif action == "add":
                        add_material(
                            doc,
                            row_data,
                            pattern_lookup,
                            material_lookup,
                        )
                        added += 1

                    elif action == "rename":
                        rename_material(
                            row_data,
                            pattern_lookup,
                            material_lookup,
                        )
                        renamed += 1

                    elif action == "update":
                        update_material(
                            row_data,
                            pattern_lookup,
                            material_lookup,
                        )
                        updated += 1

                    elif action == "delete":
                        delete_material(
                            row_data,
                            material_lookup,
                        )
                        deleted += 1

                    else:
                        errors.append(
                            "Row {}: Unknown action '{}'".format(row, action)
                        )

                except Exception as ex:
                    errors.append("Row {}: {}\n".format(row, str(ex) )+traceback.format_exc())

    summary = []

    summary.append( "Added: {}".format(added) )
    summary.append( "Renamed: {}".format(renamed) )
    summary.append( "Updated: {}".format(updated) )
    summary.append( "Deleted: {}".format(deleted) )
    summary.append( "Skipped: {} (no action specified)".format(skipped) )

    summary.append( "Errors: {}".format(len(errors)) )

    if errors:
        summary.append( "\nErrors:\n" + "\n".join(errors[:20]) )

    forms.alert( "\n".join(summary), title="Material Import Complete"
)


if __name__ == "__main__":
    try:
        import_materials()
    except Exception:
        print(traceback.format_exc())