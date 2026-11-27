# -*- coding: utf-8 -*-
"""Update Materials From Project.

Overwrites the materials in the current project with the materials of the same
name in another project (e.g. a project with corrected swatches into the company
template). Materials that do not exist in the current project are not added.

Run it from the project to be updated. For each matching material the identity
text, class, shading colour, transparency and graphics patterns are copied, and
the appearance asset is copied across and replaces the existing one.
"""

# # -------------- Standard Library Imports --------------
import os
import sys
import traceback

# # ------------------ pyRevit Imports -------------------
from pyrevit import DB
from pyrevit import forms
from pyrevit import revit
from pyrevit import script
from pyrevit.framework import List

# # ------------------- module imports -------------------
MATERIAL_LIB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "Tools.panel",
    "lib",
)
if os.path.isdir(MATERIAL_LIB_DIR) and MATERIAL_LIB_DIR not in sys.path:
    sys.path.append(MATERIAL_LIB_DIR)

import revitmaterials  # noqa: E402

output = script.get_output()

PATTERN_FIELDS = [
    ("SurfaceForegroundPatternId", "SurfaceForegroundPatternColor"),
    ("SurfaceBackgroundPatternId", "SurfaceBackgroundPatternColor"),
    ("CutForegroundPatternId", "CutForegroundPatternColor"),
    ("CutBackgroundPatternId", "CutBackgroundPatternColor"),
]

TEXT_FIELDS = [
    DB.BuiltInParameter.ALL_MODEL_DESCRIPTION,
    DB.BuiltInParameter.KEYNOTE_PARAM,
    DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS,
]


# ----------------------------------------------------------------------
# Source document
# ----------------------------------------------------------------------
def find_open_document(path):
    """Returns the open document for a file path, or None."""
    wanted = os.path.normcase(os.path.normpath(path))
    for open_doc in revit.HOST_APP.app.Documents:
        if (
            open_doc.PathName
            and os.path.normcase(os.path.normpath(open_doc.PathName)) == wanted
        ):
            return open_doc
    return None


def open_document(path):
    """Open a project file without making it the active document."""
    options = DB.OpenOptions()
    options.DetachFromCentralOption = (
        DB.DetachFromCentralOption.DetachAndPreserveWorksets
    )
    model_path = DB.ModelPathUtils.ConvertUserVisiblePathToModelPath(path)
    return revit.HOST_APP.app.OpenDocumentFile(model_path, options)


# ----------------------------------------------------------------------
# Material handling
# ----------------------------------------------------------------------
def copy_colour(colour):
    """Returns a new Color, or None if the colour is unset."""
    if colour is None or not colour.IsValid:
        return None
    return DB.Color(colour.Red, colour.Green, colour.Blue)


def copy_material_properties(source_doc, source, dest_doc, dest, dest_patterns):
    """Copy everything except the appearance asset from source to dest."""
    dest.MaterialClass = source.MaterialClass

    for bip in TEXT_FIELDS:
        revitmaterials.set_material_text(
            dest, bip, revitmaterials.get_material_text(source, bip)
        )

    colour = copy_colour(source.Color)
    if colour:
        dest.Color = colour

    revitmaterials.set_transparency(dest, revitmaterials.get_transparency(source))

    for pattern_prop, colour_prop in PATTERN_FIELDS:
        pattern_name = revitmaterials.get_pattern_name(
            source_doc, getattr(source, pattern_prop)
        )
        setattr(
            dest,
            pattern_prop,
            revitmaterials.get_pattern_id(pattern_name, dest_patterns),
        )
        colour = copy_colour(getattr(source, colour_prop))
        if colour:
            setattr(dest, colour_prop, colour)


def copy_appearance_asset(source_doc, asset_id, dest_doc):
    """Copy an appearance asset between documents. Returns the new asset or None."""
    new_ids = DB.ElementTransformUtils.CopyElements(
        source_doc,
        List[DB.ElementId]([asset_id]),
        dest_doc,
        DB.Transform.Identity,
        DB.CopyPasteOptions(),
    )
    for new_id in new_ids:
        return dest_doc.GetElement(new_id)
    return None


