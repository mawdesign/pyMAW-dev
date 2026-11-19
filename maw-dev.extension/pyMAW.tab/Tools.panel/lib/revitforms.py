# -*- coding: utf-8 -*-
"""Reusable pyRevit forms for material tools."""

# # -------------- Standard Library Imports --------------
import os

# # -------------------- .NET Imports --------------------
from System.Collections.ObjectModel import ObservableCollection

# # ------------------ pyRevit Imports -------------------
from pyrevit import forms


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


class MaterialOption(forms.TemplateListItem):
    """List item showing a material's name."""

    @property
    def name(self):
        return self.item.Name


def select_materials(
    materials, title="Select Materials", button_name="Continue", multiselect=True
):
    """Show a material picker. Returns selected materials, or None if cancelled."""
    return forms.SelectFromList.show(
        [MaterialOption(m) for m in materials],
        multiselect=multiselect,
        title=title,
        button_name=button_name,
    )


def _get_lib_file(filename):
    return os.path.join(os.path.dirname(__file__), filename)


def edit_option_paths(user_paths, default_paths, value_delim="|"):
    """Show the search path editor. Returns edited paths, or None if cancelled."""
    window = SearchPathsWindow(
        _get_lib_file("paths_select.xaml"),
        user_paths,
        default_paths,
        "user",
        value_delim,
    )
    window.ShowDialog()

    return window.Paths
