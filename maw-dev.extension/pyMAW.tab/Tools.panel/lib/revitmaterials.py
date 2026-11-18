# -*- coding: utf-8 -*-
"""Materials Management Tools."""

# # -------------- Standard Library Imports --------------
import os
import timeit
from collections import defaultdict
import xml.etree.ElementTree as ET

# # ------------------ pyRevit Imports -------------------
from pyrevit import revit
from pyrevit import DB

# # ------------------ module imports --------------------
import revitini

# GET REVIT TEMP PATH
# -------------------
# from pathlib import Path
# import tempfile
# REVITTEMP = Path(tempfile.gettempdir())
# print(REVITTEMP) # since 2019 has a GUID at the end of environment TMP value
#
# GET MATERIAL THUMBNAIL
# ----------------------
# Appearance asset > render asset > find by name (string) > thumbnail
# e.g. "tmp:?MaterialThumbnails_PID_6d48\237ea2532c0Metal_Roofing_Trapezoidal(3).png"
# replace "tmp:?" with REVITTEMP

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
    elements = (
        DB.FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements()
    )

    for elem in elements:
        try:
            mat_ids = elem.GetMaterialIds(False)

            if not mat_ids:
                continue

            for mat_id in mat_ids:
                key = mat_id.IntegerValue
                usage_cache[key]["count"] += 1

                # Area
                try:
                    area = elem.GetMaterialArea(mat_id, False)

                    area_m2 = DB.UnitUtils.ConvertFromInternalUnits(
                        area, DB.UnitTypeId.SquareMeters
                    )
                    usage_cache[key]["area"] += area_m2
                except:
                    pass

                # Volume
                try:
                    volume = elem.GetMaterialVolume(mat_id)

                    volume_m3 = DB.UnitUtils.ConvertFromInternalUnits(
                        volume, DB.UnitTypeId.CubicMeters
                    )
                    usage_cache[key]["volume"] += volume_m3
                except:
                    pass

        except:
            pass
    return


def get_pattern_name(doc, pattern_id):
    try:
        if pattern_id and pattern_id != DB.ElementId.InvalidElementId:
            pat = doc.GetElement(pattern_id)
            if pat:
                return pat.Name
    except Exception as e:
        return "Error: {}".format(e)

    return "<none>"


def get_asset(doc, material, asset_type="appearance"):
    asset_data = {"id": None, "name": ""}
    if asset_type != "appearance":
        asset_data["name"] = "Error: Only appearance assets implemented"
        return asset_data
    try:
        asset_id = material.AppearanceAssetId

        if asset_id and asset_id != DB.ElementId.InvalidElementId:
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


def get_material_usage(material):
    data = usage_cache.get(material.Id.IntegerValue, None)

    if not data:
        return 0, 0.0, 0.0

    return (data["count"], data["area"], data["volume"])


def get_material_search_paths(ini="user"):
    """Returns:

    [
        ordered list of material search paths: string
    ].
    """
    global texture_paths

    texture_paths = [AUTODESK_TEXTURE_PATH]
    # potentially also:
    # C:\Program Files (x86)\Common Files\Autodesk Shared\Materials\Textures\1\Mats\
    # C:\Program Files (x86)\Common Files\Autodesk Shared\Materials\Textures\2\Mats\
    # C:\Program Files (x86)\Common Files\Autodesk Shared\Materials\Textures\3\Mats\

    texture_paths += revitini.get_option_paths(
        "Directories", "AdditionalRenderAppearancePaths", ini=ini
    )

    return texture_paths


