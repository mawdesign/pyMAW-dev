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
    points = [
        lib.schedule_point_for_tag(tag, view, viewport)
        for _, tag, view, viewport in targets
    ]
    with revit.Transaction("Planting Tag: Update schedule positions"):
        for (instance, _, _, _), point in zip(targets, points):
            instance.Point = point
    return len(targets)


def main():
    sheet, viewports = get_sheet_and_viewports()
    if not sheet:
        forms.alert(
            "Run this from a sheet or from a plan view placed on a sheet.",
            exitscript=True,
        )
    try:
        targets = collect_targets(sheet, viewports)
        if not targets:
            forms.alert(
                "No schedules on this sheet have a '{}' value.".format(
                    lib.SCHEDULE_TAG_PARAM
                ),
                exitscript=True,
            )
        output.print_md("Moved {} schedule(s).".format(apply_targets(targets)))
    except Exception:
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    main()
