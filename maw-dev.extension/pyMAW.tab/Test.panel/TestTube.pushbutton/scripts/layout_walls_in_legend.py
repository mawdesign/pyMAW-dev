# -*- coding: utf-8 -*-
"""Layout Walls In Legend.

Duplicates a base legend component into a 1m x 1m grid for all wall types.
"""

# # -------------- Standard Library Imports --------------
# import os
# import sys
# import clr
import math

# # ------------------ pyRevit Imports -------------------
from pyrevit import script, forms
from pyrevit import revit
from pyrevit import DB


logger = script.get_logger()


def mm_to_ft(mm):
    return mm / 304.8


def layout_walls_in_legend():
    doc = revit.doc
    view = doc.ActiveView

    # 1. Validate active view is a Legend
    if view.ViewType != DB.ViewType.Legend:
        forms.alert(
            "Please run this script from a Legend view.",
            title="Invalid View",
            warn_icon=True,
        )
        return

    # 2. Find a base Legend Component to copy
    legend_components = (
        DB.FilteredElementCollector(doc, view.Id)
        .OfCategory(DB.BuiltInCategory.OST_LegendComponents)
        .WhereElementIsNotElementType()
        .ToElements()
    )

    if not legend_components:
        forms.alert(
            "Revit API requires an existing Legend Component to duplicate.\n\n"
            "Please manually place at least ONE legend component (of any type) in this view, then run the script again.",
            title="Action Required",
            warn_icon=True,
        )
        return

    base_comp = legend_components[0]

    # Legend components often don't have a valid LocationPoint property.
    # We must use get_BoundingBox(view) to extract spatial coordinates.
    base_bb = base_comp.get_BoundingBox(view)

    if not base_bb:
        forms.alert(
            "Could not determine the location of the base legend component.",
            title="Error",
            warn_icon=True,
        )
        return

    # Calculate center point by averaging Min and Max bounds
    base_loc = DB.XYZ(
        (base_bb.Min.X + base_bb.Max.X) / 2.0, (base_bb.Min.Y + base_bb.Max.Y) / 2.0, 0
    )

    # 3. Collect all Basic Wall Types
    wall_types = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.WallType)
        .WhereElementIsElementType()
        .ToElements()
    )
    basic_wall_types = [wt for wt in wall_types if wt.Kind == DB.WallKind.Basic]

    if not basic_wall_types:
        forms.alert(
            "No basic wall types found in the project.", title="Error", warn_icon=True
        )
        return

    basic_wall_types.sort(key=lambda x: DB.Element.Name.__get__(x))

    # 4. Get a Text Note Type
    text_type = DB.FilteredElementCollector(doc).OfClass(DB.TextNoteType).FirstElement()

    # 5. Calculate Grid
    total_walls = len(basic_wall_types)
    cols = int(math.ceil(math.sqrt(total_walls)))

    spacing_ft = mm_to_ft(1000.0)
    wall_len_ft = mm_to_ft(900.0)

    walls_created = 0

    with revit.Transaction("Layout Wall Legend Grid"):
        for i, wt in enumerate(basic_wall_types):
            col = i % cols
            row = i // cols

            # Center the wall horizontally, align interior face flush with the top of the cell
            # Legend components are typically anchored by their centerline, so offset down by half the width
            target_pt = DB.XYZ(
                col * spacing_ft + (spacing_ft / 2.0),
                -row * spacing_ft - (wt.Width / 2.0),
                0,
            )

            # Calculate translation vector from the base component
            translation = target_pt - base_loc

            try:
                # Duplicate the component
                new_ids = DB.ElementTransformUtils.CopyElement(
                    doc, base_comp.Id, translation
                )
                new_comp = doc.GetElement(new_ids[0])

                # Swap the component's target to the current Wall Type
                comp_param = new_comp.get_Parameter(
                    DB.BuiltInParameter.LEGEND_COMPONENT
                )
                if comp_param and not comp_param.IsReadOnly:
                    comp_param.Set(wt.Id)

                # Attempt to set the view representation to "Floor Plan" (Value 1)
                view_param = new_comp.get_Parameter(
                    DB.BuiltInParameter.LEGEND_COMPONENT_VIEW
                )
                if view_param and not view_param.IsReadOnly:
                    view_param.Set(-8)

                # Attempt to set the Host Length to 900mm
                length_param = new_comp.LookupParameter(
                    "Host Length"
                ) or new_comp.LookupParameter("Component Length")
                if length_param and not length_param.IsReadOnly:
                    length_param.Set(wall_len_ft)

                # Get Type Mark (Fallback to Type Name if empty)
                type_mark_param = wt.get_Parameter(
                    DB.BuiltInParameter.ALL_MODEL_TYPE_MARK
                )
                type_mark = (
                    type_mark_param.AsString()
                    if type_mark_param and type_mark_param.AsString()
                    else DB.Element.Name.__get__(wt)
                )

                # Place Text Note in the center of the cell
                text_pt = DB.XYZ(
                    col * spacing_ft + (spacing_ft / 2.0),
                    -row * spacing_ft - (spacing_ft / 2.0),
                    0,
                )

                if text_type:
                    DB.TextNote.Create(doc, view.Id, text_pt, type_mark, text_type.Id)

                walls_created += 1

            except Exception as e:
                logger.error(
                    "Failed to layout legend component for {}: {}".format(
                        DB.Element.Name.__get__(wt), e
                    )
                )

        # Hide or delete the original base component so it doesn't mess up the grid
        try:
            doc.Delete(base_comp.Id)
        except:
            pass

    forms.alert(
        "Successfully laid out {} legend components.".format(walls_created),
        title="Complete",
    )


if __name__ == "__main__":
    layout_walls_in_legend()