def get_referenced_asset_ids(doc):
    """Returns the set of appearance asset id values used by any material."""
    return {
        revitmaterials.get_element_id_value(m.AppearanceAssetId)
        for m in revitmaterials.get_materials(doc, sort=False)
        if revitmaterials.is_valid_id(m.AppearanceAssetId)
    }


def update_materials_in_transaction(source_doc, dest_doc, names, source, dest, errors):
    """Overwrite matching materials. Returns ({new asset id: source name}, old ids)."""
    dest_patterns = revitmaterials.get_fill_patterns_by_name(dest_doc)
    copied_assets = {}
    renames = {}
    replaced_ids = []

    with revit.Transaction("Update Materials From Project"):
        with forms.ProgressBar(
            title="Materials ({value}/{max_value})", cancellable=True
        ) as pb:
            for i, name in enumerate(names, 1):
                if pb.cancelled:
                    errors.append("Cancelled before '{}'.".format(name))
                    break
                pb.update_progress(i, len(names))

                try:
                    copy_material_properties(
                        source_doc, source[name], dest_doc, dest[name], dest_patterns
                    )
                    source_asset_id = source[name].AppearanceAssetId
                    if not revitmaterials.is_valid_id(source_asset_id):
                        continue

                    key = revitmaterials.get_element_id_value(source_asset_id)
                    if key not in copied_assets:
                        new_asset = copy_appearance_asset(
                            source_doc, source_asset_id, dest_doc
                        )
                        copied_assets[key] = new_asset
                        renames[new_asset.Id] = source_doc.GetElement(
                            source_asset_id
                        ).Name

                    old_id = dest[name].AppearanceAssetId
                    if revitmaterials.is_valid_id(old_id):
                        replaced_ids.append(old_id)
                    dest[name].AppearanceAssetId = copied_assets[key].Id

                except Exception:
                    errors.append("{}\n{}".format(name, traceback.format_exc()))

        remove_unused_assets(dest_doc, replaced_ids, errors)

    return renames


def remove_unused_assets(doc, candidate_ids, errors):
    """Delete replaced assets that no material uses any more."""
    still_used = get_referenced_asset_ids(doc)
    removed = set()
    for asset_id in candidate_ids:
        key = revitmaterials.get_element_id_value(asset_id)
        if key in still_used or key in removed:
            continue
        removed.add(key)
        try:
            doc.Delete(asset_id)
        except Exception:
            errors.append("Could not delete old asset {}.".format(key))


def restore_asset_names(doc, renames, errors):
    """Give copied assets their source names (a copy may be given a suffix)."""
    for asset_id, source_name in renames.items():
        asset = doc.GetElement(asset_id)
        if asset is None or asset.Name == source_name:
            continue
        if not revitmaterials.update_asset_name(doc, asset_id, source_name):
            errors.append(
                "Asset '{}' could not be renamed to '{}'.".format(
                    asset.Name, source_name
                )
            )


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    dest_doc = revit.doc
    path = forms.pick_file(
        file_ext="rvt", title="Select Project To Copy Materials From"
    )
    if not path:
        script.exit()

    source_doc = find_open_document(path)
    opened_here = source_doc is None
    if source_doc is not None and source_doc.Equals(dest_doc):
        forms.alert("Select a different project.", exitscript=True)

    errors = []
    try:
        if opened_here:
            source_doc = open_document(path)

        source = revitmaterials.get_materials_by_name(source_doc)
        dest = revitmaterials.get_materials_by_name(dest_doc)
        names = sorted(n for n in dest if n in source)
        if not names:
            forms.alert("No materials with matching names.", exitscript=True)

        if not forms.alert(
            "Overwrite {} of {} materials in this project with the versions from:"
            "\n{}".format(len(names), len(dest), path),
            title="Update Materials",
            yes=True,
            no=True,
        ):
            script.exit()

        renames = update_materials_in_transaction(
            source_doc, dest_doc, names, source, dest, errors
        )
        restore_asset_names(dest_doc, renames, errors)
    finally:
        if opened_here and source_doc is not None:
            source_doc.Close(False)

    summary = [
        "Materials matched: {}".format(len(names)),
        "Errors: {}".format(len(errors)),
    ]
    if errors:
        summary.append("\n" + "\n".join(errors[:20]))
    forms.alert("\n".join(summary), title="Material Update Complete")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(traceback.format_exc())
