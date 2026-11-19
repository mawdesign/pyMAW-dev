# -*- coding: utf-8 -*-
"""Rename Material Assets."""

# IronPython 2.7 needs this for \uXXXX escapes; ruff format strips u"" prefixes.
from __future__ import unicode_literals

# # -------------- Standard Library Imports --------------
import traceback
import re

# import os
# import sys
# import wpf

# # -------------------- .NET Imports --------------------
# clr.AddReference("System.Drawing")
# clr.AddReference("PresentationCore")
# clr.AddReference("WindowsBase")

# # ------------------ pyRevit Imports -------------------
from pyrevit import script, forms
from pyrevit import revit
from pyrevit.framework import ObservableCollection

# # ------------------ module imports --------------------
import revitmaterials


STATUS_SYMBOLS = {
    "same": "\ue94e",
    "shared": "\ue171",
    "error": "\ue7ba\ue184",
    "generic": "\ue003",
    "copied": "\ue8c8",
    "edited": "\uf67b",
}

STATUS_COLOURS = {
    "shared": "#FFF2CC",  # amber
    "error": "#FFCCCC",  # light red
}


class MaterialAssetRow(forms.Reactive):
    def __init__(self, data):
        self._selected = False
        self._is_selectable = True
        self._asset_name = data["appearance_name"]
        self._original_asset_name = data["appearance_name"]
        self._asset_name_colour = "Black"
        self._status = data["appearance_status"]
        self._status_icon = ""
        self._copy_icon = ""
        self._edited = False
        self._copied = False

        self.MaterialId = data["material"].Id
        self.MaterialName = data["name"]
        self.AssetId = data["asset_id"]
        self.AssetName = data["appearance_name"]
        self.IsLocked = data["asset_id"] is None
        self.Status = data["appearance_status"]
        self.StatusToolTip = data["appearance_tooltip"]
        self.SharedCount = data["shared_count"]

        self.StatusIcon = self._get_icon()
        self.StatusColour = STATUS_COLOURS.get(self.Status, "#FFFFFF")
        self.CopyIcon = self._get_copy_icon()

        self.UpdateState()

    @forms.reactive
    def Selected(self):
        return self._selected

    @Selected.setter
    def Selected(self, value):
        self._selected = value

    @forms.reactive
    def IsSelectable(self):
        return self._is_selectable

    @IsSelectable.setter
    def IsSelectable(self, value):
        self._is_selectable = value

    @forms.reactive
    def Edited(self):
        return self._edited

    @Edited.setter
    def Edited(self, value):
        self._edited = value
        self.StatusIcon = self._get_icon()
        self.CopyIcon = self._get_copy_icon()
        self.UpdateState()

    @forms.reactive
    def Copied(self):
        return self._copied

    @Copied.setter
    def Copied(self, value):
        self._copied = value
        self.StatusIcon = self._get_icon()
        self.CopyIcon = self._get_copy_icon()

    @forms.reactive
    def AssetName(self):
        return self._asset_name

    @AssetName.setter
    def AssetName(self, value):
        # print("\nSET {} : {}".format(self.MaterialName, value))
        user_edit = False

        if hasattr(self, "Owner") and self.Owner and not self.Owner._updating:
            user_edit = True
            self.Owner.PropagateAssetName(self, value)

        self._apply_asset_name(value, user_edit=user_edit)

    @forms.reactive
    def AssetNameColour(self):
        return self._asset_name_colour

    @AssetNameColour.setter
    def AssetNameColour(self, value):
        self._asset_name_colour = value

    def _apply_asset_name(self, value, user_edit=False):
        self._asset_name = value

        if value != self._original_asset_name:
            self.Edited = True
            if user_edit:
                self.Selected = True
        else:
            self.Edited = False

    def SetAssetName(self, value, user_edit=False):
        self._apply_asset_name(value, user_edit=user_edit)
        self.OnPropertyChanged("AssetName")

    def ResetName(self):
        self.AssetName = self._original_asset_name
        self.Copied = False

    def CopyName(self):
        if self.IsLocked or self.Status in ("same", "generic"):
            return
        self.AssetName = self.MaterialName
        self.Copied = True
        self.Selected = True

    @forms.reactive
    def Status(self):
        return self._status

    @Status.setter
    def Status(self, value):
        self._status = value
        self.StatusIcon = self._get_icon()

    @forms.reactive
    def StatusIcon(self):
        return self._status_icon

    @StatusIcon.setter
    def StatusIcon(self, value):
        self._status_icon = value

    @forms.reactive
    def CopyIcon(self):
        return self._copy_icon

    @CopyIcon.setter
    def CopyIcon(self, value):
        self._copy_icon = value

    def _get_icon(self):
        if self.Copied:
            return STATUS_SYMBOLS.get("copied", "")
        if self.Edited:
            return STATUS_SYMBOLS.get("edited", "")
        return STATUS_SYMBOLS.get(self.Status, "")

    def _get_copy_icon(self):
        if self.Copied or self.Edited:
            return "\ue7a7"  # Undo
        if (
            self.IsLocked
            or self.Status in ("same", "generic")
            or self.AssetName == self.MaterialName
        ):
            return ""  # nothing to copy
        return "\uf413"

    def UpdateState(self):
        disabled = self.IsLocked or (
            not self.Edited and self.Status in ("same", "generic")
        )

        self.IsSelectable = not disabled
        if disabled:
            self.Selected = False
        if self.AssetName == self.MaterialName == self._original_asset_name:
            disabled = True
        self.AssetNameColour = "Gray" if disabled else "Black"


