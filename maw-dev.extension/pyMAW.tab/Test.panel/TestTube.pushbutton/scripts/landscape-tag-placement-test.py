# -*- coding: utf-8 -*-
"""One-shot test of PromptForFamilyInstancePlacement with a Space Tag type.

Reports whether the default Space Tag type is a FamilySymbol and what
happens when it is passed to PromptForFamilyInstancePlacement.
"""

# # -------------- Standard Library Imports --------------
import traceback

# # ------------------ pyRevit Imports -------------------
from pyrevit import revit, DB, forms, script
from pyrevit.compat import get_elementid_value_func

from Autodesk.Revit.Exceptions import OperationCanceledException

output = script.get_output()
get_id_value = get_elementid_value_func()


def get_default_space_tag_type():
    type_id = revit.doc.GetDefaultFamilyTypeId(
        DB.ElementId(DB.BuiltInCategory.OST_MEPSpaceTags)
    )
    if type_id == DB.ElementId.InvalidElementId:
        return None
    return revit.doc.GetElement(type_id)


def main():
    tag_type = get_default_space_tag_type()
    if not tag_type:
        forms.alert("No default Space Tag type found.", exitscript=True)

    output.print_md("**Tag type:** {}".format(tag_type.Name))
    output.print_md("**Class:** {}".format(tag_type.GetType().FullName))
    output.print_md("**Is FamilySymbol:** {}".format(isinstance(tag_type, DB.FamilySymbol)))

    before = set(
        get_id_value(e.Id)
        for e in DB.FilteredElementCollector(revit.doc, revit.active_view.Id)
        .OfCategory(DB.BuiltInCategory.OST_MEPSpaceTags)
        .WhereElementIsNotElementType()
    )

    try:
        revit.uidoc.PromptForFamilyInstancePlacement(tag_type)
    except OperationCanceledException:
        output.print_md("Placement finished.")
    except Exception:
        output.print_md("**PromptForFamilyInstancePlacement failed:**")
        output.print_code(traceback.format_exc())
        return

    after = [
        e
        for e in DB.FilteredElementCollector(revit.doc, revit.active_view.Id)
        .OfCategory(DB.BuiltInCategory.OST_MEPSpaceTags)
        .WhereElementIsNotElementType()
        if get_id_value(e.Id) not in before
    ]
    output.print_md("**New Space Tags created:** {}".format(len(after)))


if __name__ == "__main__":
    main()
