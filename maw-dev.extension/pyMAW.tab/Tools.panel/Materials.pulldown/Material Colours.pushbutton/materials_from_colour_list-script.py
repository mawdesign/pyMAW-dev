# -*- coding: utf-8 -*-
"""Materials From Colour List."""

# # -------------- Standard Library Imports --------------
import re
import traceback

# # ------------------ pyRevit Imports -------------------
from pyrevit import forms
from pyrevit import revit

# # ------------------- module imports -------------------
import revitcolour
import revitexcel
import revitforms
import revitmaterials


# ----------------------------------------------------------
# Helpers
# ----------------------------------------------------------


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
    working = re.sub(r"[^\w\s\-\.\(\)]", "_", working)

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


def to_number(text):
    """Cell text -> int/float, or None if blank or not numeric."""
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return int(value) if value.is_integer() else value


def load_colour_rows(sheet):
    """Returns [{"name", "r", "g", "b", "lrv"}, ...] from a revitexcel sheet."""
    required = ["colour name", "r", "g", "b"]
    if not all(h in sheet["headers"] for h in required):
        raise Exception("Worksheet must contain columns: Colour Name, R, G, B")

    colours = []
    for row in sheet["rows"]:
        if not row.get("colour name"):
            continue
        colours.append(
            {
                "name": row["colour name"],
                "r": int(float(row["r"])),
                "g": int(float(row["g"])),
                "b": int(float(row["b"])),
                "lrv": to_number(row.get("lrv")),
            }
        )

    return colours


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

    doc = revit.doc
    materials = revitmaterials.get_materials(doc)

    selected_materials = revitforms.select_materials(
        materials, title="Select Template Materials"
    )

    if not selected_materials:
        return

    excel_path = forms.pick_file(file_ext="xlsx", title="Select Colour Workbook")

    if not excel_path:
        return

    workbook = revitexcel.read_workbook(excel_path)

    sheet_name = forms.SelectFromList.show(sorted(workbook), title="Select Worksheet")

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
    if not material_pattern:
        return

    material_pattern = sanitise_material_name(
        material_pattern, ignore_tokens=["{material}", "{colour}", "{lrv}"]
    )

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
    if not asset_pattern:
        return

    asset_pattern = sanitise_material_name(
        asset_pattern,
        ignore_tokens=["{material}", "{colour}", "{lrv}", "{new_mat_name}"],
    )

    colours = load_colour_rows(workbook[sheet_name])

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
                    revit_colour = revitcolour.rgb_to_colour(rgb)

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

                        new_mat.UseRenderAppearanceForShading = False
                        new_mat.Color = revit_colour

                        asset_name = build_name(
                            asset_pattern,
                            template.Name,
                            colour_name,
                            lrv_val,
                            parent_name=new_material_name,
                        )

                        new_asset = revitmaterials.duplicate_appearance_asset(
                            doc, new_mat, asset_name
                        )

                        if new_asset:
                            new_mat.AppearanceAssetId = new_asset.Id
                            revitmaterials.set_asset_colour(
                                doc, new_asset.Id, revit_colour
                            )

                        existing_names.add(new_material_name)

                        count_success += 1

                    except Exception:
                        print("Failed: {}".format(new_material_name))

                        print(traceback.format_exc())

    forms.alert(
        "Material generation complete.\n{} of {} materials made.".format(
            count_success, count
        ),
        title="Materials From Colour List",
    )


if __name__ == "__main__":
    try:
        materials_from_colour_list()

    except Exception:
        print(traceback.format_exc())
