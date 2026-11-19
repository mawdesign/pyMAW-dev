# -*- coding: utf-8 -*-
"""Revit material helpers: retrieval, usage, appearance assets and texture paths."""

# # -------------- Standard Library Imports --------------
import os
import timeit
from collections import defaultdict

# # ------------------ pyRevit Imports -------------------
from pyrevit import revit
from pyrevit import DB

# # ------------------ module imports --------------------
import revitmaterialconfig
import revitini

# Globals
usage_cache = defaultdict(lambda: {"count": 0, "area": 0.0, "volume": 0.0})

# System and Revit Folders
COMMONPROGRAMFILES = os.environ.get(
    "CommonProgramFiles", r"C:\Program Files\Common Files"
)
COMMONPROGRAMFILESX86 = os.environ.get(
    "CommonProgramFiles(x86)", r"C:\Program Files (x86)\Common Files"
)
AUTODESK_TEXTURE_FOLDER = os.path.join("Autodesk Shared", "Materials", "Textures")
AUTODESK_TEXTURE_PATH = os.path.join(COMMONPROGRAMFILES, AUTODESK_TEXTURE_FOLDER)


def _build_material_usage_cache(doc):
    """Sets usage_cache to:

    {
        materialId.IntegerValue: {
            'count': int,
            'area': float,    # m²
            'volume': float   # m³
        }
    }.
    """
    usage_cache.clear()
    elements = (
        DB.FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements()
    )

    for elem in elements:
        try:
            mat_ids = elem.GetMaterialIds(False)

            if not mat_ids:
                continue

            for mat_id in mat_ids:
                key = get_element_id_value(mat_id)
                usage_cache[key]["count"] += 1

                # Area
                try:
                    area = elem.GetMaterialArea(mat_id, False)

                    area_m2 = DB.UnitUtils.ConvertFromInternalUnits(
                        area, DB.UnitTypeId.SquareMeters
                    )
                    usage_cache[key]["area"] += area_m2
                except Exception:
                    pass

                # Volume
                try:
                    volume = elem.GetMaterialVolume(mat_id)

                    volume_m3 = DB.UnitUtils.ConvertFromInternalUnits(
                        volume, DB.UnitTypeId.CubicMeters
                    )
                    usage_cache[key]["volume"] += volume_m3
                except Exception:
                    pass

        except Exception:
            pass
    return


NO_PATTERN = "<none>"


# ----------------------------------------------------------------------
# Element ids
# ----------------------------------------------------------------------
def get_element_id_value(element_id):
    """Integer value of an ElementId (``.Value`` from Revit 2024, else ``.IntegerValue``)."""
    try:
        return element_id.Value
    except AttributeError:
        return element_id.IntegerValue


def is_valid_id(element_id):
    """True if element_id is set and not ElementId.InvalidElementId."""
    return bool(element_id) and element_id != DB.ElementId.InvalidElementId


# ----------------------------------------------------------------------
# Retrieval
# ----------------------------------------------------------------------
def get_materials(doc, sort=True):
    """Returns all materials in the document, sorted by name unless sort=False."""
    materials = list(DB.FilteredElementCollector(doc).OfClass(DB.Material))
    if sort:
        materials.sort(key=lambda m: m.Name.lower())
    return materials


def get_materials_by_name(doc):
    """Returns {material name: Material}."""
    return {m.Name: m for m in get_materials(doc, sort=False)}


def get_fill_patterns_by_name(doc):
    """Returns {pattern name: ElementId}."""
    patterns = DB.FilteredElementCollector(doc).OfClass(DB.FillPatternElement)
    return {p.Name: p.Id for p in patterns}


def get_pattern_name(doc, pattern_id):
    """Fill pattern name for an id; NO_PATTERN if unset."""
    try:
        if is_valid_id(pattern_id):
            pat = doc.GetElement(pattern_id)
            if pat:
                return pat.Name
    except Exception as e:
        return "Error: {}".format(e)

    return NO_PATTERN


def get_pattern_id(pattern_name, pattern_lookup):
    """Reciprocal of get_pattern_name; pattern_lookup from get_fill_patterns_by_name."""
    if not pattern_name or pattern_name == NO_PATTERN:
        return DB.ElementId.InvalidElementId
    return pattern_lookup.get(pattern_name, DB.ElementId.InvalidElementId)


# ----------------------------------------------------------------------
# Material properties
# ----------------------------------------------------------------------
def get_material_text(material, bip):
    """String value of a built-in parameter; "" if the parameter is missing."""
    param = material.get_Parameter(bip)
    return (param.AsString() or "") if param else ""


def set_material_text(material, bip, value):
    """Set a built-in parameter. Returns True if set."""
    param = material.get_Parameter(bip)
    if not param or param.IsReadOnly:
        return False
    try:
        return bool(param.Set(value))
    except Exception:
        return False


