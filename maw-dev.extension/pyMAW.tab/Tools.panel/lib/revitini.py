# -*- coding: utf-8 -*-
"""Access Revit ini file."""

# # -------------- Standard Library Imports --------------
import os
import sys
import codecs
import re

try:
    import configparser  # Python 3 (Revit 2025+)
except ImportError:
    import ConfigParser as configparser  # Python 2 (Revit 2024 and older)  # noqa: N813
from System.Collections.ObjectModel import ObservableCollection

# # ------------------ pyRevit Imports -------------------
from pyrevit import HOST_APP
from pyrevit import forms


REVIT_EXE_DIR = os.path.dirname(HOST_APP.proc_path)


class FormPathItem(object):
    def __init__(self, path=""):
        self.Selected = False
        self.Path = path


class SearchPathsWindow(forms.WPFWindow):
    def __init__(self, xaml_file, user_paths, default_paths, ini, value_delim):

        forms.WPFWindow.__init__(self, xaml_file)

        self.rows = ObservableCollection[FormPathItem]()
        self.user_paths = user_paths
        self.default_paths = default_paths
        paths = user_paths if ini == "user" else default_paths
        self.load_paths(paths)
        self.dgPaths.ItemsSource = self.rows
        self.delimiter = value_delim
        self.Paths = None

        self.btnDefaultIni.Click += self.btnDefaultIni_Click
        self.btnUserIni.Click += self.btnUserIni_Click
        self.btnOK.Click += self.btnOK_Click
        self.btnCancel.Click += self.btnCancel_Click

        self.dgPaths.CellEditEnding += self.dgPaths_CellEditEnding

    def load_paths(self, paths):
        self.rows.Clear()
        for path in paths:
            if path.strip():
                self.rows.Add(FormPathItem(path))
        self.ensure_blank_row()

    def ensure_blank_row(self):
        if self.rows.Count == 0:
            self.rows.Add(FormPathItem())
            return
        if self.rows[self.rows.Count - 1].Path.strip():
            self.rows.Add(FormPathItem())

    def dgPaths_CellEditEnding(self, sender, args):
        """Adds new blank row after row edited.

        Splits entered text into rows by the delimiter.
        """
        text = args.EditingElement.Text
        if not self.delimiter or self.delimiter not in text:
            self.ensure_blank_row()
            return

        parts = [p.strip() for p in text.split(self.delimiter) if p.strip()]
        if len(parts) < 2:
            self.ensure_blank_row()
            return

        row = args.Row.Item
        row.Path = parts[0]
        insert_after = self.rows.IndexOf(row)
        for i, path in enumerate(parts[1:]):
            self.rows.Insert(insert_after + i + 1, FormPathItem(path))
        self.ensure_blank_row()

    def DeleteRow_Click(self, sender, args):
        row = sender.Tag
        self.rows.Remove(row)
        self.ensure_blank_row()

    def BrowseRow_Click(self, sender, args):
        row = sender.DataContext
        if not row:
            return

        folder = forms.pick_folder()
        if folder:
            row.Path = folder
            self.dgPaths.CommitEdit()
            self.dgPaths.Items.Refresh()
            self.ensure_blank_row()

    def btnUserIni_Click(self, sender, args):
        self.load_paths(self.user_paths)

    def btnDefaultIni_Click(self, sender, args):
        self.load_paths(self.default_paths)

    def btnOK_Click(self, sender, args):
        self.Paths = []
        for row in self.rows:
            path = row.Path.strip()
            if os.path.exists(path):
                self.Paths.append(os.path.normpath(path))
        self.DialogResult = True
        self.Close()

    def btnCancel_Click(self, sender, args):
        self.Paths = None
        self.Close()


def _get_lib_file(filename):
    return os.path.join(os.path.dirname(__file__), filename)


def resolve_revit_path(raw_path):
    """Takes a raw path string from Revit.ini (relative or absolute) and converts it into a clean, normalized absolute path."""
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
    sections = revit_config.sections()
    option_value = ""
    if section in sections:
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
    raw_paths = get_option_list(section, option, value_delim="|", ini=ini)
    paths = [resolve_revit_path(path) for path in raw_paths if path]
    return paths


def edit_option_paths(user_paths, default_paths, value_delim="|"):
    window = SearchPathsWindow(
        _get_lib_file("paths_select.xaml"),
        user_paths,
        default_paths,
        "user",
        value_delim,
    )
    window.ShowDialog()

    return window.Paths
