# -*- coding: utf-8 -*-
"""Import Materials From Excel.

Round-trip companion to Export Materials To Excel.
"""

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

# Pattern + colour columns: (pattern header, colour header, pattern prop, colour prop)
PATTERN_FIELDS = [
    (
        "surface fg pattern",
        "surface fg colour",
        "SurfaceForegroundPatternId",
        "SurfaceForegroundPatternColor",
    ),
    (
        "surface bg pattern",
        "surface bg colour",
        "SurfaceBackgroundPatternId",
        "SurfaceBackgroundPatternColor",
    ),
    (
        "cut fg pattern",
        "cut fg colour",
        "CutForegroundPatternId",
        "CutForegroundPatternColor",
    ),
    (
        "cut bg pattern",
        "cut bg colour",
        "CutBackgroundPatternId",
        "CutBackgroundPatternColor",
    ),
]

TEXT_FIELDS = [
    ("description", DB.BuiltInParameter.ALL_MODEL_DESCRIPTION),
    ("keynote", DB.BuiltInParameter.KEYNOTE_PARAM),
    ("comments", DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS),
]


# ----------------------------------------------------------------------
# Material Handling
# ----------------------------------------------------------------------
def set_colour_property(material, prop, text):
    """Set a Color property from "(r,g,b)" or hex text; ignored if unparseable."""
    colour = revitcolour.parse_colour(text)
    if colour:
        setattr(material, prop, colour)


def update_material_properties(material, data, pattern_lookup):
    """Apply the columns present in `data` to the material."""
    if "class" in data:
        material.MaterialClass = data["class"]

    for header, bip in TEXT_FIELDS:
        if header in data:
            revitmaterials.set_material_text(material, bip, data[header])

    if "shading colour" in data:
        set_colour_property(material, "Color", data["shading colour"])

    if data.get("transparency"):
        revitmaterials.set_transparency(material, data["transparency"])

    for pattern_header, colour_header, pattern_prop, colour_prop in PATTERN_FIELDS:
        if pattern_header in data:
            setattr(
                material,
                pattern_prop,
                revitmaterials.get_pattern_id(data[pattern_header], pattern_lookup),
            )
        if colour_header in data:
            set_colour_property(material, colour_prop, data[colour_header])


def add_material(doc, data, pattern_lookup, material_lookup):
    material_name = data.get("material name")

    if material_name in material_lookup:
        raise Exception("Material already exists: {}".format(material_name))

    material = doc.GetElement(DB.Material.Create(doc, material_name))
    material_lookup[material_name] = material

    update_material_properties(material, data, pattern_lookup)
    return material


def rename_material(data, pattern_lookup, material_lookup):
    old_name = data.get("old material name")
    new_name = data.get("material name")
    material = material_lookup.get(old_name)

    if not material:
        raise Exception("Material not found: {}".format(old_name))

    if old_name != new_name:
        material.Name = new_name
        material_lookup.pop(old_name, None)
        material_lookup[new_name] = material

    update_material_properties(material, data, pattern_lookup)
    return material


def update_material(data, pattern_lookup, material_lookup):
    material_name = data.get("material name")
    material = material_lookup.get(material_name)

    if not material:
        raise Exception("Material not found: {}".format(material_name))

    update_material_properties(material, data, pattern_lookup)
    return material


def delete_material(doc, data, material_lookup):
    material_name = data.get("old material name") or data.get("material name")
    material = material_lookup.get(material_name)

    if not material:
        raise Exception("Material not found: {}".format(material_name))

    sample_ids = revitmaterials.find_material_users(doc, material, limit=5)

    if sample_ids:
        raise Exception(
            "Material '{}' is in use. Sample Ids: {}".format(
                material_name, ", ".join(sample_ids)
            )
        )

    doc.Delete(material.Id)
    material_lookup.pop(material_name, None)


def get_action(data, material_lookup):
    """Action from the "action" column, else inferred from the other columns."""
    if "action" in data:
        return data["action"].lower()
    if data.get("material name") and data.get("old material name"):
        return "rename"
    if data.get("material name") in material_lookup:
        return "update"
    return "add"


# ----------------------------------------------------------------------
# Excel Import
# ----------------------------------------------------------------------
def import_materials():
    doc = revit.doc

    filepath = forms.pick_file(file_ext="xlsx", title="Select Material Spreadsheet")

    if not filepath:
        return

    sheet = revitexcel.read_sheet(filepath, "Materials")

    if sheet is None:
        forms.alert(
            "Materials worksheet not found.", title="Import Failed", warn_icon=True
        )
        return

    if "material name" not in sheet["headers"]:
        forms.alert(
            "Material Name column not found.", title="Import Failed", warn_icon=True
        )
        return

    material_lookup = revitmaterials.get_materials_by_name(doc)
    pattern_lookup = revitmaterials.get_fill_patterns_by_name(doc)

    counts = {"add": 0, "rename": 0, "update": 0, "delete": 0, "skip": 0}
    errors = []
    rows = sheet["rows"]
    total = len(rows)

    with revit.Transaction("Import Materials"):
        with forms.ProgressBar(
            title="Materials ({value}/{max_value})", cancellable=True
        ) as pb:
            for i, data in enumerate(rows, 1):
                if pb.cancelled:
                    forms.alert("Import cancelled.")
                    break

                row = data["_row"]
                try:
                    action = get_action(data, material_lookup)
                    pb.update_progress(i, total)
                    pb.title = "{}: {} ({}/{})".format(
                        action.upper() if action else "SKIPPING",
                        data.get("material name") or data.get("old material name"),
                        i,
                        total,
                    )

                    if not action:
                        counts["skip"] += 1
                    elif action == "add":
                        add_material(doc, data, pattern_lookup, material_lookup)
                        counts["add"] += 1
                    elif action == "rename":
                        rename_material(data, pattern_lookup, material_lookup)
                        counts["rename"] += 1
                    elif action == "update":
                        update_material(data, pattern_lookup, material_lookup)
                        counts["update"] += 1
                    elif action == "delete":
                        delete_material(doc, data, material_lookup)
                        counts["delete"] += 1
                    else:
                        errors.append("Row {}: Unknown action '{}'".format(row, action))

                except Exception as ex:
                    errors.append(
                        "Row {}: {}\n{}".format(row, ex, traceback.format_exc())
                    )

    summary = [
        "Added: {}".format(counts["add"]),
        "Renamed: {}".format(counts["rename"]),
        "Updated: {}".format(counts["update"]),
        "Deleted: {}".format(counts["delete"]),
        "Skipped: {} (no action specified)".format(counts["skip"]),
        "Errors: {}".format(len(errors)),
    ]

    if errors:
        summary.append("\nErrors:\n" + "\n".join(errors[:20]))

    forms.alert("\n".join(summary), title="Material Import Complete")


if __name__ == "__main__":
    try:
        import_materials()
    except Exception:
        print(traceback.format_exc())