def get_transparency(material):
    """Transparency as a fraction 0-1."""
    param = material.get_Parameter(DB.BuiltInParameter.MATERIAL_PARAM_TRANSPARENCY)
    return param.AsInteger() / 100.0 if param else 0.0


def set_transparency(material, fraction):
    """Reciprocal of get_transparency. Returns True if set."""
    return set_material_text(
        material,
        DB.BuiltInParameter.MATERIAL_PARAM_TRANSPARENCY,
        int(round(float(fraction) * 100)),
    )


def is_material_parameter(param):
    """True if a family parameter is a Material reference (Revit 2021+)."""
    try:
        return param.Definition.GetDataType() == DB.SpecTypeId.Reference.Material
    except AttributeError:  # Revit 2021
        return param.Definition.ParameterType == DB.ParameterType.Material


# ----------------------------------------------------------------------
# Usage
# ----------------------------------------------------------------------
def build_usage_cache(doc):
    """Fill usage_cache for all materials in use. Call before get_material_usage."""
    _build_material_usage_cache(doc)


def get_material_usage(material):
    """Returns (count, area m2, volume m3) from the usage cache."""
    data = usage_cache.get(get_element_id_value(material.Id), None)

    if not data:
        return 0, 0.0, 0.0

    return (data["count"], data["area"], data["volume"])


def find_material_users(doc, material, limit=5):
    """Returns up to ``limit`` ElementIds (as strings) of elements using the material.

    Checks placed instances (geometry, layers, painted faces) then element types,
    stopping early.
    """
    target_id = material.Id
    found = []

    for el in DB.FilteredElementCollector(doc).WhereElementIsNotElementType():
        if not el.Category:
            continue
        if target_id in el.GetMaterialIds(False) or target_id in el.GetMaterialIds(True):
            found.append(el.Id.ToString())
            if len(found) >= limit:
                return found

    for el_type in DB.FilteredElementCollector(doc).WhereElementIsElementType():
        if target_id in el_type.GetMaterialIds(False):
            found.append(el_type.Id.ToString())
            if len(found) >= limit:
                return found

    return found


# ----------------------------------------------------------------------
# Appearance assets
# ----------------------------------------------------------------------
def get_asset(doc, material, asset_type="appearance"):
    """Returns {"id": ElementId or None, "name": str} for the material's asset."""
    asset_data = {"id": None, "name": ""}
    if asset_type != "appearance":
        asset_data["name"] = "Error: Only appearance assets implemented"
        return asset_data
    try:
        asset_id = material.AppearanceAssetId

        if is_valid_id(asset_id):
            asset = doc.GetElement(asset_id)

            if asset:
                asset_data["id"] = asset_id
                asset_data["name"] = asset.Name
                return asset_data

    except Exception as e:
        asset_data["name"] = "Error: {}".format(e)
        return asset_data

    asset_data["name"] = "Generic"
    return asset_data


def duplicate_appearance_asset(doc, material, asset_name):
    """Duplicate the material's appearance asset. Returns the new asset, or None."""
    if not is_valid_id(material.AppearanceAssetId):
        return None

    try:
        return doc.GetElement(material.AppearanceAssetId).Duplicate(asset_name)
    except Exception:
        return None


def set_asset_colour(doc, asset_id, colour):
    """Set the generic diffuse colour of an appearance asset. Returns True if set."""
    if not is_valid_id(asset_id):
        return False

    edit_scope = DB.Visual.AppearanceAssetEditScope(doc)

    try:
        asset = edit_scope.Start(asset_id)
        prop = asset.FindByName(DB.Visual.Generic.GenericDiffuse)
        if prop:
            prop.SetValueAsColor(colour)
        edit_scope.Commit(True)
        return bool(prop)
    except Exception as e:
        print(str(e))
        try:
            edit_scope.Cancel()
        except Exception:
            pass
        return False


def get_asset_colour(doc, asset_id):
    """Reciprocal of set_asset_colour. Returns DB.Color, or None."""
    if not is_valid_id(asset_id):
        return None

    asset_elem = doc.GetElement(asset_id)
    if not asset_elem:
        return None

    prop = asset_elem.GetRenderingAsset().FindByName(DB.Visual.Generic.GenericDiffuse)
    return prop.GetValueAsColor() if prop else None


# ----------------------------------------------------------------------
# Texture search paths
# ----------------------------------------------------------------------
def get_material_search_paths(ini="user"):
    """Returns ordered list of material search paths (strings)."""
    # potentially also:
    # C:\Program Files (x86)\Common Files\Autodesk Shared\Materials\Textures\1\Mats\
    # (and ...\2\Mats, ...\3\Mats)
    return [AUTODESK_TEXTURE_PATH] + revitini.get_option_paths(
        "Directories", "AdditionalRenderAppearancePaths", ini=ini
    )


