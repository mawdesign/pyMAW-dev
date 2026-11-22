# -*- coding: utf-8 -*-
"""Shared helpers for the landscape-tag and landscape-tag-update scripts.

Each planting schedule carries the element Id of its Space Tag in the instance
parameter named by SCHEDULE_TAG_PARAM (text or integer).
"""

# # -------------- Standard Library Imports --------------
import json
import re

# # ------------------ pyRevit Imports -------------------
from pyrevit import revit, DB, forms, script
from pyrevit.compat import get_elementid_value_func

logger = script.get_logger()
get_id_value = get_elementid_value_func()

SETTINGS_FILE_ID = "landscape_tag_settings"
DEFAULT_SETTINGS = {
    "space_parameter": None,
    "template_name": None,
    "offset_x_mm": 0.0,
    "offset_y_mm": 0.0,
}
TEMPLATE_PREFIX = "_TEMPLATE"
SCHEDULE_NAME = "MASS PLANTING - {detail}/{sheet} - {space}"
SCHEDULE_TAG_PARAM = "Location_MAW"
MM_PER_FOOT = 304.8
INVALID_NAME_CHARS = re.compile(r"[\\:{}\[\]|;<>?`~]")


def get_text_value(parameter):
    return parameter.AsString() or parameter.AsValueString() or ""


def get_settings_path():
    return script.get_data_file(SETTINGS_FILE_ID, "json", add_cmd_name=False)


def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(get_settings_path(), "r") as settings_file:
            settings.update(json.load(settings_file))
    except (IOError, ValueError):
        logger.debug("No saved landscape tag settings; using defaults.")
    return settings


def save_settings(settings):
    with open(get_settings_path(), "w") as settings_file:
        json.dump(settings, settings_file, indent=2)


def get_space_parameter_names(space):
    return sorted(
        p.Definition.Name
        for p in space.Parameters
        if p.StorageType == DB.StorageType.String
        or p.StorageType == DB.StorageType.Integer
    )


def pick_space_parameter(space, settings):
    selected = forms.SelectFromList.show(
        get_space_parameter_names(space),
        title="Space parameter for bed / planting mix",
        button_name="Use parameter",
    )
    if selected:
        settings["space_parameter"] = selected
        save_settings(settings)
    return selected


def get_space_parameter_name(space, settings):
    saved = settings.get("space_parameter")
    if saved and space.LookupParameter(saved):
        return saved
    return pick_space_parameter(space, settings)


def find_template_schedules():
    prefix = TEMPLATE_PREFIX.lower()
    return [
        s
        for s in DB.FilteredElementCollector(revit.doc).OfClass(DB.ViewSchedule)
        if not s.IsTemplate and s.Name.lower().startswith(prefix)
    ]


def pick_template(templates, settings):
    by_name = dict((s.Name, s) for s in templates)
    selected = forms.SelectFromList.show(
        sorted(by_name), title="Select template schedule", button_name="Use template"
    )
    if not selected:
        return None
    settings["template_name"] = selected
    save_settings(settings)
    return by_name[selected]


def choose_template(settings):
    templates = find_template_schedules()
    if not templates:
        forms.alert(
            "No schedule found with a name starting '{}'.".format(TEMPLATE_PREFIX),
            exitscript=True,
        )
    saved = [t for t in templates if t.Name == settings.get("template_name")]
    if saved:
        return saved[0]
    if len(templates) == 1:
        return templates[0]
    template = pick_template(templates, settings)
    if not template:
        script.exit()
    return template


def ask_offset(label, current):
    text = forms.ask_for_string(
        default=str(current),
        prompt="{} offset in mm on the sheet.".format(label),
        title="Schedule offset from tag",
    )
    if text is None:
        return current
    try:
        return float(text)
    except ValueError:
        forms.alert("'{}' is not a number. Keeping {}.".format(text, current))
        return current


def configure_settings():
    settings = load_settings()
    spaces = list(
        DB.FilteredElementCollector(revit.doc)
        .OfCategory(DB.BuiltInCategory.OST_MEPSpaces)
        .WhereElementIsNotElementType()
    )
    if spaces:
        pick_space_parameter(spaces[0], settings)
    else:
        forms.alert("No Spaces in the model, so the Space parameter is unchanged.")
    templates = find_template_schedules()
    if len(templates) > 1:
        pick_template(templates, settings)
    elif not templates:
        forms.alert(
            "No schedule found with a name starting '{}'.".format(TEMPLATE_PREFIX)
        )
    settings["offset_x_mm"] = ask_offset(
        "Horizontal (positive moves right)", settings["offset_x_mm"]
    )
    settings["offset_y_mm"] = ask_offset(
        "Vertical (positive moves up)", settings["offset_y_mm"]
    )
    save_settings(settings)
    return settings


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
    settings = load_settings()
    sheet_point = model_to_sheet_point(tag.TagHeadPosition, view, viewport)
    return DB.XYZ(
        sheet_point.X + settings["offset_x_mm"] / MM_PER_FOOT,
        sheet_point.Y + settings["offset_y_mm"] / MM_PER_FOOT,
        0,
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
