# -*- coding: utf-8 -*-
"""
Normal and Bump Map Generator for Corrugated, Trapezoidal, and Ribbed Profiles (IronPython).

This script uses a WPF/XAML interface.
It uses the .NET System.Drawing library for image generation.
It can also create a corresponding Revit Model Fill Pattern and Filled Region Type.
"""

# pyRevit Imports
from pyrevit import revit, script, forms, DB
from pyrevit.revit.db.transaction import Transaction

# Required Imports
import wpf
import sys
import os
from math import pi, cos, sin, ceil, sqrt

# Import Shared Config Library
import pattern_config

# .NET Imports
import clr
import System

clr.AddReference("System.Drawing")
from System.Drawing import Bitmap, Color

clr.AddReference("PresentationFramework")
from System.Windows import Window
from System import Uri
from System.Windows.Media.Imaging import BitmapImage

# Get the directory of the currently running script
PATH_SCRIPT = script.get_script_path()
CONFIG = script.get_config("patterns")
IS_METRIC = CONFIG.get_option("Metric", True)


# --- CONVERSION FUNCTIONS ---


def dim_from_string(dim_as_string):
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
        dim_as_string += " mm" if IS_METRIC else '"'
    if (
        dim_as_string.replace(".", "").replace("/", "").replace(" ", "").isdigit()
        and not IS_METRIC
    ):
        dim_as_string += '"'

    units = (
        DB.Units(DB.UnitSystem.Metric)
        if IS_METRIC
        else DB.Units(DB.UnitSystem.Imperial)
    )
    unit_spec = DB.SpecTypeId.Length

    # TryParse will handle conversions (e.g., "1ft" in Metric mode)
    success, dim_int_units = DB.UnitFormatUtils.TryParse(
        units, unit_spec, dim_as_string
    )
    if not success and not IS_METRIC:
        success, dim_int_units = DB.UnitFormatUtils.TryParse(
            units, DB.ForgeTypeId("autodesk.spec.aec:length-2.0.0"), dim_as_string + '"'
        )

    if success:
        dim_display_units = get_display_unit(dim_int_units)
        return dim_display_units, dim_int_units

    return None, None


def get_display_unit(dim_int_units):
    # Convert from internal feet to the user's selected display unit
    if IS_METRIC:
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


# --- VALIDATION FUNCTIONS ---


def validate_trapezoid(spacing, rib_width, top_width):
    """Validates that trapezoid dimensions are geometrically possible."""
    # This check is unit-agnostic as it's a simple ratio
    if (rib_width + top_width) >= spacing:
        forms.alert(
            "The sum of 'Rib Width' and 'Top Width' must be less than the 'Rib Spacing'.",
            title="Invalid Dimensions",
            exitscript=True,
        )
        return False
    return True


def validate_ribbed(spacing, thickness):
    """Validates that ribbed dimensions are geometrically possible."""
    # This check is unit-agnostic
    if thickness >= spacing:
        forms.alert(
            "'Rib Thickness' must be less than 'Rib Spacing'.",
            title="Invalid Dimensions",
            exitscript=True,
        )
        return False
    return True


# --- IMAGE/PATTERN HELPER FUNCTIONS ---


def calculate_dimensions(rib_spacing_int):
    """
    Calculates the real-world size and number of repeats for the texture.
    Ensures the texture is at least 1' or 300mm wide and has at least 3 repeats.
    """
    width_for_3_repeats = rib_spacing_int * 3.0
    target_real_world_width = max(
        (300.0 / 304.8 if IS_METRIC else 1.0), width_for_3_repeats
    )
    num_repeats = int(ceil(target_real_world_width / rib_spacing_int))
    final_real_world_width = num_repeats * rib_spacing_int
    return final_real_world_width, num_repeats


def generate_color_row(pixel_count, generation_func):
    """
    Generates a single row of pixel colors by calling a generation function
    for each pixel.
    """
    color_row = []
    for i in range(pixel_count):
        color_components = generation_func(i, pixel_count)
        color_row.append(Color.FromArgb(*color_components))
    return color_row


