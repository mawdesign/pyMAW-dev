# -*- coding: utf-8 -*-
"""Read the Revit.ini file (parsing only; see revitforms for UI)."""

# # -------------- Standard Library Imports --------------
import os
import sys
import codecs
import re

try:
    import configparser  # Python 3 (Revit 2025+)
except ImportError:
    import ConfigParser as configparser  # Python 2 (Revit 2024 and older)  # noqa: N813

# # ------------------ pyRevit Imports -------------------
from pyrevit import HOST_APP


REVIT_EXE_DIR = os.path.dirname(HOST_APP.proc_path)


def resolve_revit_path(raw_path):
    """Convert a raw Revit.ini path (relative or absolute) to a normalised absolute path."""
    if not raw_path:
        return None

    # Remove whitespace
    cleaned_path = raw_path.strip()

    # If Revit saved it as a pure absolute path (starts with a drive letter or UNC),
    # just return it normalized.
    if os.path.isabs(cleaned_path):
        return os.path.normpath(cleaned_path)

    # Combine the Revit.exe folder path with the relative path from the INI.
    # os.path.abspath automatically resolves all the '..' segments correctly.
    return os.path.abspath(os.path.join(REVIT_EXE_DIR, cleaned_path))


def read_revit_ini(ini="user"):
    """Returns the Revit ini file."""
    revit_ver = HOST_APP.version
    user_ini_path = os.path.expandvars(
        "%APPDATA%\\Autodesk\\Revit\\Autodesk Revit {0}\\Revit.ini".format(revit_ver)
    )
    default_ini_path = os.path.expandvars(
        "%ALLUSERSPROFILE%\\Autodesk\\RVT {0}\\UserDataCache\\Revit.ini".format(
            revit_ver
        )
    )
    revit_ini_path = user_ini_path if ini == "user" else default_ini_path

    if not os.path.exists(revit_ini_path):
        return None

    # Determine the Python version
    is_py3 = sys.version_info[0] >= 3

    if is_py3:
        # CPython 3.x (Revit 2025+)
        # strict=False handles duplicate sections
        # delimiters=('=', ':') ensures it tolerates the double '=' issue
        config = configparser.ConfigParser(strict=False, delimiters=("=", ":"))

        # Robust encoding fallback
        try:
            with open(revit_ini_path, "r", encoding="utf-16") as f:
                config.read_file(f)
        except (UnicodeDecodeError, LookupError):
            with open(revit_ini_path, "r", encoding="utf-8-sig") as f:
                config.read_file(f)

        return config

    else:
        # IronPython 2.7 (Revit < 2025)
        config = configparser.ConfigParser()

        # CRITICAL FIX FOR PY2.7: Modify the Option Regular Expression.
        # This forces the parser to split ONLY on the very first '=' or ':',
        # protecting paths like DefaultTemplate=Architecture=C:\...
        config.OPTCRE = re.compile(
            r"(?P<option>[^:=\s][^:=]*)\s*(?P<vi>[:=])\s*(?P<value>.*)$"
        )

        # Robust encoding fallback using codecs (IronPython compatible)
        try:
            with codecs.open(revit_ini_path, "r", encoding="utf-16") as f:
                config.readfp(f)
        except (UnicodeDecodeError, LookupError):
            with codecs.open(revit_ini_path, "r", encoding="utf-8-sig") as f:
                config.readfp(f)

        return config


def get_option(section, option, ini="user"):
    """Returns selected option from selected section."""
    revit_config = read_revit_ini(ini)
    option_value = ""
    if revit_config is None:
        return option_value
    if section in revit_config.sections():
        if revit_config.has_option(section, option):
            # Using .get() is cross-version stable
            option_value = revit_config.get(section, option)
    return option_value


def get_option_list(section, option, value_delim="|", ini="user"):
    """Returns dict of values within an option."""
    option_value = get_option(section, option, ini=ini)
    option_list = [v for v in option_value.split(value_delim) if v]
    return option_list


def get_option_paths(section, option, value_delim="|", ini="user"):
    """Returns list of resolved absolute paths held in an option."""
    raw_paths = get_option_list(section, option, value_delim=value_delim, ini=ini)
    paths = [resolve_revit_path(path) for path in raw_paths if path]
    return [p for p in paths if p]