def resolve_material_image_path(raw_path, texture_paths, fallback_roots=None):
    """Resolve a material image path using Revit-like logic.

    Args:
        raw_path (str):
            Raw path extracted from the material asset.
        texture_paths (list[str]):
            Fully resolved absolute search locations.
            Includes AdditionalRenderPaths and any company libraries.
        fallback_roots (list[str], optional):
            Extra absolute folders searched last (method "Ini Fix"),
            e.g. a library folder missing from Revit.ini.

    Returns:
        (
            resolved_path,      # str | None
            resolution_method,  # str
            elapsed_ms          # float
        )
    """
    start = timeit.default_timer()

    def finish(path, method):
        return (path, method, round((timeit.default_timer() - start) * 1000.0, 2))

    if not raw_path:
        return finish(None, "Empty")

    #
    # Normalise separators
    #
    path = raw_path.strip()
    path = os.path.normpath(path)

    #
    # 1. Exact match
    #
    if os.path.exists(path):
        return finish(path, "Exact")

    #
    # 2. Autodesk legacy path fix
    #
    idx = path.lower().find(AUTODESK_TEXTURE_FOLDER.lower())

    if idx >= 0:
        rel_path = path[idx + len(AUTODESK_TEXTURE_FOLDER) :]
        rel_path = rel_path.lstrip("\\/")
        candidate = os.path.join(AUTODESK_TEXTURE_PATH, rel_path)
        candidate = os.path.normpath(candidate)

        if os.path.exists(candidate):
            return finish(candidate, "Autodesk Legacy Fix")

    #
    # 3. Relative Autodesk path
    #
    if not os.path.isabs(path):
        candidate = os.path.normpath(os.path.join(AUTODESK_TEXTURE_PATH, path))

        if os.path.exists(candidate):
            return finish(candidate, "Autodesk Relative")

    #
    # 4. General relative path search
    #
    if not os.path.isabs(path):
        for root in texture_paths:
            candidate = os.path.normpath(os.path.join(root, path))

            if os.path.exists(candidate):
                return finish(candidate, "Search Path")

    #
    # 5. Filename search
    #
    if os.path.basename(path) != path:
        filename = os.path.basename(path)

        for root in texture_paths:
            candidate = os.path.normpath(os.path.join(root, filename))

            if os.path.exists(candidate):
                return finish(candidate, "Filename Search")

    #
    # 5b. Revit.ini fix
    #
    if not os.path.isabs(path):
        for root in fallback_roots or []:
            candidate = os.path.normpath(os.path.join(root, path))

            if os.path.exists(candidate):
                return finish(candidate, "Ini Fix")

    #
    # 6. Missing
    #
    return finish("<not found>", "Missing")


def make_relative_material_path(resolved_path, preferred_paths):
    """Returns path relative to first matching preferred library."""
    if not resolved_path:
        return ""

    resolved = os.path.normpath(resolved_path)

    for root in preferred_paths:
        root = os.path.normpath(root)

        if resolved.lower().startswith(root.lower()):
            rel = resolved[len(root) :]
            return rel.lstrip("\\/")

    return resolved_path


def classify_paths(path_data, preferred_paths, prefer_relative=True):
    """Add classification information to material texture records.

    Parameters.
    ----------
    path_data : list(dict)
        Output from get_material_texture_paths()
    preferred_paths : list(str)
        Preferred material library locations.
    prefer_relative : bool
        If True:
            relative paths are preferred over absolute paths.
        If False:
            both relative and absolute paths inside preferred
            locations are considered acceptable.

    Returns:
    -------
    list(dict)
    Adds:
        in_preferred      bool
        severity          int
        status            str
    """
    normalised_preferred = []

    for path in preferred_paths:
        if not path:
            continue
        normalised_preferred.append(os.path.normcase(os.path.normpath(path)))

    for item in path_data:
        method = item.get("method", "")
        stored_path = item.get("path", "") or ""
        resolved_path = item.get("resolved_path", "") or ""

        #
        # Check whether resolved file is inside
        # a preferred library location.
        #
        in_preferred = False

        if resolved_path:
            resolved = os.path.normcase(os.path.normpath(resolved_path))
            for preferred in normalised_preferred:
                if resolved.startswith(preferred):
                    in_preferred = True
                    break

        #
        # Determine whether stored path is relative.
        #
        is_relative = bool(stored_path) and not os.path.isabs(stored_path)

        #
        # Defaults
        #
        severity = 2
        status = "problem"

        #
        # Missing always highest severity
        #
        if method == "Missing":
            severity = 2
            status = "missing"

        #
        # Filename matches are suspicious
        #
        elif method == "Filename Search":
            severity = 2
            status = "filename_search"

        #
        # Legacy Autodesk mapping
        #
        elif method == "Autodesk Legacy Fix":
            severity = 1
            status = "legacy"

        #
        # Found via configured path search
        #
        elif method in ("Search Path", "Ini Fix"):
            if in_preferred:
                if prefer_relative:
                    if is_relative:
                        severity = 0
                        status = "preferred"
                    else:
                        severity = 1
                        status = "absolute"
                else:
                    severity = 0
                    status = "preferred"
            else:
                severity = 2
                status = "outside_library"

        #
        # Exact path or Autodesk relative path
        #
        elif method in ("Exact", "Autodesk Relative"):
            if in_preferred:
                if prefer_relative:
                    if is_relative:
                        severity = 0
                        status = "preferred"

                    else:
                        severity = 1
                        status = "absolute"

                else:
                    severity = 0
                    status = "preferred"

            else:
                severity = 2
                status = "outside_library"

        #
        # Anything unexpected
        #
        else:
            severity = 2
            status = "unknown"

        item["in_preferred"] = in_preferred
        item["severity"] = severity
        item["status"] = status
    return path_data