def create_bitmap_from_row(image_size, color_row):
    """Creates a .NET Bitmap by tiling a single row of colors."""
    bitmap = Bitmap(image_size, image_size)
    for y in range(image_size):
        for x in range(image_size):
            bitmap.SetPixel(x, y, color_row[x])
    return bitmap


# --- Revit pattern and filled region functions ---


def create_revit_fill_pattern(doc, pattern_name, profile_type, p_values):
    """
    Creates or retrieves a Revit model fill pattern with parallel lines.
    For Corrugated: Creates one line per repeat.
    For Trapezoidal: Creates two lines per repeat (at base of rib).
    For Ribbed: Creates one line per repeat.
    Returns (FillPatternElement, status_message)
    """
    # Check if a model pattern with this name already exists
    existing = DB.FillPatternElement.GetFillPatternElementByName(
        doc, DB.FillPatternTarget.Model, pattern_name
    )
    if existing:
        return existing, "already exists"

    try:
        # Create the fill pattern definition
        fill_pattern = DB.FillPattern(
            pattern_name,
            DB.FillPatternTarget.Model,
            DB.FillPatternHostOrientation.ToHost,
        )
        grids = []
        spacing_int = p_values["spacing"]

        if profile_type == "Corrugated":
            # Create a single grid of parallel vertical lines
            grid1 = DB.FillGrid()
            grid1.Angle = pi / 2  # Vertical lines
            grid1.Origin = DB.UV(0, 0)
            grid1.Offset = spacing_int  # Distance between lines
            grid1.Shift = 0
            grid1.SetSegments([])  # Solid line
            grids.append(grid1)

        elif profile_type == "Trapezoidal":
            rib_width_int = p_values["rib_width"]

            # Grid 1: First line of the pair
            grid1 = DB.FillGrid()
            grid1.Angle = pi / 2
            grid1.Origin = DB.UV(0, 0)
            grid1.Offset = spacing_int  # The PAIR repeats at this offset
            grid1.Shift = 0
            grid1.SetSegments([])
            grids.append(grid1)

            # Grid 2: Second line of the pair, offset by the rib width
            grid2 = DB.FillGrid()
            grid2.Angle = pi / 2
            grid2.Origin = DB.UV(rib_width_int, 0)  # Offset from the first line
            grid2.Offset = spacing_int  # The PAIR repeats at this offset
            grid2.Shift = 0
            grid2.SetSegments([])
            grids.append(grid2)

        elif profile_type == "Ribbed":
            origin_offset_int = p_values["spacing"] / 2.0

            # Create a single grid of parallel vertical lines
            grid1 = DB.FillGrid()
            grid1.Angle = pi / 2
            grid1.Origin = DB.UV(origin_offset_int, 0)
            grid1.Offset = spacing_int
            grid1.Shift = 0
            grid1.SetSegments([])
            grids.append(grid1)

        fill_pattern.SetFillGrids(grids)

        # Create the fill pattern element inside a transaction
        with Transaction("Create Fill Pattern: " + pattern_name) as rvt_transaction:
            fill_pattern_element = DB.FillPatternElement.Create(doc, fill_pattern)

        return fill_pattern_element, "created successfully"
    except Exception as e:
        return None, str(e)


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


# --- Normal Map Vector Functions ---
# (These functions are unit-agnostic as they operate on ratios,
#  but they expect all inputs to be in the SAME unit, e.g., mm)


def get_corrugated_vector_func(spacing, height, num_repeats):
    """Returns a function that calculates the normal vector for a corrugated profile."""
    amplitude = height / 2.0

    def get_vector_color(index, total_pixels):
        x = num_repeats * (float(index) / total_pixels)
        dz_dx = (2 * pi * amplitude / spacing) * cos(2 * pi * x)
        magnitude = sqrt(dz_dx**2 + 1)
        nx = -dz_dx / magnitude
        ny = 0.0
        nz = 1 / magnitude
        r = int((nx * 0.5 + 0.5) * 255)
        g = int((ny * 0.5 + 0.5) * 255)
        b = int((nz * 0.5 + 0.5) * 255)
        return r, g, b

    return get_vector_color


