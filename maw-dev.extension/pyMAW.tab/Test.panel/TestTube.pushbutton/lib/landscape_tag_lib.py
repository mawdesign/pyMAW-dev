# -*- coding: utf-8 -*-
"""Shared helpers for the landscape-tag and landscape-tag-update scripts.

Each planting schedule carries the element Id of its Space Tag in the instance
parameter named by SCHEDULE_TAG_PARAM (text or integer).
"""

# # -------------- Standard Library Imports --------------
import re

# # ------------------ pyRevit Imports -------------------
from pyrevit import revit, DB, forms, script
from pyrevit.compat import get_elementid_value_func

logger = script.get_logger()
get_id_value = get_elementid_value_func()

CONFIG_SECTION = "landscape_tag"
CONFIG_KEY = "space_parameter"
TEMPLATE_PREFIX = "_TEMPLATE"
SCHEDULE_NAME = "MASS PLANTING - {detail}/{sheet} - {space}"
SCHEDULE_TAG_PARAM = "Location_MAW"
SCHEDULE_GAP_X_FT = 0 / 304.8
SCHEDULE_GAP_Y_FT = -30 / 304.8
INVALID_NAME_CHARS = re.compile(r"[\\:{}\[\]|;<>?`~]")


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


def choose_template():
    prefix = TEMPLATE_PREFIX.lower()
    templates = [
        s
        for s in DB.FilteredElementCollector(revit.doc).OfClass(DB.ViewSchedule)
        if not s.IsTemplate and s.Name.lower().startswith(prefix)
    ]
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


def build_schedule_name(viewport, space):
    detail = viewport.get_Parameter(DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER)
    sheet = revit.doc.GetElement(viewport.SheetId)
    name = SCHEDULE_NAME.format(
        detail=detail.AsString() if detail else "",
        sheet=sheet.SheetNumber,
        space=space.Number,
    )
    return INVALID_NAME_CHARS.sub("-", name)


def get_or_create_schedule(template, parameter_name, value, view, name):
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


def get_schedule_tag(schedule):
    parameter = schedule.LookupParameter(SCHEDULE_TAG_PARAM)
    if not parameter or not parameter.HasValue:
        return None
    if parameter.StorageType == DB.StorageType.Integer:
        value = parameter.AsInteger()
    else:
        text = (parameter.AsString() or "").strip()
        if not text.isdigit():
            return None
        value = int(text)
    tag = revit.doc.GetElement(DB.ElementId(value)) if value > 0 else None
    return tag if isinstance(tag, DB.Mechanical.SpaceTag) else None


def set_schedule_tag(schedule, tag):
    parameter = schedule.LookupParameter(SCHEDULE_TAG_PARAM)
    if not parameter or parameter.IsReadOnly:
        return False
    value = get_id_value(tag.Id)
    if parameter.StorageType == DB.StorageType.Integer:
        return parameter.Set(value)
    return parameter.Set(str(value))


def find_viewport(view):
    for viewport in DB.FilteredElementCollector(revit.doc).OfClass(DB.Viewport):
        if viewport.ViewId == view.Id:
            return viewport
    return None


def read_view_frame(view, viewport):
    crop = view.CropBox
    return viewport.GetBoxCenter(), crop.Transform, (crop.Min + crop.Max) / 2.0


def get_view_frame(view, viewport):
    if view.CropBoxActive:
        return read_view_frame(view, viewport)
    with revit.DryTransaction("Planting Tag: Measure view"):
        view.CropBoxActive = True
        revit.doc.Regenerate()
        return read_view_frame(view, viewport)


def model_to_sheet_point(point, view, viewport):
    sheet_center, transform, crop_center = get_view_frame(view, viewport)
    scale = float(view.Scale)
    local = transform.Inverse.OfPoint(point)
    return DB.XYZ(
        sheet_center.X + (local.X - crop_center.X) / scale,
        sheet_center.Y + (local.Y - crop_center.Y) / scale,
        0,
    )


def schedule_point_for_tag(tag, view, viewport):
    sheet_point = model_to_sheet_point(tag.TagHeadPosition, view, viewport)
    return DB.XYZ(
        sheet_point.X + SCHEDULE_GAP_X_FT, sheet_point.Y - SCHEDULE_GAP_Y_FT, 0
    )


def find_schedule_instance(schedule, sheet):
    for instance in DB.FilteredElementCollector(revit.doc).OfClass(
        DB.ScheduleSheetInstance
    ):
        if instance.OwnerViewId == sheet.Id and instance.ScheduleId == schedule.Id:
            return instance
    return None


def get_space_tags(view):
    return list(
        DB.FilteredElementCollector(revit.doc, view.Id)
        .OfCategory(DB.BuiltInCategory.OST_MEPSpaceTags)
        .WhereElementIsNotElementType()
    )
