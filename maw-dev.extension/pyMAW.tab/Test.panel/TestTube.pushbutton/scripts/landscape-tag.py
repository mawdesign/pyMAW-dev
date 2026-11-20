# -*- coding: utf-8 -*-
"""Tags planting bed Spaces and places a filtered planting schedule below each.

Place Space Tags as you would normally (multiple spaces, Esc to finish). For
each bed value a copy of the template schedule (name starts with '_TEMPLATE')
is filtered to that value, named by detail number, sheet number and space
number, and placed on the sheet just below the tag. The view must be on a
sheet, so the same bed can be tagged on several sheets or views. The
tag's element Id is stored on the schedule so landscape-tag-update can move
the schedules after the tags are rearranged.

Shift-click to choose a different Space parameter.
"""

# # -------------- Standard Library Imports --------------
import traceback

# # ------------------ pyRevit Imports -------------------
from pyrevit import revit, DB, forms, script

# # ----------------- Autodesk Imports -------------------
from Autodesk.Revit.Exceptions import OperationCanceledException

import landscape_tag_lib as lib

logger = script.get_logger()


def get_default_tag_type():
    type_id = revit.doc.GetDefaultFamilyTypeId(
        DB.ElementId(DB.BuiltInCategory.OST_MEPSpaceTags)
    )
    if type_id == DB.ElementId.InvalidElementId:
        return None
    return revit.doc.GetElement(type_id)


def place_tags(view, tag_type):
    before = set(lib.get_id_value(t.Id) for t in lib.get_space_tags(view))
    try:
        revit.uidoc.PromptForFamilyInstancePlacement(tag_type)
    except OperationCanceledException:
        pass
    return [t for t in lib.get_space_tags(view) if lib.get_id_value(t.Id) not in before]


def group_tags_by_value(tags, parameter_name):
    groups = {}
    for tag in tags:
        space = tag.Space
        parameter = space.LookupParameter(parameter_name) if space else None
        value = lib.get_text_value(parameter) if parameter else ""
        if not value:
            logger.warning("Skipped a tag whose space has no bed value.")
            continue
        groups.setdefault(value, []).append(tag)
    return groups


def process_group(value, tags, template, parameter_name, view, viewport):
    name = lib.build_schedule_name(viewport, tags[0].Space)
    schedule = lib.get_or_create_schedule(template, parameter_name, value, view, name)
    if not lib.get_schedule_tag(schedule):
        with revit.Transaction("Planting Tag: Link schedule to tag"):
            if not lib.set_schedule_tag(schedule, tags[0]):
                logger.warning(
                    "Could not write '{}' on schedule.".format(lib.SCHEDULE_TAG_PARAM)
                )
    sheet = revit.doc.GetElement(viewport.SheetId)
    if lib.find_schedule_instance(schedule, sheet):
        return
    point = lib.schedule_point_for_tag(tags[0], view, viewport)
    with revit.Transaction("Planting Tag: Place planting schedule"):
        DB.ScheduleSheetInstance.Create(revit.doc, sheet.Id, schedule.Id, point)


def main():
    view = revit.active_view
    if not isinstance(view, DB.ViewPlan):
        forms.alert("Run this from a plan view.", exitscript=True)

    viewport = lib.find_viewport(view)
    if not viewport:
        forms.alert(
            "This view is not placed on a sheet. Place it on a sheet before tagging.",
            exitscript=True,
        )

    tag_type = get_default_tag_type()
    if not tag_type:
        forms.alert("No default Space Tag type found.", exitscript=True)

    template = lib.choose_template()
    config = script.get_config(lib.CONFIG_SECTION)

    try:
        tags = [t for t in place_tags(view, tag_type) if t.Space]
        if not tags:
            return
        parameter_name = lib.get_space_parameter_name(tags[0].Space, config)
        if not parameter_name:
            return
        groups = group_tags_by_value(tags, parameter_name)
        for value, group in groups.items():
            process_group(value, group, template, parameter_name, view, viewport)
    except Exception:
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    main()
