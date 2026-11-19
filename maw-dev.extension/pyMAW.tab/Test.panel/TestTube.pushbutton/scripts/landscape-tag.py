# -*- coding: utf-8 -*-
"""Tags a planting bed Space and places a filtered planting schedule below it.

Pick a Space, then click a tag position and a leader end for each Space Tag
to create. Press Esc to finish. A copy of the template schedule (name starts
with '_TEMPLATE') is filtered to the Space parameter value and placed on the
sheet just below the first tag.

Shift-click to choose a different Space parameter.
"""

# # -------------- Standard Library Imports --------------
import re
import traceback

# # ------------------ pyRevit Imports -------------------
from pyrevit import revit, DB, forms, script

# # ----------------- Autodesk Imports -------------------
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType

logger = script.get_logger()
output = script.get_output()

CONFIG_SECTION = "landscape_tag"
CONFIG_KEY = "space_parameter"
TEMPLATE_PREFIX = "_TEMPLATE"
SCHEDULE_NAME = "Planting - {}"
SCHEDULE_GAP_FT = 10.0 / 304.8
INVALID_NAME_CHARS = re.compile(r"[\\:{}\[\]|;<>?`~]")


class SpaceFilter(ISelectionFilter):
    def AllowElement(self, element):
        return element.Category is not None and element.Category.Id == DB.ElementId(
            DB.BuiltInCategory.OST_MEPSpaces
        )

    def AllowReference(self, reference, position):
        return False


def pick_space(uidoc):
    try:
        reference = uidoc.Selection.PickObject(
            ObjectType.Element, SpaceFilter(), "Pick a Space to tag"
        )
    except OperationCanceledException:
        return None
    return revit.doc.GetElement(reference)


def pick_point(uidoc, prompt):
    try:
        return uidoc.Selection.PickPoint(prompt)
    except OperationCanceledException:
        return None


def get_text_value(parameter):
    return parameter.AsString() or parameter.AsValueString() or ""


def get_space_parameter_name(space, config):
    saved = getattr(config, CONFIG_KEY, None)
    if saved and not script.EXEC_PARAMS.config_mode and space.LookupParameter(saved):
        return saved
    names = sorted(
        p.Definition.Name
        for p in space.Parameters
        if p.StorageType == DB.StorageType.String
        or p.StorageType == DB.StorageType.Integer
    )
    selected = forms.SelectFromList.show(
        names,
        title="Space parameter for bed / planting mix",
        button_name="Use parameter",
    )
    if not selected:
        return None
    setattr(config, CONFIG_KEY, selected)
    script.save_config()
    return selected


def find_template_schedules():
    prefix = TEMPLATE_PREFIX.lower()
    return [
        s
        for s in DB.FilteredElementCollector(revit.doc).OfClass(DB.ViewSchedule)
        if not s.IsTemplate and s.Name.lower().startswith(prefix)
    ]


def choose_template():
    templates = find_template_schedules()
    if not templates:
        forms.alert(
            "No schedule found with a name starting '{}'.".format(TEMPLATE_PREFIX),
            exitscript=True,
        )
    if len(templates) == 1:
        return templates[0]
    by_name = dict((s.Name, s) for s in templates)
    selected = forms.SelectFromList.show(
        sorted(by_name), title="Select template schedule", button_name="Use template"
    )
    if not selected:
        script.exit()
    return by_name[selected]


def find_schedule_by_name(name):
    for schedule in DB.FilteredElementCollector(revit.doc).OfClass(DB.ViewSchedule):
        if schedule.Name == name:
            return schedule
    return None


def find_space_field(definition, parameter_name):
    candidates = ("Space: {}".format(parameter_name), parameter_name)
    for index in range(definition.GetFieldCount()):
        field = definition.GetField(index)
        if field.GetName() in candidates:
            return field
    for schedulable in definition.GetSchedulableFields():
        if schedulable.GetName(revit.doc) in candidates[:1]:
            field = definition.AddField(schedulable)
            field.IsHidden = True
            return field
    return None


def set_equal_filter(definition, field, value):
    for index in reversed(range(definition.GetFilterCount())):
        if definition.GetFilter(index).FieldId == field.FieldId:
            definition.RemoveFilter(index)
    definition.AddFilter(
        DB.ScheduleFilter(field.FieldId, DB.ScheduleFilterType.Equal, value)
    )


def match_view_phase(schedule, view):
    view_phase = view.get_Parameter(DB.BuiltInParameter.VIEW_PHASE)
    schedule_phase = schedule.get_Parameter(DB.BuiltInParameter.VIEW_PHASE)
    if not view_phase or not schedule_phase or schedule_phase.IsReadOnly:
        logger.warning("Could not set schedule phase to match the view.")
        return
    schedule_phase.Set(view_phase.AsElementId())