class MaterialAssetWindow(forms.WPFWindow):
    def __init__(self, xaml_file, rows):
        forms.WPFWindow.__init__(self, xaml_file)

        self._updating = False
        self._hide_unselected = False
        self.result = False
        self.rows = rows
        self.dgItems.ItemsSource = self.rows

        self.btnAll.Click += self.btnAll_Click
        self.btnNone.Click += self.btnNone_Click
        self.btnNotShared.Click += self.btnNotShared_Click
        self.btnEdited.Click += self.btnEdited_Click
        self.btnHideUnselected.Click += self.btnHideUnselected_Click
        self.btnOK.Click += self.btnOK_Click
        self.btnCancel.Click += self.btnCancel_Click

        self.asset_rows = {}

        for row in self.rows:
            row.Owner = self
            if row.AssetId not in self.asset_rows:
                self.asset_rows[row.AssetId] = []
            self.asset_rows[row.AssetId].append(row)

    def refresh_grid(self):
        if self._hide_unselected:
            self.dgItems.ItemsSource = [r for r in self.rows if r.Selected]
        else:
            self.dgItems.ItemsSource = self.rows
        self.dgItems.Items.Refresh()

    def PropagateAssetName(self, source_row, new_name):
        if self._updating:
            return
        self._updating = True
        try:
            for row in self.asset_rows[source_row.AssetId]:
                if row is source_row:
                    continue
                # row.AssetName = new_name
                row.SetAssetName(new_name, user_edit=False)
        finally:
            self._updating = False
            source_row.Selected = True

    def btnAll_Click(self, sender, args):
        for row in self.rows:
            row.Selected = True
        self.refresh_grid()

    def btnNone_Click(self, sender, args):
        for row in self.rows:
            row.Selected = False
        self.refresh_grid()

    def btnNotShared_Click(self, sender, args):
        for row in self.rows:
            row.Selected = row.Status not in ["shared", "same"]
        self.refresh_grid()

    def btnEdited_Click(self, sender, args):
        for row in self.rows:
            row.Selected = row.Status == "copied" or row.Edited
        self.refresh_grid()

    def btnHideUnselected_Click(self, sender, args):
        self.dgItems.CommitEdit()
        self.dgItems.CommitEdit()
        self._hide_unselected = not self._hide_unselected
        self.btnHideUnselected.Content = (
            "Show All" if self._hide_unselected else "Hide Unselected"
        )
        self.refresh_grid()

    def SelectionCheckbox_Click(self, sender, args):
        row = sender.DataContext
        new_value = sender.IsChecked

        for selected_row in self.dgItems.SelectedItems:
            if selected_row is not row:
                selected_row.Selected = new_value

    def CopyName_Click(self, sender, args):
        row = sender.DataContext
        if not row:
            return

        self.dgItems.CommitEdit()
        self.dgItems.CommitEdit()
        if row.Copied or row.Edited:
            row.ResetName()
        else:
            row.CopyName()

    def btnOK_Click(self, sender, args):
        self.DialogResult = True
        self.result = True
        self.Close()

    def btnCancel_Click(self, sender, args):
        self.result = False
        self.Close()


