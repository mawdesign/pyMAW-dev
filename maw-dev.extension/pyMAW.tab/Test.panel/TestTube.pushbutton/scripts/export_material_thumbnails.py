# -*- coding: utf-8 -*-
"""Export Material Thumbnails.

Saves the cached thumbnail image of every material in the project that has one,
named after the material (not the appearance asset). Materials sharing an
appearance asset each get their own copy.

The thumbnail value is read from the appearance asset's rendering asset property
"thumbnail". It may be missing, a "tmp:?" path relative to the Revit temp folder,
or a full path, and can refer to a file from another session or PC that no longer
exists. Those materials are skipped and listed in the report.
"""

import os
import re
import shutil
import tempfile
import traceback

from pyrevit import revit, DB, forms, script

logger = script.get_logger()
output = script.get_output()

THUMBNAIL_PROPERTY = "thumbnail"
TEMP_PREFIX = "tmp:"
INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]+')


def get_thumbnail_value(doc, material):
    """Return the raw thumbnail string of a material, or None if it has none."""
    asset_element = doc.GetElement(material.AppearanceAssetId)
    if not isinstance(asset_element, DB.AppearanceAssetElement):
        return None
    try:
        rendering_asset = asset_element.GetRenderingAsset()
        thumbnail_property = rendering_asset.FindByName(THUMBNAIL_PROPERTY)
        value = thumbnail_property.Value
    except Exception:
        return None
    return value if value else None


def resolve_thumbnail_path(raw_value):
    """Return an existing file path for a raw thumbnail value, or None."""
    if raw_value.lower().startswith(TEMP_PREFIX):
        relative_path = raw_value[len(TEMP_PREFIX) :].lstrip("?")
        path = os.path.join(tempfile.gettempdir(), relative_path)
    else:
        path = raw_value
    return path if os.path.isfile(path) else None


def safe_filename(name):
    return INVALID_FILENAME_CHARS.sub("_", name).strip(" .") or "material"


def unique_destination(folder, name, extension, used_names):
    base = safe_filename(name)
    candidate = base
    counter = 2
    while candidate.lower() in used_names:
        candidate = "{} ({})".format(base, counter)
        counter += 1
    used_names.add(candidate.lower())
    return os.path.join(folder, candidate + extension)


def collect_thumbnails(doc):
    """Return (material name, source path) pairs and the names of those skipped."""
    found = []
    skipped = []
    materials = DB.FilteredElementCollector(doc).OfClass(DB.Material)
    for material in sorted(materials, key=lambda m: m.Name.lower()):
        raw_value = get_thumbnail_value(doc, material)
        path = resolve_thumbnail_path(raw_value) if raw_value else None
        if path:
            found.append((material.Name, path))
        else:
            skipped.append(material.Name)
    return found, skipped


def export_thumbnails(thumbnails, folder):
    used_names = set()
    exported = 0
    for name, source in thumbnails:
        extension = os.path.splitext(source)[1] or ".png"
        destination = unique_destination(folder, name, extension, used_names)
        try:
            shutil.copyfile(source, destination)
            exported += 1
        except Exception:
            logger.error("Could not copy thumbnail for '{}'.".format(name))
            print(traceback.format_exc())
    return exported


def main():
    doc = revit.doc
    folder = forms.pick_folder("Select folder for material thumbnails")
    if not folder:
        script.exit()

    thumbnails, skipped = collect_thumbnails(doc)
    exported = export_thumbnails(thumbnails, folder)

    output.print_md(
        "**{} thumbnails exported** to `{}`. {} materials had no usable thumbnail.".format(
            exported, folder, len(skipped)
        )
    )
    if skipped:
        output.print_md("Skipped materials:")
        for name in skipped:
            print(name)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(traceback.format_exc())