def get_trapezoidal_vector_func(rib_width, top_width, spacing, height, num_repeats):
    """Returns a function that calculates the normal vector for a trapezoidal profile."""
    slope_width = (spacing - rib_width - top_width) / 2.0
    p1 = rib_width
    p2 = p1 + slope_width
    p3 = p2 + top_width
    slope = height / slope_width if slope_width > 0 else 0
    total_width = spacing * num_repeats

    def get_vector_color(index, total_pixels):
        x_width = total_width * (float(index) / total_pixels)
        x_mod = x_width % spacing
        dz_dx = 0
        if p1 <= x_mod < p2:
            dz_dx = slope
        elif p3 <= x_mod:
            dz_dx = -slope
        magnitude = sqrt(dz_dx**2 + 1)
        nx = -dz_dx / magnitude
        ny = 0.0
        nz = 1 / magnitude
        r = int((nx * 0.5 + 0.5) * 255)
        g = int((ny * 0.5 + 0.5) * 255)
        b = int((nz * 0.5 + 0.5) * 255)
        return r, g, b

    return get_vector_color


def get_ribbed_vector_func(spacing, thickness, height, num_repeats):
    """
    Returns a function that calculates the normal vector for a rounded
    (semi-elliptical) ribbed profile.
    """
    a = thickness / 2.0  # semi-minor axis
    h = height  # semi-major axis
    p1 = (spacing - thickness) / 2.0
    p2 = p1 + thickness
    total_width = spacing * num_repeats
    # Pre-calculate constants for efficiency
    a_sq = a**2 if a > 0 else 0
    h_sq = h**2

    def get_vector_color(index, total_pixels):
        x_width = total_width * (float(index) / total_pixels)
        x_mod = x_width % spacing
        dz_dx = 0.0
        if p1 <= x_mod < p2 and a_sq > 0:
            x_rel = x_mod - (p1 + a)  # Center x on the rib, range [-a, a]
            z_term_sq = 1.0 - (x_rel**2 / a_sq)
            if z_term_sq > 0.00001:  # Check if inside the ellipse and not at the edge
                z = h * sqrt(z_term_sq)
                if z > 0.0001:  # Avoid division by zero at the peak
                    dz_dx = -(h_sq * x_rel) / (a_sq * z)
        magnitude = sqrt(dz_dx**2 + 1.0)
        nx = -dz_dx / magnitude
        ny = 0.0
        nz = 1.0 / magnitude
        r = int((nx * 0.5 + 0.5) * 255)
        g = int((ny * 0.5 + 0.5) * 255)
        b = int((nz * 0.5 + 0.5) * 255)
        return r, g, b

    return get_vector_color


# --- Bump Map Height Functions ---


def get_corrugated_height_func(height, num_repeats):
    """Returns a function that calculates the height for a corrugated profile."""
    amplitude = height / 2.0

    def get_height_color(index, total_pixels):
        x = num_repeats * (float(index) / total_pixels)
        # Shift sine wave to be in range [0, height]
        y_height = amplitude * sin(2 * pi * x) + amplitude
        # Normalize to grayscale value
        gray = int((y_height / height) * 255)
        return gray, gray, gray

    return get_height_color


def get_trapezoidal_height_func(rib_width, top_width, spacing, height, num_repeats):
    """Returns a function that calculates the height for a trapezoidal profile."""
    slope_width = (spacing - rib_width - top_width) / 2.0
    p1 = rib_width
    p2 = p1 + slope_width
    p3 = p2 + top_width
    slope = height / slope_width if slope_width > 0 else 0
    total_width = spacing * num_repeats

    def get_height_color(index, total_pixels):
        x_width = total_width * (float(index) / total_pixels)
        x_mod = x_width % spacing
        y_height = 0.0
        if p1 <= x_mod < p2:
            y_height = slope * (x_mod - p1)
        elif p2 <= x_mod < p3:
            y_height = height
        elif p3 <= x_mod:
            y_height = height - slope * (x_mod - p3)
        gray = int((y_height / height) * 255)
        return gray, gray, gray

    return get_height_color


