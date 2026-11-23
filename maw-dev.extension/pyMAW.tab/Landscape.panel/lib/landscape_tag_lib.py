# -*- coding: utf-8 -*-
"""Shared helpers for the landscape-tag and landscape-tag-update scripts.

Each planting schedule carries the element Id of its Space Tag in the instance
parameter named by SCHEDULE_TAG_PARAM. Tool settings are stored as one line of
JSON in the Project Information parameter named by SETTINGS_PARAM. Both
parameters come from landscape_tag_parameters.txt, which ensure_parameters adds
to the project if they are missing.
"""

# # -------------- Standard Library Imports --------------
import json
import os.path as op
import re

# # ------------------ pyRevit Imports -------------------
from pyrevit import revit, DB, forms, script, HOST_APP
from pyrevit.compat import get_elementid_value_func

from System import Guid, Int32, Int64

logger = script.get_logger()
get_id_value = get_elementid_value_func()

PARAMETER_FILE = op.join(op.dirname(__file__), "landscape_tag_parameters.txt")
SETTINGS_PARAM = "LANDSCAPE_TAG_SETTINGS"
SETTINGS_GUID = "3b9ef27a-c415-4060-bbfe-c28301f53a23"
DEFAULT_SETTINGS = {
    "space_parameter": None,
    "template_name": None,
    "offset_x_mm": 0.0,
    "offset_y_mm": 0.0,
}
TEMPLATE_PREFIX = "_TEMPLATE"
SCHEDULE_NAME = "MASS PLANTING - {detail}/{sheet} - {space}"
SCHEDULE_TAG_PARAM = "LANDSCAPE_TAG_ID"
SCHEDULE_TAG_GUID = "c62b258e-353f-469f-bb57-6f053712148d"
MM_PER_FOOT = 304.8
MOVE_TOLERANCE_FT = 1e-4
FALLBACK_SPACE_PARAMETER = "Number"
INVALID_NAME_CHARS = re.compile(r"[\\:{}\[\]|;<>?`~]")


def find_parameter(element, name, guid):
    return element.get_Parameter(Guid(guid)) or element.LookupParameter(name)


def get_text_value(parameter):
    return parameter.AsString() or parameter.AsValueString() or ""


def get_bound_parameter_names():
    names = set()
    iterator = revit.doc.ParameterBindings.ForwardIterator()
    while iterator.MoveNext():
        names.add(iterator.Key.Name)
    return names


def get_parameter_group():
    if HOST_APP.is_newer_than(2023):
        return DB.GroupTypeId.Data
    return DB.BuiltInParameterGroup.PG_DATA


def ensure_parameters():
    required = [
        (SETTINGS_PARAM, DB.BuiltInCategory.OST_ProjectInformation),
        # API-QUIRK: the docs say USERMODIFIABLE and HIDEWHENNOVALUE only restrict
        # UI users, but a Schedules parameter that is not user modifiable or is
        # hidden when empty is read-only to the API, so LANDSCAPE_TAG_ID must be
        # user modifiable and visible when empty.
        (SCHEDULE_TAG_PARAM, DB.BuiltInCategory.OST_Schedules),
    ]
    bound = get_bound_parameter_names()
    missing = [(name, cat) for name, cat in required if name not in bound]
    if not missing:
        return
    app = HOST_APP.app
    previous_file = app.SharedParametersFilename
    app.SharedParametersFilename = PARAMETER_FILE
    try:
        definitions = dict(
            (d.Name, d)
            for group in app.OpenSharedParameterFile().Groups
            for d in group.Definitions
        )
        with revit.Transaction("Landscape Tag: Add parameters"):
            for name, built_in_category in missing:
                categories = app.Create.NewCategorySet()
                category = revit.doc.Settings.Categories.get_Item(built_in_category)
                categories.Insert(category)
                binding = app.Create.NewInstanceBinding(categories)
                revit.doc.ParameterBindings.Insert(
                    definitions[name], binding, get_parameter_group()
                )
    finally:
        app.SharedParametersFilename = previous_file


def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    parameter = find_parameter(
        revit.doc.ProjectInformation, SETTINGS_PARAM, SETTINGS_GUID
    )
    if not parameter or not parameter.HasValue:
        return settings
    try:
        settings.update(json.loads(parameter.AsString()))
    except ValueError:
        logger.warning("Saved landscape tag settings are invalid; using defaults.")
    return settings


