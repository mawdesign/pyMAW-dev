# -*- coding: utf-8 -*-
"""Moves planting schedules to sit below their Space Tags on the current sheet.

Run from a sheet (all plan views on it) or from a plan view that is on a
sheet. Each schedule on the sheet holds the element Id of its Space Tag in a
parameter and is moved to sit below that tag.
"""

# # -------------- Standard Library Imports --------------
import traceback

# # ------------------ pyRevit Imports -------------------
from pyrevit import revit, DB, forms, script

import landscape_tag_hook as hook
import landscape_tag_lib as lib

__persistentengine__ = True

logger = script.get_logger()


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


def repair_orphans(viewports):
    schedules = lib.get_schedules_by_name()
    repairs = []
    for viewport in viewports:
        view = revit.doc.GetElement(viewport.ViewId)
        if not isinstance(view, DB.ViewPlan):
            continue
        for tag in lib.get_space_tags(view):
            schedule = lib.find_orphan_schedule(tag, viewport, schedules)
            if schedule:
                schedules.pop(schedule.Name)
                repairs.append((schedule, tag))
    if repairs:
        with revit.Transaction("Planting Tag: Relink schedules"):
            for schedule, tag in repairs:
                lib.set_schedule_tag(schedule, tag)
    return len(repairs)


def collect_targets(sheet, viewports):
    viewport_by_view = dict((vp.ViewId, vp) for vp in viewports)
    targets = []
    for instance in DB.FilteredElementCollector(revit.doc).OfClass(
        DB.ScheduleSheetInstance
    ):
        if instance.OwnerViewId != sheet.Id:
            continue
        tag = lib.get_schedule_tag(revit.doc.GetElement(instance.ScheduleId))
        viewport = viewport_by_view.get(tag.OwnerViewId) if tag else None
        if viewport:
            view = revit.doc.GetElement(tag.OwnerViewId)
            targets.append((instance, tag, view, viewport))
    return targets


def apply_targets(targets):
    moves = []
    for instance, tag, view, viewport in targets:
        point = lib.schedule_point_for_tag(tag, view, viewport)
        if instance.Point.DistanceTo(point) > lib.MOVE_TOLERANCE_FT:
            moves.append((instance, point))
    if not moves:
        return 0
    with revit.Transaction("Planting Tag: Update schedule positions"):
        for instance, point in moves:
            instance.Point = point
    return len(moves)


def main():
    sheet, viewports = get_sheet_and_viewports()
    if not sheet:
        forms.alert(
            "Run this from a sheet or from a plan view placed on a sheet.",
            exitscript=True,
        )
    hook.register()
    try:
        relinked = repair_orphans(viewports)
        targets = collect_targets(sheet, viewports)
        if not targets:
            forms.alert(
                "No schedules on this sheet have a '{}' value.".format(
                    lib.SCHEDULE_TAG_PARAM
                ),
                exitscript=True,
            )
        moved = apply_targets(targets)
        if moved or relinked:
            forms.toast(
                "Moved {} and relinked {} planting schedule(s).".format(
                    moved, relinked
                ),
                title="Update Planting Schedules",
            )
        else:
            forms.alert("All planting schedules are already in position.")
    except Exception:
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    main()