def resolve_material_image_path(raw_path, texture_paths):
    """Resolve a material image path using Revit-like logic.

    Args:
        raw_path (str):
            Raw path extracted from the material asset.
        texture_paths (list[str]):
            Fully resolved absolute search locations.
            Includes AdditionalRenderPaths and any company libraries.

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
    missing_ini = revitini.resolve_revit_path(
        "..\\..\\..\\_CAD\\_Revit\\Library\\_Data\Revit Materials Assets\\"
    )
    candidate = os.path.normpath(os.path.join(missing_ini, path))

    if os.path.exists(candidate):
        return finish(candidate, "Ini Fix")

    #
    # 6. Missing
    #
    return finish("<not found>", "Missing")


import os


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


def get_material_texture_paths(material, doc, texture_paths=None, ini="user"):
    paths = []
    seen_paths = set()
    if not texture_paths:
        texture_paths = get_material_search_paths(ini)

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
                            raw_path, texture_paths
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


def get_materials(doc):
    try:
        materials = DB.FilteredElementCollector(doc).OfClass(DB.Material).ToElements()
        _build_material_usage_cache(doc)
        return materials
    except Exception:
        # failed to get materials
        return None


def update_asset_name(doc, asset_id, new_name):
    """Returns True if asset is updated."""
    if asset_id == DB.ElementId.InvalidElementId:
        return False

    asset_elem = doc.GetElement(asset_id)

    if not asset_elem:
        return False

    with revit.Transaction("Rename Appearance Asset"):
        try:
            edit_scope = DB.Visual.AppearanceAssetEditScope(doc)
            edit_scope.Start(asset_id)

            asset_elem.Name = new_name

            edit_scope.Commit(False)
            return True

        except Exception as e:
            print(str(e))

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

    for i in range(asset.Size):
        prop = asset[i]

        try:
            if prop.NumberOfConnectedProperties < 1:
                continue

            connected = prop.GetConnectedProperty(0)
            bitmap_prop = connected.FindByName(
                DB.Visual.UnifiedBitmap.UnifiedbitmapBitmap
            )
            updated = False

            if bitmap_prop:
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
                    edit_scope.Commit(False)
                    return True

        except Exception as e:
            print(str(e))

    return False


def xml_get_or_create_libraries_element(parent):
    """Return Libraries element, creating it if required."""
    libraries = parent.find("Libraries")

    if libraries is None:
        libraries = ET.SubElement(parent, "Libraries")

    return libraries


def xml_add_library_element_first(libraries, name, filepath):
    """Add library as first item, removing any existing copy."""
    # Remove existing entries with same path or name
    for lib in list(libraries):
        if lib.tag == "Library" and (
            lib.get("name") == name or lib.get("file") == filepath
        ):
            libraries.remove(lib)

    # Create new entry
    new_lib = ET.Element("Library")
    new_lib.set("name", name)
    new_lib.set("file", filepath)

    # Insert at beginning
    libraries.insert(0, new_lib)


def xml_material_library_is_configured(root, name, path, destination):
    material_browser = root.find(".//MaterialBrowser")

    if material_browser is None:
        return False

    if destination in ["material", "both"]:
        if material_browser.get("isLibraryPaneVisible") != "1":
            return False

        libraries = material_browser.find("Libraries")
        if libraries is None:
            return False

        lib = libraries.find("Library")
        if not lib:
            return False
        if lib.get("name") != name:
            return False
        if lib.get("file") != path:
            return False

    asset_browser = root.find(".//AspectBrowser")

    if asset_browser is None:
        return False

    if destination in ["asset", "both"]:
        libraries = asset_browser.find("Libraries")
        if libraries is None:
            return False

        lib = libraries.find("Library")
        if not lib:
            return False
        if lib.get("name") != name:
            return False
        if lib.get("file") != path:
            return False

    return True


def xml_add_material_library(name, path, xml_path, destination):
    """Add a material library to list of material or asset libraries."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    material_browser = root.find(".//MaterialBrowser")
    asset_browser = root.find(".//AspectBrowser")

    if xml_material_library_is_configured(root, name, path, destination):
        return ""  # no change required

    try:
        if material_browser is not None and destination in ["material", "both"]:
            material_browser.set("isLibraryPaneVisible", "1")
            libraries = xml_get_or_create_libraries_element(material_browser)
            xml_add_library_element_first(libraries, name, path)

        if asset_browser is not None and destination in ["asset", "both"]:
            libraries = xml_get_or_create_libraries_element(asset_browser)
            xml_add_library_element_first(libraries, name, path)

        tree.write(xml_path, encoding="utf-8", xml_declaration=False)
        return ""
    except Exception as e:
        return e


def config_add_material_library(name, path, source="user", destination="both"):
    """Adds a material library (.adsklib) to the MaterialUIConfig.xml.

    Parameters.
    ----------
    name: display name for the library
    path: path to the library
    source:  "user" (default), "appdata", or "both"
    destination: material = material browser
                 asset    = asset browser
                 both     = add to both (default)

    Returns:
    -------
    True if successful
    """
    version = __revit__.Application.VersionNumber
    errors = ""

    xml_paths = []
    if source in ["user", "both"]:
        xml_path = r"C:\Users\%USERNAME%\AppData\Roaming\Autodesk\Revit\Autodesk Revit {}\MaterialUIConfig.xml".format(
            version
        )
        xml_path = os.path.expandvars(xml_path)
        if os.path.exists(xml_path):
            xml_paths.append(xml_path)

    if source in ["appdata", "both"]:
        xml_path = (
            r"C:\ProgramData\Autodesk\RVT {}\UserDataCache\MaterialUIConfig.xml".format(
                version
            )
        )
        xml_path = os.path.expandvars(xml_path)
        if os.path.exists(xml_path):
            xml_paths.append(xml_path)

    if len(xml_paths) == 0:  # No path found counts as a fail
        return "MaterialUIConfig.xml file not found for this user and Revit version"

    for p in xml_paths:
        errors += "\n" + xml_add_material_library(name, path, p, destination)

    return errors.strip()