def save_settings(settings):
    parameter = find_parameter(
        revit.doc.ProjectInformation, SETTINGS_PARAM, SETTINGS_GUID
    )
    if not parameter or parameter.IsReadOnly:
        forms.alert("The {} parameter is not available.".format(SETTINGS_PARAM))
        return False
    text = json.dumps(settings, sort_keys=True, separators=(",", ":"))
    try:
        with revit.Transaction("Landscape Tag: Save settings"):
            parameter.Set(text)
    except Exception as error:
        forms.alert(
            "Could not save settings. Another user may be editing Project "
            "Information.\n\n{}".format(error)
        )
        return False
    return True


def get_space_parameter_names(space):
    return sorted(
        p.Definition.Name
        for p in space.Parameters
        if p.StorageType == DB.StorageType.String
        or p.StorageType == DB.StorageType.Integer
    )


def pick_space_parameter(space, settings):
    names = get_space_parameter_names(space)
    current = settings.get("space_parameter")
    if current in names:
        default = current
    elif FALLBACK_SPACE_PARAMETER in names:
        default = FALLBACK_SPACE_PARAMETER
    else:
        default = None
    selected = forms.ask_for_one_item(
        names,
        default=default,
        prompt="Space parameter for bed / planting mix",
        title="Landscape tag settings",
    )
    if selected:
        settings["space_parameter"] = selected
    return selected


def get_space_parameter_name(space, settings):
    saved = settings.get("space_parameter")
    if saved and space.LookupParameter(saved):
        return saved
    selected = pick_space_parameter(space, settings)
    if selected:
        save_settings(settings)
    return selected


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
    save_settings(settings)
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


def get_schedules_by_name():
    return dict(
        (s.Name, s)
        for s in DB.FilteredElementCollector(revit.doc).OfClass(DB.ViewSchedule)
    )


def find_orphan_schedule(tag, viewport, schedules_by_name):
    space = tag.Space
    if not space:
        return None
    schedule = schedules_by_name.get(build_schedule_name(viewport, space))
    if schedule and not get_schedule_tag(schedule):
        return schedule
    return None


def get_tag_viewports(tag, viewports):
    """Returns the viewports whose view shows the tag.

    Note: a tag drawn in a dependent view is owned by its primary view, so a
    viewport matches when its view is the owner or a dependent of the owner.
    """
    owner_id = tag.OwnerViewId
    matches = []
    for viewport in viewports:
        view = revit.doc.GetElement(viewport.ViewId)
        if view.Id == owner_id or view.GetPrimaryViewId() == owner_id:
            matches.append(viewport)
    return matches


def find_tag_viewport(tag, viewports, schedule_name):
    matches = get_tag_viewports(tag, viewports)
    space = tag.Space
    if space:
        for viewport in matches:
            if build_schedule_name(viewport, space) == schedule_name:
                return viewport
    return matches[0] if matches else None


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


def make_element_id(value):
    """Builds an ElementId from a Python int on any Revit version.

    Note: Revit 2024+ ElementId has Int32 and Int64 constructors, and IronPython
    cannot choose between them for a plain int.
    """
    if HOST_APP.is_newer_than(2023):
        return DB.ElementId(Int64(value))
    return DB.ElementId(Int32(value))


def get_schedule_tag(schedule):
    parameter = find_parameter(schedule, SCHEDULE_TAG_PARAM, SCHEDULE_TAG_GUID)
    if not parameter or not parameter.HasValue:
        return None
    if parameter.StorageType == DB.StorageType.Integer:
        value = parameter.AsInteger()
    else:
        text = (parameter.AsString() or "").strip()
        if not text.isdigit():
            return None
        value = int(text)
    tag = revit.doc.GetElement(make_element_id(value)) if value > 0 else None
    return tag if isinstance(tag, DB.Mechanical.SpaceTag) else None


def set_schedule_tag(schedule, tag):
    parameter = find_parameter(schedule, SCHEDULE_TAG_PARAM, SCHEDULE_TAG_GUID)
    if not parameter:
        logger.warning(
            "'{}' not found on schedule '{}'. It may be bound to the wrong "
            "category, or hidden from the API while empty.".format(
                SCHEDULE_TAG_PARAM, schedule.Name
            )
        )
        return False
    if parameter.IsReadOnly:
        logger.warning(
            "'{}' is read-only (shared: {}, storage: {}).".format(
                SCHEDULE_TAG_PARAM, parameter.IsShared, parameter.StorageType
            )
        )
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