def get_ribbed_height_func(spacing, thickness, height, num_repeats):
    """
    Returns a function that calculates the height for a flat
    (rectangular) ribbed profile. (Black and White)
    """
    p1 = (spacing - thickness) / 2.0
    p2 = p1 + thickness
    total_width = spacing * num_repeats

    def get_height_color(index, total_pixels):
        x_width = total_width * (float(index) / total_pixels)
        x_mod = x_width % spacing
        gray = 0
        if p1 <= x_mod < p2:
            gray = 255
        return gray, gray, gray

    return get_height_color


# --- UI & Generation ---


class RoofingForm(Window):
    def __init__(self):
        # Load XAML file
        path_xaml_file = os.path.join(PATH_SCRIPT, "roofpatternUI.xaml")
        wpf.LoadComponent(self, path_xaml_file)

        # Set unit radio buttons based on saved pyRevit config
        self.MetricRadioButton.IsChecked = IS_METRIC
        self.ImperialRadioButton.IsChecked = not IS_METRIC
        self._update_ui_for_units()

        # Load image assets (Icons and Diagrams)
        # Assumes images are in the same folder as the script
        try:
            # --- Load Icons ---
            self.IconCorrugated.Source = BitmapImage(
                Uri(os.path.join(PATH_SCRIPT, "icon_corrugated.png"))
            )
            self.IconTrapezoidal.Source = BitmapImage(
                Uri(os.path.join(PATH_SCRIPT, "icon_trapezoidal.png"))
            )
            self.IconRibbed.Source = BitmapImage(
                Uri(os.path.join(PATH_SCRIPT, "icon_ribbed.png"))
            )

            # --- Pre-load diagram URIs ---
            self.corrugated_diagram = BitmapImage(
                Uri(os.path.join(PATH_SCRIPT, "diagram_corrugated.png"))
            )
            self.trapezoidal_diagram = BitmapImage(
                Uri(os.path.join(PATH_SCRIPT, "diagram_trapezoidal.png"))
            )
            self.ribbed_diagram = BitmapImage(
                Uri(os.path.join(PATH_SCRIPT, "diagram_ribbed.png"))
            )

            # Set initial diagram
            self.DiagramImage.Source = self.corrugated_diagram

        except Exception as e:
            forms.alert(
                "Could not load UI images. "
                "Make sure icon_*.png and diagram_*.png files are in the script bundle.",
                title="UI Error",
            )

        # Show the form
        self.ShowDialog()

    def _update_ui_for_units(self):
        """Updates UI text and default values based on unit system."""
        global IS_METRIC
        IS_METRIC = self.MetricRadioButton.IsChecked

        unit_suffix = "(mm)" if IS_METRIC else "(in)"
        self.DimensionsGroup.Header = "Dimensions " + unit_suffix

        # Set appropriate default values
        if self.RadioCorrugated.IsChecked:
            self.SpacingInput.Text = "76" if IS_METRIC else "2 2/3"
            self.CorrugatedHeightInput.Text = "20" if IS_METRIC else "7/8"
        elif self.RadioTrapezoidal.IsChecked:
            self.SpacingInput.Text = "130" if IS_METRIC else "5.125"
            self.TrapezoidalHeightInput.Text = "40" if IS_METRIC else "1.5"
            self.TrapezoidalRibWidthInput.Text = "70" if IS_METRIC else "2.75"
            self.TrapezoidalTopWidthInput.Text = "25" if IS_METRIC else "0.75"
        elif self.RadioRibbed.IsChecked:
            self.SpacingInput.Text = "340" if IS_METRIC else "8"
            self.RibbedHeightInput.Text = "50" if IS_METRIC else "2"
            self.RibbedThicknessInput.Text = "20" if IS_METRIC else "0.625"

    def Unit_Changed(self, sender, e):
        """Fires when Metric or Imperial radio buttons are clicked."""
        self._update_ui_for_units()

    def RoofType_Changed(self, sender, e):
        """Hides and shows input fields based on roof type selection."""

        # Determine which radio button is checked
        profile_type = "Corrugated"  # Default
        if self.RadioTrapezoidal.IsChecked:
            profile_type = "Trapezoidal"
        elif self.RadioRibbed.IsChecked:
            profile_type = "Ribbed"

        # Set visibility for input panels
        self.CorrugatedInputs.Visibility = System.Windows.Visibility.Collapsed
        self.TrapezoidalInputs.Visibility = System.Windows.Visibility.Collapsed
        self.RibbedInputs.Visibility = System.Windows.Visibility.Collapsed

        # Set diagram and default values
        if profile_type == "Corrugated":
            self.CorrugatedInputs.Visibility = System.Windows.Visibility.Visible
            self.DiagramImage.Source = self.corrugated_diagram
            self.SpacingInput.Text = "76" if IS_METRIC else "3"
            self.CorrugatedHeightInput.Text = "20" if IS_METRIC else "0.75"

        elif profile_type == "Trapezoidal":
            self.TrapezoidalInputs.Visibility = System.Windows.Visibility.Visible
            self.DiagramImage.Source = self.trapezoidal_diagram
            self.SpacingInput.Text = "130" if IS_METRIC else "5.125"
            self.TrapezoidalHeightInput.Text = "40" if IS_METRIC else "1.5"
            self.TrapezoidalRibWidthInput.Text = "70" if IS_METRIC else "2.75"
            self.TrapezoidalTopWidthInput.Text = "20" if IS_METRIC else "0.75"

        elif profile_type == "Ribbed":
            self.RibbedInputs.Visibility = System.Windows.Visibility.Visible
            self.DiagramImage.Source = self.ribbed_diagram
            self.SpacingInput.Text = "200" if IS_METRIC else "8"
            self.RibbedHeightInput.Text = "50" if IS_METRIC else "2"
            self.RibbedThicknessInput.Text = "15" if IS_METRIC else "0.625"

    def SubmitButton_Click(self, sender, e):
        """Main logic function. Gathers inputs and runs generators."""
        global IS_METRIC

        # --- 1. Get User Settings (Units & Outputs) ---

        # Get unit selection from UI and save if it changed
        is_metric_ui = self.MetricRadioButton.IsChecked
        if is_metric_ui != IS_METRIC:
            CONFIG.set_option("Metric", is_metric_ui)
            script.save_config()
            IS_METRIC = is_metric_ui  # Update global for this session

        # Get selected outputs
        gen_normal = self.CheckNormal.IsChecked
        gen_bump = self.CheckBump.IsChecked
        gen_pattern = self.CheckPattern.IsChecked
        gen_fillregion = self.CheckFillRegion.IsChecked

        if not gen_normal and not gen_bump and not gen_pattern and not gen_fillregion:
            forms.alert(
                "No outputs selected. Nothing to generate.", title="Action Cancelled"
            )
            return

        # Get profile type
        profile_type = "Corrugated"
        if self.RadioTrapezoidal.IsChecked:
            profile_type = "Trapezoidal"
        elif self.RadioRibbed.IsChecked:
            profile_type = "Ribbed"

        # Load naming config
        config = pattern_config.load_config(PATH_SCRIPT)
        CONFIG_SECTION = "Roofing Patterns"

        # --- 2. Initialize and Parse All Dimensions ---
        image_size = 1024
        normal_vector_func = None
        bump_height_func = None

        # These store Revit's internal unit (decimal feet)
        (
            spacing_int,
            height_int,
            rib_width_int,
            top_width_int,
            thickness_int,
            real_world_dim_int,
        ) = (None, None, None, None, None, 0.0)

        # These store the display value (mm or in) for naming
        (
            spacing_display,
            height_display,
            rib_width_display,
            top_width_display,
            thickness_display,
            real_world_dim_display,
        ) = ("0", "0", "0", "0", "0", "0")

        try:
            # --- Get Universal Spacing ---
            spacing_display, spacing_int = dim_from_string(self.SpacingInput.Text)
            if not spacing_int:
                raise ValueError("Invalid Rib Spacing")

            # --- Get Profile-Specific Values ---
            if profile_type == "Corrugated":
                height_display, height_int = dim_from_string(
                    self.CorrugatedHeightInput.Text
                )

            elif profile_type == "Trapezoidal":
                height_display, height_int = dim_from_string(
                    self.TrapezoidalHeightInput.Text
                )
                rib_width_display, rib_width_int = dim_from_string(
                    self.TrapezoidalRibWidthInput.Text
                )
                top_width_display, top_width_int = dim_from_string(
                    self.TrapezoidalTopWidthInput.Text
                )

                if not rib_width_int or not top_width_int:
                    raise ValueError("Invalid Trapezoidal Dimensions")
                if not validate_trapezoid(spacing_int, rib_width_int, top_width_int):
                    return  # Validation failed

            elif profile_type == "Ribbed":
                height_display, height_int = dim_from_string(
                    self.RibbedHeightInput.Text
                )
                thickness_display, thickness_int = dim_from_string(
                    self.RibbedThicknessInput.Text
                )

                if not thickness_int:
                    raise ValueError("Invalid Ribbed Dimensions")
                if not validate_ribbed(spacing_int, thickness_int):
                    return  # Validation failed

            if not height_int:
                raise ValueError("Invalid Height")

            # --- Calculate dimensions and get generator functions ---
            real_world_dim_int, repeats = calculate_dimensions(spacing_int)
            real_world_dim_display = get_display_unit(real_world_dim_int)

            if profile_type == "Corrugated":
                normal_vector_func = get_corrugated_vector_func(
                    spacing_int, height_int, repeats
                )
                bump_height_func = get_corrugated_height_func(height_int, repeats)
            elif profile_type == "Trapezoidal":
                normal_vector_func = get_trapezoidal_vector_func(
                    rib_width_int, top_width_int, spacing_int, height_int, repeats
                )
                bump_height_func = get_trapezoidal_height_func(
                    rib_width_int, top_width_int, spacing_int, height_int, repeats
                )
            elif profile_type == "Ribbed":
                normal_vector_func = get_ribbed_vector_func(
                    spacing_int, thickness_int, height_int, repeats
                )
                bump_height_func = get_ribbed_height_func(
                    spacing_int, thickness_int, height_int, repeats
                )

            # --- Prepare placeholders for naming templates ---
            pattern_values_display = {
                "spacing": spacing_display,
                "height": height_display,
                "rib_width": rib_width_display,
                "top_width": top_width_display,
                "thickness": thickness_display,
                "size": real_world_dim_display,
                "unit": "mm" if IS_METRIC else "in",
            }

            # --- Get Naming Templates ---
            key_suffix = profile_type.lower()
            pattern_name_template = pattern_config.get_template(
                config, CONFIG_SECTION, key_suffix + "_pattern_name"
            )
            region_name_template = pattern_config.get_template(
                config, CONFIG_SECTION, key_suffix + "_region_name"
            )
            normal_map_template = pattern_config.get_template(
                config, CONFIG_SECTION, key_suffix + "_normal_map"
            )
            bump_map_template = pattern_config.get_template(
                config, CONFIG_SECTION, key_suffix + "_bump_map"
            )

            # --- Format Names ---
            pattern_name = pattern_name_template.format(**pattern_values_display)
            filled_region_name = region_name_template.format(**pattern_values_display)

            # --- Determine default filename for save dialog ---
            default_filename = ""
            if gen_normal:
                default_filename = (
                    normal_map_template.format(**pattern_values_display) + ".png"
                )
            elif gen_bump:
                default_filename = (
                    bump_map_template.format(**pattern_values_display) + ".png"
                )

        except (ValueError, TypeError) as e:
            forms.alert(
                "Please ensure all dimension fields contain valid numbers.\nError: "
                + str(e),
                title="Invalid Input",
                exitscript=True,
            )
            return
        except Exception as e:
            forms.alert(
                "An unexpected error occurred during setup: " + str(e),
                title="Error",
                exitscript=True,
            )
            return

        # If we are here, inputs are valid. Close the form.
        self.Close()

        # --- Run Generation Logic ---

        # --- Create Fill Pattern and/or Filled Region if requested ---
        pattern_created_msg = ""
        fill_region_created_msg = ""
        pattern_element = None

        if gen_pattern or gen_fillregion:
            pattern_values_int = {
                "spacing": spacing_int,
                "height": height_int,
                "rib_width": rib_width_int,
                "top_width": top_width_int,
                "thickness": thickness_int,
                "size": real_world_dim_int,
            }

            pattern_element, reason = create_revit_fill_pattern(
                revit.doc, pattern_name, profile_type, pattern_values_int
            )

            if gen_pattern:
                if pattern_element:
                    pattern_created_msg = "\n\nFill Pattern '{}' {}.".format(
                        pattern_name, reason
                    )
                else:
                    pattern_created_msg = (
                        "\n\nFill Pattern '{}' not created (Reason: {}).".format(
                            pattern_name, reason
                        )
                    )

            if gen_fillregion:
                if pattern_element:
                    success, fr_reason = create_filled_region_type(
                        revit.doc, filled_region_name, pattern_element
                    )
                    if success:
                        fill_region_created_msg = (
                            "\nFilled Region Type '{}' created successfully.".format(
                                filled_region_name
                            )
                        )
                    else:
                        fill_region_created_msg = "\nFilled Region Type '{}' not created (Reason: {}).".format(
                            filled_region_name, fr_reason
                        )
                else:
                    fill_region_created_msg = "\nFilled Region Type not created (Fill Pattern '{}' could not be found or created).".format(
                        filled_region_name
                    )

        # --- Generate and Save Image Files if requested ---
        saved_files_msg = ""
        if gen_normal or gen_bump:
            save_path = forms.save_file(
                files_filter="PNG Image (*.png)|*.png",
                title="Save Normal Map Image",
                default_name=default_filename,
            )

            if save_path:
                saved_files = []
                save_dir = os.path.dirname(save_path)
                try:
                    # --- Determine Normal Map Path ---
                    normal_path = None
                    if gen_normal:
                        if gen_bump:
                            # Both selected: get explicit name for normal map
                            normal_filename = (
                                normal_map_template.format(**pattern_values_display)
                                + ".png"
                            )
                            normal_path = os.path.join(save_dir, normal_filename)
                        else:
                            # Only normal selected: use the path from save dialog
                            normal_path = save_path

                    # --- Determine Bump Map Path ---
                    bump_path = None
                    if gen_bump:
                        if gen_normal:
                            # Both selected: get explicit name for bump map
                            bump_filename = (
                                bump_map_template.format(**pattern_values_display)
                                + ".png"
                            )
                            bump_path = os.path.join(save_dir, bump_filename)
                        else:
                            # Only bump selected: use the path from save dialog
                            bump_path = save_path

                    # --- Save Normal Map ---
                    if gen_normal and normal_path:
                        color_row = generate_color_row(image_size, normal_vector_func)
                        bitmap = create_bitmap_from_row(image_size, color_row)
                        bitmap.Save(normal_path, System.Drawing.Imaging.ImageFormat.Png)
                        saved_files.append(normal_path)

                    # --- Save Bump Map ---
                    if gen_bump and bump_path:
                        color_row = generate_color_row(image_size, bump_height_func)
                        bitmap = create_bitmap_from_row(image_size, color_row)
                        bitmap.Save(bump_path, System.Drawing.Imaging.ImageFormat.Png)
                        saved_files.append(bump_path)

                    # --- Format Save Message ---
                    if saved_files:
                        saved_files_msg = "Files saved successfully:\n" + "\n".join(
                            saved_files
                        )
                        saved_files_msg += "\n\nFor use in the Revit material editor, set the texture map size to:\n"
                        saved_files_msg += "Width: {size:.2f} {unit}\nHeight: {size:.2f} {unit}".format(
                            size=float(real_world_dim_display),
                            unit=pattern_values_display["unit"],
                        )

                except Exception as e:
                    forms.alert(str(e), title="Error Saving File")

        # --- Show Final Summary ---
        final_message = (
            saved_files_msg + pattern_created_msg + fill_region_created_msg
        ).strip()
        if final_message:
            forms.alert(final_message, title="Generation Complete")


# Main execution point
if __name__ == "__main__":
    # Create and show the form
    form = RoofingForm()
