# -*- coding: utf-8 -*-
"""Moves planting schedules to sit below their Space Tags on the current sheet.

Run from a sheet (all plan views on it) or from a plan view that is on a
sheet. Each tag's schedule Id parameter identifies its schedule. Where several
tags share a schedule, the first tag found is used. Schedules not yet on the
sheet are placed.
"""

# # -------------- Standard Library Imports --------------
import traceback

# # ------------------ pyRevit Imports -------------------
from pyrevit import revit, DB, forms, script

import landscape_tag_lib as lib

logger = script.get_logger()
output = script.get_output()


def get_sheet_and_viewports():
    view = revit.active_view
    if isinstance(view, DB.ViewSheet):
        viewports = [revit.doc.GetElement(i) for i in view.GetAllViewports()]
        return view, viewports
    if isinstance(view, DB.ViewPlan):
        viewport = lib.find_viewport(view)
        if viewport:
            return revit.doc.GetElement(viewport.SheetId), [viewport]
    return None, []


def collect_targets(viewports):
    targets = {}
    for viewport in viewports:
        view = revit.doc.GetElement(viewport.ViewId)
        if not isinstance(view, DB.ViewPlan):
            continue
        for tag in lib.get_space_tags(view):
            schedule_id = lib.get_tag_schedule_id(tag)
            if not schedule_id or schedule_id in targets:
                continue
            schedule = revit.doc.GetElement(schedule_id)
            if isinstance(schedule, DB.ViewSchedule):
                targets[schedule_id] = (schedule, tag, view, viewport)
    return targets


def apply_targets(targets, sheet):
    moved = placed = 0
    with revit.Transaction("Planting Tag: Update schedule positions"):
        for schedule, tag, view, viewport in targets.values():
            point = lib.schedule_point_for_tag(tag, view, viewport)
            instance = lib.find_schedule_instance(schedule, sheet)
            if instance:
                instance.Point = point
                moved += 1
            else:
                DB.ScheduleSheetInstance.Create(
                    revit.doc, sheet.Id, schedule.Id, point
                )
                placed += 1
    return moved, placed


def main():
    sheet, viewports = get_sheet_and_viewports()
    if not sheet:
        forms.alert(
            "Run this from a sheet or from a plan view placed on a sheet.",
            exitscript=True,
        )
    try:
        targets = collect_targets(viewports)
        if not targets:
            forms.alert(
                "No tags with a '{}' value found.".format(lib.TAG_SCHEDULE_PARAM),
                exitscript=True,
            )
        moved, placed = apply_targets(targets, sheet)
        output.print_md("Moved {} schedule(s), placed {}.".format(moved, placed))
    except Exception:
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    main()
