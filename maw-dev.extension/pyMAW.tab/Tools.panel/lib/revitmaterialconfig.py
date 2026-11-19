# -*- coding: utf-8 -*-
"""Material tool settings and Revit material browser configuration.

Settings come from ``material_settings.json`` beside this module.
Browser configuration is read from and written to MaterialUIConfig.xml.
"""

# # -------------- Standard Library Imports --------------
import json
import os
import xml.etree.ElementTree as ET

# # ------------------ pyRevit Imports -------------------
from pyrevit import HOST_APP

# # ------------------ module imports --------------------
import revitini

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "material_settings.json")
_settings_cache = {}


# ----------------------------------------------------------------------
# Settings file
# ----------------------------------------------------------------------
def load_settings(reload=False):
    """Returns settings dict; empty defaults if the file is missing."""
    if reload or not _settings_cache:
        settings = {"libraries": [], "texture_fallback_paths": []}
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                settings.update(json.load(f))
        _settings_cache.clear()
        _settings_cache.update(settings)
    return _settings_cache


def get_company_libraries():
    """Returns [{"name": str, "file": str}, ...] of admin-configured libraries."""
    return [
        lib for lib in load_settings()["libraries"] if lib.get("name") and lib.get("file")
    ]


def get_texture_fallback_paths():
    """Returns resolved absolute fallback texture folders."""
    paths = [
        revitini.resolve_revit_path(p) for p in load_settings()["texture_fallback_paths"]
    ]
    return [p for p in paths if p]


# ----------------------------------------------------------------------
# MaterialUIConfig.xml
# ----------------------------------------------------------------------
def get_config_paths(source="user"):
    """Returns existing MaterialUIConfig.xml paths.

    source: "user" (%APPDATA%), "appdata" (%PROGRAMDATA%) or "both".
    """
    version = HOST_APP.version
    candidates = []
    if source in ("user", "both"):
        candidates.append(
            os.path.join(
                os.environ.get("APPDATA", ""),
                "Autodesk",
                "Revit",
                "Autodesk Revit {0}".format(version),
                "MaterialUIConfig.xml",
            )
        )
    if source in ("appdata", "both"):
        candidates.append(
            os.path.join(
                os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
                "Autodesk",
                "RVT {0}".format(version),
                "UserDataCache",
                "MaterialUIConfig.xml",
            )
        )
    return [p for p in candidates if os.path.exists(p)]


def xml_get_or_create_libraries_element(parent):
    """Return Libraries element, creating it if required."""
    libraries = parent.find("Libraries")

    if libraries is None:
        libraries = ET.SubElement(parent, "Libraries")

    return libraries


def xml_add_library_element_first(libraries, name, filepath):
    """Add library as first item, removing any existing copy."""
    for lib in list(libraries):
        if lib.tag == "Library" and (
            lib.get("name") == name or lib.get("file") == filepath
        ):
            libraries.remove(lib)

    new_lib = ET.Element("Library")
    new_lib.set("name", name)
    new_lib.set("file", filepath)
    libraries.insert(0, new_lib)


def _first_library_matches(browser, name, path):
    libraries = browser.find("Libraries")
    if libraries is None:
        return False
    lib = libraries.find("Library")
    # Element truthiness is its child count, so compare with None
    return lib is not None and lib.get("name") == name and lib.get("file") == path


def xml_material_library_is_configured(root, name, path, destination):
    """True if the library is already first in the requested browser(s)."""
    material_browser = root.find(".//MaterialBrowser")
    asset_browser = root.find(".//AspectBrowser")

    if destination in ("material", "both"):
        if material_browser is None:
            return False
        if material_browser.get("isLibraryPaneVisible") != "1":
            return False
        if not _first_library_matches(material_browser, name, path):
            return False

    if destination in ("asset", "both"):
        if asset_browser is None:
            return False
        if not _first_library_matches(asset_browser, name, path):
            return False

    return True


def xml_add_material_library(name, path, xml_path, destination):
    """Add a library to one config file. Returns "" or an error message."""
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        if xml_material_library_is_configured(root, name, path, destination):
            return ""  # no change required

        material_browser = root.find(".//MaterialBrowser")
        asset_browser = root.find(".//AspectBrowser")

        if material_browser is not None and destination in ("material", "both"):
            material_browser.set("isLibraryPaneVisible", "1")
            libraries = xml_get_or_create_libraries_element(material_browser)
            xml_add_library_element_first(libraries, name, path)

        if asset_browser is not None and destination in ("asset", "both"):
            libraries = xml_get_or_create_libraries_element(asset_browser)
            xml_add_library_element_first(libraries, name, path)

        tree.write(xml_path, encoding="utf-8", xml_declaration=False)
        return ""
    except Exception as e:
        return "{0}: {1}".format(xml_path, e)


def config_add_material_library(name, path, source="user", destination="both"):
    """Add a material library (.adsklib) to MaterialUIConfig.xml.

    Args:
        name: display name for the library
        path: path to the .adsklib file
        source: "user" (default), "appdata" or "both"
        destination: "material" (material browser), "asset" (asset browser)
            or "both" (default)

    Returns:
        str: error messages, empty if successful
    """
    xml_paths = get_config_paths(source)
    if not xml_paths:
        return "MaterialUIConfig.xml file not found for this user and Revit version"

    errors = [xml_add_material_library(name, path, p, destination) for p in xml_paths]
    return "\n".join(e for e in errors if e)
