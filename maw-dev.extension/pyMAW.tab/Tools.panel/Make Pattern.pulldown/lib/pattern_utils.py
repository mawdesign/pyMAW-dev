# -*- coding: utf-8 -*-
"""
Shared library of utility functions for pattern generation tools.
- Unit parsing (dim_from_string)
- Revit element creation (Filled Region)
- Color/UI converters
"""

# pyRevit Imports
from pyrevit import revit, script, forms, DB
from pyrevit.revit.db.transaction import Transaction

# .NET Imports
import clr
import System

clr.AddReference("PresentationFramework")
from System.Windows.Media import SolidColorBrush, Color as MediaColor

# --- CONVERSION FUNCTIONS ---


def db_color_to_wpf_brush(db_color):
    """Converts an Autodesk.Revit.DB.Color to a WPF.Media.Brush."""
    if not db_color or not db_color.IsValid:
        # Default to gray if invalid
        return SolidColorBrush(MediaColor.FromRgb(192, 192, 192))
    return SolidColorBrush(
        MediaColor.FromRgb(db_color.Red, db_color.Green, db_color.Blue)
    )


def db_color_from_hex(hex_color_string):
    """
    Converts a hex color string (e.g., '#FF0000' or 'FF0000') to a DB.Color object.
    """
    # Remove the '#' if it exists
    if hex_color_string.startswith("#"):
        hex_color_string = hex_color_string[1:]

    # Ensure the string is the correct length
    if len(hex_color_string) == 8:
        hex_color_string = hex_color_string[2:]  # remove alpha
    elif len(hex_color_string) != 6:
        raise ValueError("Invalid hex color string length. Expected 6 characters.")

    # Extract R, G, B components and convert them to integers
    r = int(hex_color_string[0:2], 16)
    g = int(hex_color_string[2:4], 16)
    b = int(hex_color_string[4:6], 16)

    # Create and return the DB.Color object
    return DB.Color(r, g, b)


def hex_from_db_color(db_color):
    # color_value = "#{:02X}{:02X}{:02X}".format(db_color.Red,db_color.Green,db_color.Blue)
    # isn't working with IroPyton 2.7 so ...
    r = db_color.Red
    g = db_color.Green
    b = db_color.Blue

    # Use the reliable '%' formatting style
    color_value = "#%02X%02X%02X" % (r, g, b)
    return color_value


# --- UNIT PARSING FUNCTIONS ---


def dim_from_string(dim_as_string, is_metric):
    """
    Parses a string (e.g., "100", "1' 6\"", "7.5cm") into Revit's
    internal units (decimal feet) and the current display units (mm or in).
    Uses the user's current IS_METRIC setting to assume default units.

    Returns:
        (string, float): (value in current display units, value in internal units)
                        e.g., ("100", 0.328) for "100mm" if IS_METRIC
                        e.g., ("4", 0.333) for "4in" if not IS_METRIC
                        Returns (None, None) on failure.
    """
    dim_as_string = dim_as_string.strip()
    dim_int_units = None
    dim_display_units = None

    # If user just types a number, assume it's in the current unit system
    if dim_as_string.replace(".", "").isdigit():
        dim_as_string += " mm" if is_metric else '"'
    if (
        dim_as_string.replace(".", "").replace("/", "").replace(" ", "").isdigit()
        and not is_metric
    ):
        dim_as_string += '"'

    units = (
        DB.Units(DB.UnitSystem.Metric)
        if is_metric
        else DB.Units(DB.UnitSystem.Imperial)
    )
    unit_spec = DB.SpecTypeId.Length

    # TryParse will handle conversions (e.g., "1ft" in Metric mode)
    success, dim_int_units = DB.UnitFormatUtils.TryParse(
        units, unit_spec, dim_as_string
    )
    if not success and not is_metric:
        success, dim_int_units = DB.UnitFormatUtils.TryParse(
            units, DB.ForgeTypeId("autodesk.spec.aec:length-2.0.0"), dim_as_string + '"'
        )

    if success:
        dim_display_units = get_display_unit(dim_int_units, is_metric)
        return dim_display_units, dim_int_units

    return None, None


def get_display_unit(dim_int_units, is_metric):
    # Convert from internal feet to the user's selected display unit
    if is_metric:
        unit_type = DB.UnitTypeId.Millimeters
    else:
        unit_type = DB.UnitTypeId.Inches
    dim_display_units = DB.UnitUtils.ConvertFromInternalUnits(dim_int_units, unit_type)
    dim_display_units = round(dim_display_units, 2)
    if dim_display_units == int(dim_display_units):
        dim_as_string = str(
            int(dim_display_units)
        )  # avoid decimal and zero if is whole number
    else:
        dim_as_string = str(dim_display_units)
    return dim_as_string


# --- REVIT ELEMENT CREATION ---


def create_filled_region_type(doc, filled_region_name, fill_pattern_element):
    """
    Creates a new FilledRegionType that uses the given fill pattern.
    Returns (True/False, status_message)
    """
    # Check if a FilledRegionType with this name already exists
    # - Create Filter:
    param_id = DB.ElementId(DB.BuiltInParameter.ALL_MODEL_TYPE_NAME)
    param_val = DB.ParameterValueProvider(param_id)
    condition = DB.FilterStringEquals()
    if revit.HOST_APP.is_older_than(2022):
        filter_rule = DB.FilterStringRule(
            param_val, condition, filled_region_name, True
        )
    else:
        filter_rule = DB.FilterStringRule(param_val, condition, filled_region_name)

    filled_region_filter = DB.ElementParameterFilter(filter_rule)
    existing_type = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.FilledRegionType)
        .WherePasses(filled_region_filter)
        .FirstElement()
    )
    if existing_type:
        return False, "already exists"

    try:
        with Transaction("Create Filled Region Type: " + filled_region_name) as t:
            # Get a default type to duplicate
            default_type_id = doc.GetDefaultElementTypeId(
                DB.ElementTypeGroup.FilledRegionType
            )
            default_type = doc.GetElement(default_type_id)

            if not default_type:
                # Fallback to finding any solid fill
                solid_fill_id = DB.FilledRegionType.GetBuiltInFilledRegionTypeId(
                    DB.BuiltInFilledRegionType.SolidBlack
                )
                default_type = doc.GetElement(solid_fill_id)

            new_type = default_type.Duplicate(filled_region_name)

            # Set the foreground pattern
            new_type.ForegroundPatternId = fill_pattern_element.Id
            new_type.ForegroundPatternColor = DB.Color(0, 0, 0)  # Black lines

            # Ensure background is transparent
            new_type.BackgroundPatternId = DB.ElementId(-1)  # None
            new_type.BackgroundPatternColor = DB.Color(0, 0, 0)  # Black
            new_type.IsMasking = False

            # Set Line Weight
            new_type.LineWeight = 2

        return True, "created successfully"
    except Exception as e:
        return False, str(e)