def get_or_create_schedule(template, parameter_name, value, view):
    raw_name = SCHEDULE_NAME.format(value)
    name = INVALID_NAME_CHARS.sub("-", raw_name)
    with revit.Transaction("Create planting schedule"):
        schedule = find_schedule_by_name(name)
        if not schedule:
            new_id = template.Duplicate(DB.ViewDuplicateOption.Duplicate)
            schedule = revit.doc.GetElement(new_id)
            schedule.Name = name
        field = find_space_field(schedule.Definition, parameter_name)
        if not field:
            forms.alert(
                "Template has no Space field for '{}'.".format(parameter_name),
                exitscript=True,
            )
        set_equal_filter(schedule.Definition, field, value)
        match_view_phase(schedule, view)
    return schedule


def get_tag_type_id():
    type_id = revit.doc.GetDefaultFamilyTypeId(
        DB.ElementId(DB.BuiltInCategory.OST_MEPSpaceTags)
    )
    if type_id == DB.ElementId.InvalidElementId:
        return None
    return type_id


def create_space_tag(space, view, head_point, leader_end, type_id):
    location = space.Location.Point
    with revit.Transaction("Tag space"):
        tag = revit.doc.Create.NewSpaceTag(
            space, DB.UV(location.X, location.Y), view
        )
        if type_id:
            tag.ChangeTypeId(type_id)
        tag.HasLeader = True
        revit.doc.Regenerate()
        tag.TagHeadPosition = head_point
        tag.LeaderEnd = leader_end
    return tag


def tag_space(space, view, uidoc):
    type_id = get_tag_type_id()
    head_points = []
    while True:
        head_point = pick_point(uidoc, "Click tag position (Esc to finish)")
        if not head_point:
            break
        leader_end = pick_point(uidoc, "Click leader end (Esc to finish)")
        if not leader_end:
            break
        create_space_tag(space, view, head_point, leader_end, type_id)
        head_points.append(head_point)
    return head_points


def find_viewport(view):
    for viewport in DB.FilteredElementCollector(revit.doc).OfClass(DB.Viewport):
        if viewport.ViewId == view.Id:
            return viewport
    return None


def model_to_sheet_point(point, view, viewport):
    scale = float(view.Scale)
    sheet_center = viewport.GetBoxCenter()
    if not view.CropBoxActive:
        logger.warning("Crop region is off; schedule placed at the view's centre.")
        return DB.XYZ(sheet_center.X, sheet_center.Y, 0)
    crop = view.CropBox
    local = crop.Transform.Inverse.OfPoint(point)
    crop_center = (crop.Min + crop.Max) / 2.0
    return DB.XYZ(
        sheet_center.X + (local.X - crop_center.X) / scale,
        sheet_center.Y + (local.Y - crop_center.Y) / scale,
        0,
    )


def is_on_sheet(schedule, sheet):
    return any(
        instance.OwnerViewId == sheet.Id and instance.ScheduleId == schedule.Id
        for instance in DB.FilteredElementCollector(revit.doc).OfClass(
            DB.ScheduleSheetInstance
        )
    )


def place_schedule(schedule, view, head_point):
    viewport = find_viewport(view)
    if not viewport:
        forms.alert(
            "View is not on a sheet. Schedule '{}' was created but not placed.".format(
                schedule.Name
            )
        )
        return
    sheet = revit.doc.GetElement(viewport.SheetId)
    if is_on_sheet(schedule, sheet):
        return
    sheet_point = model_to_sheet_point(head_point, view, viewport)
    below = DB.XYZ(sheet_point.X, sheet_point.Y - SCHEDULE_GAP_FT, 0)
    with revit.Transaction("Place planting schedule"):
        DB.ScheduleSheetInstance.Create(revit.doc, sheet.Id, schedule.Id, below)


def main():
    uidoc = revit.uidoc
    view = revit.active_view
    if not isinstance(view, DB.ViewPlan):
        forms.alert("Run this from a plan view.", exitscript=True)

    space = pick_space(uidoc)
    if not space:
        script.exit()

    config = script.get_config(CONFIG_SECTION)
    parameter_name = get_space_parameter_name(space, config)
    if not parameter_name:
        script.exit()
    value = get_text_value(space.LookupParameter(parameter_name))
    if not value:
        forms.alert(
            "Space has no value for '{}'.".format(parameter_name), exitscript=True
        )

    template = choose_template()

    try:
        head_points = tag_space(space, view, uidoc)
        if not head_points:
            return
        schedule = get_or_create_schedule(template, parameter_name, value, view)
        place_schedule(schedule, view, head_points[0])
    except Exception:
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    main()
