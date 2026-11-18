# -*- coding: utf-8 -*-
"""Places a 3D grid of swatch families with assigned materials and 3D model text labels."""

# # -------------- Standard Library Imports --------------
# import clr
# import os
# import re
# import sys
import traceback
# import wpf

# # -------------------- .NET Imports --------------------
# clr.AddReference("System.Drawing")
# clr.AddReference("PresentationFramework")
# clr.AddReference("PresentationCore")
# clr.AddReference("WindowsBase")

# # ------------------ pyRevit Imports -------------------
from pyrevit import forms  # script,
from pyrevit import revit
from pyrevit import DB, UI
from rpw.ui import forms as rpw_forms

doc = revit.doc

# --- CONFIGURATION ---
FT_PER_MM = 0.00328084


class MaterialOption(forms.TemplateListItem):
    @property
    def name(self):
        return self.Name


def get_swatch_symbol(document):
    """Finds and activates the FamilySymbol for the 3D swatch."""
    symbols = (
        DB.FilteredElementCollector(document)
        .OfClass(DB.FamilySymbol)
        .OfCategory(DB.BuiltInCategory.OST_GenericModel)
        .ToElements()
    )

    fam_name = (
        forms.SelectFromList.show(
            [sym.FamilyName for sym in symbols], title="Select Swatch Family"
        )
        if len(symbols) > 1
        else symbols[0].FamilyName
    )

    for sym in symbols:
        if sym.FamilyName == fam_name:
            if not sym.IsActive:
                sym.Activate()
                document.Regenerate()
            return sym
    return None


def layout_materials_in_grid():
    # 1. Collect and sort all materials
    materials = list(DB.FilteredElementCollector(doc).OfClass(DB.Material))
    materials.sort(key=lambda m: m.Name.lower())

    if not materials:
        forms.alert("No materials found in the project.", exitscript=True)

    selected_materials = forms.SelectFromList.show(
        [MaterialOption(x) for x in materials],
        multiselect=True,
        title="Select Materials",
        button_name="Continue",
    )

    if not selected_materials:
        forms.alert(
            "No materials selected.\n\nDo you want to update current swatches?",
            ok=False,
            yes=True,
            no=True,
            exitscript=True,
        )

    swatch_symbol = get_swatch_symbol(doc)
    if not swatch_symbol:
        raise Exception("Could not find Generic Model family")
    swatch_family = doc.EditFamily(swatch_symbol.Family)
    family_mgr = swatch_family.FamilyManager

    swatch_text_params = []
    swatch_mat_params = []
    for param in family_mgr.Parameters:
        if (
            param.Definition.GetDataType() == DB.SpecTypeId.Reference.Material
            and not param.IsReadOnly
        ):
            swatch_mat_params.append(param.Definition.Name)
        if param.StorageType == DB.StorageType.String and not param.IsReadOnly:
            swatch_text_params.append(param.Definition.Name)

    components = [
        rpw_forms.Label("Swatch Family: {}".format(swatch_symbol.FamilyName)),
        rpw_forms.Label("Select Swatch Material Parameter:"),
        rpw_forms.ComboBox("mat_param", swatch_mat_params),
        rpw_forms.Label("Select Swatch Label Parameter:"),
        rpw_forms.ComboBox("mat_label", swatch_text_params),
    ]
    if selected_materials:
        components += [
            rpw_forms.Separator(),
            rpw_forms.Label("Column Spacing (mm):"),
            rpw_forms.TextBox("col_space", Text="1500"),
            rpw_forms.Label("Row Spacing (mm):"),
            rpw_forms.TextBox("row_space", Text="1800"),
            rpw_forms.Label("Columns per Row:"),
            rpw_forms.TextBox("cols", Text="10"),
        ]
    components += [rpw_forms.Button("Continue")]

    form = rpw_forms.FlexForm("Swatch Layout Parameters", components)
    form.show()

    if form.values:
        material_param = form.values["mat_param"]
        material_name_param = form.values["mat_label"]

        if selected_materials:
            try:
                # Convert the string inputs from TextBox into numbers
                col_spacing = float(form.values["col_space"]) * FT_PER_MM
                row_spacing = float(form.values["row_space"]) * FT_PER_MM
                max_cols = int(form.values["cols"])

            except ValueError:
                forms.alert(
                    "Please enter valid numeric values in the number fields.",
                    exitscript=True,
                )

    if selected_materials:
        with revit.Transaction("Generate 3D Material Swatches"):
            placed_count = 0

            for idx, mat in enumerate(selected_materials):
                col = idx % max_cols
                row = idx // max_cols

                x = col * col_spacing
                y = -row * row_spacing
                location = DB.XYZ(x, y, 0)

                # Place 3D Swatch Family Instance
                instance = doc.Create.NewFamilyInstance(
                    location, swatch_symbol, DB.Structure.StructuralType.NonStructural
                )

                # Assign the Material to the instance parameter
                mat_param = instance.LookupParameter(material_param)
                if mat_param and not mat_param.IsReadOnly:
                    mat_param.Set(mat.Id)
                    placed_count += 1

                mat_name_param = instance.LookupParameter(material_name_param)
                if mat_name_param and not mat_name_param.IsReadOnly:
                    mat_name_param.Set(mat.Name)

            forms.alert("Placed {} 3D material swatches.".format(placed_count))
    else:
        with revit.Transaction("Update 3D Material Swatches"):
            updated_count = 0

            class SwatchSelectionFilter(UI.Selection.ISelectionFilter):
                def AllowElement(self, element):
                    try:
                        return (
                            isinstance(element, DB.FamilyInstance)
                            and element.Symbol.Family.Id == swatch_symbol.Family.Id
                        )
                    except Exception:
                        return False

                def AllowReference(self, reference, point):
                    return False

            try:
                refs = revit.uidoc.Selection.PickObjects(
                    UI.Selection.ObjectType.Element,
                    SwatchSelectionFilter(),
                    "Select swatches to update",
                )
                selected_instances = [revit.doc.GetElement(r) for r in refs]
            except Exception:
                # Handles user pressing Esc to cancel
                selected_instances = []

            if not selected_instances:
                forms.alert("No swatches selected.", exitscript=True)

            for instance in selected_instances:
                mat_param = instance.LookupParameter(material_param)
                name_param = instance.LookupParameter(material_name_param)

                if not mat_param or not name_param:
                    continue

                material_id = mat_param.AsElementId()

                if material_id == DB.ElementId.InvalidElementId:
                    continue

                material = doc.GetElement(material_id)

                if not material:
                    continue

                if not name_param.IsReadOnly and name_param.AsString() != material.Name:
                    name_param.Set(material.Name)
                    updated_count += 1

            forms.alert("Updated {} swatches.".format(updated_count))


if __name__ == "__main__":
    try:
        layout_materials_in_grid()
    except Exception:
        print(traceback.format_exc())
