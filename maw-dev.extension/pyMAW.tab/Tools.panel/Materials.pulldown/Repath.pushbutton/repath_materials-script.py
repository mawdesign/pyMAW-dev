# -*- coding: utf-8 -*-
"""Repath Material Image Assets allows optional repathing to relative paths."""

# # -------------- Standard Library Imports --------------
import traceback
import clr

clr.AddReference("PresentationFramework")
import System.Windows

# # ------------------ pyRevit Imports -------------------
from pyrevit import forms, script
from pyrevit import revit

# # ------------------ module imports --------------------
import revitini
import revitmaterials

SEVERITY_SYMBOLS = {
    0: "✓",
    1: "!",
    2: "⚠",  # same as Revit error in materials dialog
}

SEVERITY_COLOURS = {
    0: "#C6EFCE",  # Excel-style pale green
    1: "#FFEB9C",  # Excel-style pale yellow
    2: "#FF0000",  # same as Revit error in materials dialog
}


class RepathItem(object):
    def __init__(
        self,
        selected,
        asset_id,
        severity,
        material_name,
        usage,
        current_path,
        resolved_path,
        relative_path,
        method,
    ):

        self.Selected = selected
        self.Id = asset_id
        self.Severity = severity
        self.StatusIcon = SEVERITY_SYMBOLS[severity]
        self.StatusColour = SEVERITY_COLOURS[severity]
        self.ResolvedPathColour = (
            "#C0C0C0" if resolved_path == current_path else "#000000"
        )
        self.RelativePathColour = (
            "#C0C0C0" if relative_path == current_path else "#000000"
        )
        self.MaterialName = material_name
        self.Usage = usage
        self.CurrentPath = current_path
        self.ProposedPath = relative_path
        self.ResolvedPath = resolved_path
        self.RelativePath = relative_path
        self.Method = method


class RepathWindow(forms.WPFWindow):
    def __init__(self, xaml_file, rows):
        forms.WPFWindow.__init__(self, xaml_file)

        self.rows = rows
        self.result = False
        self.hide_unselected = False
        self.dgItems.ItemsSource = self.rows

        self.PathType = "relative"
        self.colRelativePath = self.dgItems.Columns[6]
        self.colFullPath = self.dgItems.Columns[5]
        self.rbRelative.Checked += self.rbRelative_Checked
        self.rbFull.Checked += self.rbFull_Checked

        self.btnAll.Click += self.btnAll_Click
        self.btnNone.Click += self.btnNone_Click
        self.btnAmber.Click += self.btnAmber_Click
        self.btnRed.Click += self.btnRed_Click
        self.btnHideUnselected.Click += self.btnHideUnselected_Click
        self.btnOK.Click += self.btnOK_Click
        self.btnCancel.Click += self.btnCancel_Click

    def refresh_grid(self):
        if self.hide_unselected:
            self.dgItems.ItemsSource = [r for r in self.rows if r.Selected]
        else:
            self.dgItems.ItemsSource = self.rows
        self.dgItems.Items.Refresh()

    # def RowSelectionChanged(self, sender, args):
    # selected_count = len([
    # r for r in self.rows
    # if r.Selected
    # ])

    # if self.hide_unselected:
    # self.refresh_grid()

    def btnAll_Click(self, sender, args):
        for row in self.rows:
            row.Selected = True
        self.refresh_grid()

    def btnNone_Click(self, sender, args):
        for row in self.rows:
            row.Selected = False
        self.refresh_grid()

    def btnAmber_Click(self, sender, args):
        for row in self.rows:
            row.Selected = row.Severity == 1
        self.refresh_grid()

    def btnRed_Click(self, sender, args):
        for row in self.rows:
            row.Selected = row.Severity == 2
        self.refresh_grid()

    def btnHideUnselected_Click(self, sender, args):
        self.dgItems.CommitEdit()
        self.dgItems.CommitEdit()
        self.hide_unselected = not self.hide_unselected
        self.btnHideUnselected.Content = (
            "Show All" if self.hide_unselected else "Hide Unselected"
        )
        self.refresh_grid()

    def rbRelative_Checked(self, sender, args):
        self.colRelativePath.Visibility = System.Windows.Visibility.Visible
        self.colFullPath.Visibility = System.Windows.Visibility.Collapsed
        self.PathType = "relative"

    def rbFull_Checked(self, sender, args):
        self.colRelativePath.Visibility = System.Windows.Visibility.Collapsed
        self.colFullPath.Visibility = System.Windows.Visibility.Visible
        self.PathType = "full"

    def btnOK_Click(self, sender, args):
        # set ProposedPath from full or relative
        for row in self.rows:
            if self.PathType == "relative":
                row.ProposedPath = row.RelativePath
            else:
                row.ProposedPath = row.ResolvedPath
        self.DialogResult = True
        self.result = True
        self.Close()

    def btnCancel_Click(self, sender, args):
        self.result = False
        self.Close()


def repath_materials():
    doc = revit.doc

    user_paths = revitmaterials.get_material_search_paths(ini="user")
    default_paths = revitmaterials.get_material_search_paths(ini="default")
    preferred_paths = revitini.edit_option_paths(
        user_paths, default_paths, value_delim="|"
    )
    if not preferred_paths:
        script.exit()

    materials = revitmaterials.get_materials(doc)
    asset_paths = []
    for material in materials:
        mat_paths = revitmaterials.get_material_texture_paths(
            material, doc, texture_paths=preferred_paths
        )
        asset_paths += mat_paths
    assets = revitmaterials.classify_paths(asset_paths, preferred_paths)

    rows = []
    for item in assets:
        if item["method"] == "Missing":
            relative_path = item["resolved_path"]
        else:
            relative_path = revitmaterials.make_relative_material_path(
                item["resolved_path"], preferred_paths
            )

        rows.append(
            RepathItem(
                False,
                item["id"],
                item["severity"],
                item["material_name"],
                item["usage"],
                item["path"],
                item["resolved_path"],
                relative_path,
                item["method"],
            )
        )

    window = RepathWindow("repath_form.xaml", rows)
    window.ShowDialog()

    selected_rows = [r for r in rows if r.Selected]

    if window.result and selected_rows:
        with revit.Transaction("Repath Material Assets"):
            for row in selected_rows:
                if revitmaterials.update_asset_path(
                    doc, row.Id, row.CurrentPath, row.ProposedPath
                ):
                    print(
                        "updated {} [{}] from {} to {}".format(
                            row.MaterialName, row.Id, row.CurrentPath, row.ProposedPath
                        )
                    )
                else:
                    print(
                        "ERROR: unable to update {} [{}] from {} to {}".format(
                            row.MaterialName, row.Id, row.CurrentPath, row.ProposedPath
                        )
                    )


if __name__ == "__main__":
    try:
        repath_materials()
    except Exception:
        print(traceback.format_exc())