def get_material_texture_paths(
    material, doc, texture_paths=None, ini="user", fallback_roots=None
):
    paths = []
    seen_paths = set()
    if not texture_paths:
        texture_paths = get_material_search_paths(ini)
    if fallback_roots is None:
        fallback_roots = revitmaterialconfig.get_texture_fallback_paths()

    asset_id = material.AppearanceAssetId

    if asset_id == DB.ElementId.InvalidElementId:
        return []

    asset_elem = doc.GetElement(asset_id)

    if not asset_elem:
        return []

    asset = asset_elem.GetRenderingAsset()

    for i in range(asset.Size):
        prop = asset[i]

        try:
            if prop.NumberOfConnectedProperties < 1:
                continue

            connected = prop.GetConnectedProperty(0)
            bitmap_prop = connected.FindByName(
                DB.Visual.UnifiedBitmap.UnifiedbitmapBitmap
            )

            if bitmap_prop:
                for raw_path in bitmap_prop.Value.split("|"):
                    if raw_path and (prop.Name + ":" + raw_path) not in seen_paths:
                        seen_paths.add(
                            prop.Name + ":" + raw_path
                        )  # Track that we've seen this path
                        resolved_path, method, elapsed_ms = resolve_material_image_path(
                            raw_path, texture_paths, fallback_roots
                        )
                        paths.append(
                            {
                                "id": asset_id,
                                "material_name": material.Name,
                                "usage": prop.Name,
                                "path": raw_path,
                                "resolved_path": resolved_path,
                                "method": method,
                                "time": elapsed_ms,
                            }
                        )

        except Exception as e:
            print(str(e))

    return paths


def update_asset_name(doc, asset_id, new_name):
    """Returns True if asset is updated."""
    if asset_id == DB.ElementId.InvalidElementId:
        return False

    asset_elem = doc.GetElement(asset_id)

    if not asset_elem:
        return False

    with revit.Transaction("Rename Appearance Asset"):
        edit_scope = DB.Visual.AppearanceAssetEditScope(doc)
        try:
            edit_scope.Start(asset_id)

            asset_elem.Name = new_name

            edit_scope.Commit(False)
            return True

        except Exception as e:
            print(str(e))
            try:
                edit_scope.Cancel()
            except Exception:
                pass

    return False


def update_asset_path(doc, asset_id, old_path, new_path):
    """Returns True if asset is updated."""
    if asset_id == DB.ElementId.InvalidElementId:
        return False

    asset_elem = doc.GetElement(asset_id)

    if not asset_elem:
        return False

    edit_scope = DB.Visual.AppearanceAssetEditScope(doc)
    asset = edit_scope.Start(asset_id)
    any_updated = False

    try:
        for i in range(asset.Size):
            prop = asset[i]

            try:
                if prop.NumberOfConnectedProperties < 1:
                    continue

                connected = prop.GetConnectedProperty(0)
                bitmap_prop = connected.FindByName(
                    DB.Visual.UnifiedBitmap.UnifiedbitmapBitmap
                )
                if not bitmap_prop:
                    continue

                updated = False
                updated_paths = []
                for raw_path in bitmap_prop.Value.split("|"):
                    if raw_path and raw_path == old_path:
                        updated_paths.append(new_path)
                        updated = True
                    elif raw_path:
                        updated_paths.append(raw_path)

                if updated:
                    updated_path = "|".join(updated_paths)
                    if bitmap_prop.IsValidValue(updated_path):
                        bitmap_prop.Value = updated_path
                        any_updated = True

            except Exception as e:
                print(str(e))

        if any_updated:
            edit_scope.Commit(False)
        else:
            edit_scope.Cancel()
    except Exception as e:
        print(str(e))
        any_updated = False
        try:
            edit_scope.Cancel()
        except Exception:
            pass

    return any_updated