def rename_material_assets():
    doc = revit.doc
    script.get_output()

    materials = revitmaterials.get_materials(doc)

    if not materials:
        print("No materials found.")
        return

    asset_usage = {}
    material_assets = {}

    # Build usage map
    for material in materials:
        asset_data = revitmaterials.get_asset(doc, material)
        asset_id = asset_data["id"]
        status = ""
        tooltips = []
        tooltip = ""
        shared_count = 1

        if asset_data["name"][:6] == "Error:":
            asset_id = "error"
            tooltips.append(asset_data["name"])
            status = "error"
        if not asset_id:
            asset_id = None
            tooltips.append("Invalid or Generic asset")

        if asset_id not in asset_usage:
            asset_usage[asset_id] = {
                "asset_name": asset_data["name"],
                "materials": [],
                "status": "",
            }

        asset_usage[asset_id]["materials"].append(material)

        if asset_data["name"] == "<Generic>":
            status = "generic"
            tooltips.append("Generic asset")
        if material.Name == asset_data["name"]:
            status = "same"
            tooltips.append("Names are the same")
        if len(asset_usage[asset_id]["materials"]) > 1:
            status = "shared"
            shared_count = len(asset_usage[asset_id]["materials"])
            tooltip = "Shared with {} other material".format(shared_count - 1)
            tooltip += "s" if shared_count > 2 else ""
            tooltips.append(tooltip)
            for m in material_assets.keys():
                count = 0
                new_tooltip = ""
                old_tooltip = material_assets[m]["appearance_tooltip"]
                if material_assets[m]["appearance_name"] == asset_data["name"]:
                    material_assets[m]["appearance_status"] = status
                    new_tooltip, count = re.subn(
                        r"^Shared with .*$", tooltip, old_tooltip, flags=re.MULTILINE
                    )
                    if count == 0:
                        new_tooltip = old_tooltip + "\n" if old_tooltip else ""
                        new_tooltip += tooltip
                    material_assets[m]["appearance_tooltip"] = new_tooltip
                    material_assets[m]["shared_count"] = shared_count

        material_assets[material.Name] = {
            "name": material.Name,
            "material": material,
            "asset_id": asset_id,
            "appearance_name": asset_data["name"],
            "appearance_asset": asset_data,
            "appearance_status": status,
            "appearance_tooltip": "\n".join(tooltips),
            "shared_count": shared_count,
        }

    rows = ObservableCollection[MaterialAssetRow]()

    for _name, data in sorted(material_assets.items()):
        rows.Add(MaterialAssetRow(data))

    window = MaterialAssetWindow("rename_assets_form.xaml", rows)
    window.ShowDialog()

    if not window.result:
        return

    selected_rows = [r for r in rows if r.Selected]
    asset_updates = {}

    if selected_rows:
        warning_text = ""
        for row in selected_rows:
            new_name = (
                row.MaterialName
                if row.AssetName == row._original_asset_name
                else row.AssetName
            )
            if row.AssetId not in asset_updates:
                asset_updates[row.AssetId] = {
                    "asset_id": row.AssetId,
                    "old_name": row._original_asset_name,
                    "new_name": new_name,
                    "host_material": row.MaterialName,
                    "asset": material_assets[row.MaterialName]["appearance_asset"],
                }
            if row.SharedCount > 1:
                warning_text += "CONFIRM rename {} to {} from {}\n".format(
                    row._original_asset_name, new_name, row.MaterialName
                )
                warning_text += "⚠ Shared by {} materials\n\n".format(row.SharedCount)
        forms.alert_ifnot(
            warning_text == "",
            warning_text + "\nAre you sure?",
            yes=True,
            no=True,
            exitscript=True,
        )
        rename_count = 0
        fail_count = 0
        fail_list = []
        for i, a in asset_updates.items():
            renamed = revitmaterials.update_asset_name(doc, i, a["new_name"])
            if renamed:
                rename_count += 1
            else:
                fail_count += 1
                fail_list.append(
                    "{} could not be renamed to {}".format(a["old_name"], a["new_name"])
                )
        forms.alert(
            "{} updated, {} failed.\n{}".format(
                rename_count, fail_count, "\n".join(fail_list)
            ),
            warn_icon=(fail_count > 0),
        )


if __name__ == "__main__":
    try:
        rename_material_assets()
    except Exception:
        print(traceback.format_exc())
