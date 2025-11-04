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
import ConfigParser

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
CONFIG_FILE = "pattern_settings.ini"

# --- DEFAULT NAMING TEMPLATES (Fallback) ---
# Used if the .ini file is missing or a key is not found
DEFAULT_TEMPLATES = {
    # Corrugated
    "corrugated_normal_map": "Corrugate-{spacing}x{height}_normal_{size}mm",
    "corrugated_bump_map": "Corrugate-{spacing}x{height}_bump_{size}mm",
    "corrugated_pattern_name": "Corrugate {spacing}x{height}",
    "corrugated_region_name": "Corrugate {spacing}x{height}",
    # Trapezoidal
    "trapezoidal_normal_map": "Trapezoidal-{rib_width}x{height}@{spacing}_normal_{size}mm",
    "trapezoidal_bump_map": "Trapezoidal-{rib_width}x{height}@{spacing}_bump_{size}mm",
    "trapezoidal_pattern_name": "Trapezoidal {rib_width}x{height}@{spacing}",
    "trapezoidal_region_name": "Trapezoidal {rib_width}x{height}@{spacing}",
    # Ribbed
    "ribbed_normal_map": "Ribbed-{thickness}x{height}@{spacing}_normal_{size}mm",
    "ribbed_bump_map": "Ribbed-{thickness}x{height}@{spacing}_bump_{size}mm",
    "ribbed_pattern_name": "Ribbed {thickness}x{height}@{spacing}",
    "ribbed_region_name": "Ribbed {thickness}x{height}@{spacing}",
}


# --- CONFIGURATION FUNCTIONS ---

def load_config():
    """Loads naming templates from 'roofing_config.ini'."""
    config = ConfigParser.ConfigParser()
    if os.path.exists(os.path.join(PATH_SCRIPT, CONFIG_FILE)):
        try:
            PATH_CONFIG = os.path.join(PATH_SCRIPT, CONFIG_FILE)
            config.read(PATH_CONFIG)
        except Exception as e:
            forms.alert(
                "Error reading config file, falling back to defaults. \nFile: {}\nError: ".format(PATH_CONFIG)
                + str(e),
                title = "Error reading config file"
            )
            return None  # Will trigger fallback
    elif os.path.exists(os.path.abspath(os.path.join(PATH_SCRIPT, "..", CONFIG_FILE))):
        try:
            PATH_CONFIG = os.path.abspath(os.path.join(PATH_SCRIPT, "..", CONFIG_FILE))
            config.read(PATH_CONFIG)
        except Exception as e:
            forms.alert(
                "Error reading config file, falling back to defaults. \nFile: {}\nError: ".format(PATH_CONFIG)
                + str(e),
                title = "Error reading config file"
            )
            return None  # Will trigger fallback
    return config


def get_template(config, profile_type, template_key):
    """
    Gets a specific naming template from the config,
    or falls back to the default.
    """
    key = "{}_{}".format(profile_type.lower(), template_key)
    if (
        config
        and config.has_section("Roofing Patterns")
        and config.has_option("Roofing Patterns", key)
    ):
        return config.get("Roofing Patterns", key)
    else:
        return DEFAULT_TEMPLATES.get(key, "Roofing")  # Fallback


# --- VALIDATION FUNCTIONS ---

def validate_trapezoid(spacing, rib_width, top_width):
    """Validates that trapezoid dimensions are geometrically possible."""
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
    if thickness >= spacing:
        forms.alert(
            "'Rib Thickness' must be less than 'Rib Spacing'.",
            title="Invalid Dimensions",
            exitscript=True,
        )
        return False
    return True


# --- IMAGE/PATTERN HELPER FUNCTIONS ---


def calculate_dimensions(rib_spacing_mm):
    """
    Calculates the real-world size and number of repeats for the texture.
    Ensures the texture is at least 300mm wide and has at least 3 repeats.
    """
    width_for_3_repeats = rib_spacing_mm * 3.0
    target_real_world_width = max(300.0, width_for_3_repeats)
    num_repeats = int(ceil(target_real_world_width / rib_spacing_mm))
    final_real_world_width = num_repeats * rib_spacing_mm
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
        spacing_feet = p_values["spacing"] / 304.8

        if profile_type == "Corrugated":
            # Create a single grid of parallel vertical lines
            grid1 = DB.FillGrid()
            grid1.Angle = pi / 2  # Vertical lines
            grid1.Origin = DB.UV(0, 0)
            grid1.Offset = spacing_feet  # Distance between lines
            grid1.Shift = 0
            grid1.SetSegments([])  # Solid line
            grids.append(grid1)

        elif profile_type == "Trapezoidal":
            rib_width_feet = p_values["rib_width"] / 304.8

            # Grid 1: First line of the pair
            grid1 = DB.FillGrid()
            grid1.Angle = pi / 2
            grid1.Origin = DB.UV(0, 0)
            grid1.Offset = spacing_feet  # The PAIR repeats at this offset
            grid1.Shift = 0
            grid1.SetSegments([])
            grids.append(grid1)

            # Grid 2: Second line of the pair, offset by the rib width
            grid2 = DB.FillGrid()
            grid2.Angle = pi / 2
            grid2.Origin = DB.UV(rib_width_feet, 0)  # Offset from the first line
            grid2.Offset = spacing_feet  # The PAIR repeats at this offset
            grid2.Shift = 0
            grid2.SetSegments([])
            grids.append(grid2)

        elif profile_type == "Ribbed":
            origin_offset_feet = (p_values["spacing"] / 2.0) / 304.8

            # Create a single grid of parallel vertical lines
            grid1 = DB.FillGrid()
            grid1.Angle = pi / 2
            grid1.Origin = DB.UV(origin_offset_feet, 0)
            grid1.Offset = spacing_feet
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


def get_corrugated_vector_func(spacing_mm, height_mm, num_repeats):
    """Returns a function that calculates the normal vector for a corrugated profile."""
    amplitude = height_mm / 2.0

    def get_vector_color(index, total_pixels):
        x = num_repeats * (float(index) / total_pixels)
        dz_dx = (2 * pi * amplitude / spacing_mm) * cos(2 * pi * x)
        magnitude = sqrt(dz_dx**2 + 1)
        nx = -dz_dx / magnitude
        ny = 0.0
        nz = 1 / magnitude
        r = int((nx * 0.5 + 0.5) * 255)
        g = int((ny * 0.5 + 0.5) * 255)
        b = int((nz * 0.5 + 0.5) * 255)
        return r, g, b

    return get_vector_color


def get_trapezoidal_vector_func(
    rib_width_mm, top_width_mm, spacing_mm, height_mm, num_repeats
):
    """Returns a function that calculates the normal vector for a trapezoidal profile."""
    slope_width = (spacing_mm - rib_width_mm - top_width_mm) / 2.0
    p1 = rib_width_mm
    p2 = p1 + slope_width
    p3 = p2 + top_width_mm
    slope = height_mm / slope_width if slope_width > 0 else 0
    total_width_mm = spacing_mm * num_repeats

    def get_vector_color(index, total_pixels):
        x_mm = total_width_mm * (float(index) / total_pixels)
        x_mod = x_mm % spacing_mm
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


def get_ribbed_vector_func(spacing_mm, thickness_mm, height_mm, num_repeats):
    """
    Returns a function that calculates the normal vector for a rounded
    (semi-elliptical) ribbed profile.
    """
    a = thickness_mm / 2.0  # semi-minor axis
    h = height_mm  # semi-major axis
    p1 = (spacing_mm - thickness_mm) / 2.0
    p2 = p1 + thickness_mm
    total_width_mm = spacing_mm * num_repeats
    # Pre-calculate constants for efficiency
    a_sq = a**2 if a > 0 else 0
    h_sq = h**2

    def get_vector_color(index, total_pixels):
        x_mm = total_width_mm * (float(index) / total_pixels)
        x_mod = x_mm % spacing_mm
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


def get_corrugated_height_func(height_mm, num_repeats):
    """Returns a function that calculates the height for a corrugated profile."""
    amplitude = height_mm / 2.0

    def get_height_color(index, total_pixels):
        x = num_repeats * (float(index) / total_pixels)
        # Shift sine wave to be in range [0, height_mm]
        height = amplitude * sin(2 * pi * x) + amplitude
        # Normalize to grayscale value
        gray = int((height / height_mm) * 255)
        return gray, gray, gray

    return get_height_color


def get_trapezoidal_height_func(
    rib_width_mm, top_width_mm, spacing_mm, height_mm, num_repeats
):
    """Returns a function that calculates the height for a trapezoidal profile."""
    slope_width = (spacing_mm - rib_width_mm - top_width_mm) / 2.0
    p1 = rib_width_mm
    p2 = p1 + slope_width
    p3 = p2 + top_width_mm
    slope = height_mm / slope_width if slope_width > 0 else 0
    total_width_mm = spacing_mm * num_repeats

    def get_height_color(index, total_pixels):
        x_mm = total_width_mm * (float(index) / total_pixels)
        x_mod = x_mm % spacing_mm
        height = 0.0
        if p1 <= x_mod < p2:
            height = slope * (x_mod - p1)
        elif p2 <= x_mod < p3:
            height = height_mm
        elif p3 <= x_mod:
            height = height_mm - slope * (x_mod - p3)
        gray = int((height / height_mm) * 255)
        return gray, gray, gray

    return get_height_color


def get_ribbed_height_func(spacing_mm, thickness_mm, height_mm, num_repeats):
    """
    Returns a function that calculates the height for a flat
    (rectangular) ribbed profile. (Black and White)
    """
    p1 = (spacing_mm - thickness_mm) / 2.0
    p2 = p1 + thickness_mm
    total_width_mm = spacing_mm * num_repeats

    def get_height_color(index, total_pixels):
        x_mm = total_width_mm * (float(index) / total_pixels)
        x_mod = x_mm % spacing_mm
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

        # Set diagram
        if profile_type == "Corrugated":
            self.CorrugatedInputs.Visibility = System.Windows.Visibility.Visible
            self.DiagramImage.Source = self.corrugated_diagram
            # Set default values
            self.SpacingInput.Text = "76"
            self.CorrugatedHeightInput.Text = "20"

        elif profile_type == "Trapezoidal":
            self.TrapezoidalInputs.Visibility = System.Windows.Visibility.Visible
            self.DiagramImage.Source = self.trapezoidal_diagram
            # Set default values
            self.SpacingInput.Text = "130"
            self.TrapezoidalHeightInput.Text = "40"
            self.TrapezoidalRibWidthInput.Text = "70"
            self.TrapezoidalTopWidthInput.Text = "20"

        elif profile_type == "Ribbed":
            self.RibbedInputs.Visibility = System.Windows.Visibility.Visible
            self.DiagramImage.Source = self.ribbed_diagram
            # Set default values
            self.SpacingInput.Text = "200"
            self.RibbedHeightInput.Text = "50"
            self.RibbedThicknessInput.Text = "15"

    def SubmitButton_Click(self, sender, e):
        """Main logic function. Gathers inputs and runs generators."""

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
        config = load_config()

        # --- Initialize variables ---
        image_size = 1024
        normal_vector_func = None
        bump_height_func = None
        real_world_dim = 0.0

        # Placeholders for formatting
        spacing, height, rib_width, top_width, thickness = (
            0.0,
            None,
            None,
            None,
            None,
        )

        try:
            # --- Get Universal Spacing ---
            spacing = float(self.SpacingInput.Text)

            # --- Get Profile-Specific Values ---
            if profile_type == "Corrugated":
                height = float(self.CorrugatedHeightInput.Text)

            elif profile_type == "Trapezoidal":
                height = float(self.TrapezoidalHeightInput.Text)
                rib_width = float(self.TrapezoidalRibWidthInput.Text)
                top_width = float(self.TrapezoidalTopWidthInput.Text)

                if not validate_trapezoid(spacing, rib_width, top_width):
                    return  # Validation failed

            elif profile_type == "Ribbed":
                height = float(self.RibbedHeightInput.Text)
                thickness = float(self.RibbedThicknessInput.Text)

                if not validate_ribbed(spacing, thickness):
                    return  # Validation failed

            # --- Calculate dimensions and get generator functions ---
            real_world_dim, repeats = calculate_dimensions(spacing)

            if profile_type == "Corrugated":
                normal_vector_func = get_corrugated_vector_func(
                    spacing, height, repeats
                )
                bump_height_func = get_corrugated_height_func(height, repeats)
            elif profile_type == "Trapezoidal":
                normal_vector_func = get_trapezoidal_vector_func(
                    rib_width, top_width, spacing, height, repeats
                )
                bump_height_func = get_trapezoidal_height_func(
                    rib_width, top_width, spacing, height, repeats
                )
            elif profile_type == "Ribbed":
                normal_vector_func = get_ribbed_vector_func(
                    spacing, thickness, height, repeats
                )
                bump_height_func = get_ribbed_height_func(
                    spacing, thickness, height, repeats
                )

            # --- Prepare placeholders for naming templates ---
            pattern_values = {
                "spacing": int(spacing),
                "height": int(height) if height is not None else 0,
                "rib_width": int(rib_width) if rib_width is not None else 0,
                "top_width": int(top_width) if top_width is not None else 0,
                "thickness": int(thickness) if thickness is not None else 0,
                "size": int(real_world_dim),
            }

            # --- Get Naming Templates ---
            pattern_name_template = get_template(
                config, profile_type, "pattern_name"
            )
            region_name_template = get_template(
                config, profile_type, "region_name"
            )
            normal_map_template = get_template(
                config, profile_type, "normal_map"
            )
            bump_map_template = get_template(config, profile_type, "bump_map")

            # --- Format Names ---
            pattern_name = pattern_name_template.format(**pattern_values)
            filled_region_name = region_name_template.format(**pattern_values)

            # --- Determine default filename for save dialog ---
            default_filename = ""
            if gen_normal:
                default_filename = normal_map_template.format(**pattern_values) + ".png"
            elif gen_bump:
                default_filename = bump_map_template.format(**pattern_values) + ".png"

        except (ValueError, TypeError):
            forms.alert(
                "Please ensure all dimension fields contain valid numbers.",
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
            pattern_element, reason = create_revit_fill_pattern(
                revit.doc, pattern_name, profile_type, pattern_values
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
                        revit.doc, pattern_name, pattern_element
                    )
                    if success:
                        fill_region_created_msg = (
                            "\nFilled Region Type '{}' created successfully.".format(
                                pattern_name
                            )
                        )
                    else:
                        fill_region_created_msg = "\nFilled Region Type '{}' not created (Reason: {}).".format(
                            pattern_name, fr_reason
                        )
                else:
                    fill_region_created_msg = "\nFilled Region Type not created (Fill Pattern '{}' could not be found or created).".format(
                        pattern_name
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
                                normal_map_template.format(**pattern_values) + ".png"
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
                                bump_map_template.format(**pattern_values) + ".png"
                            )
                            bump_path = os.path.join(save_dir, bump_filename)
                        else:
                            # Only bump selected: use the path from save dialog
                            bump_path = save_path

                    # --- Save Normal Map ---
                    if gen_normal and normal_path:
                        color_row = generate_color_row(image_size, normal_vector_func)
                        bitmap = create_bitmap_from_row(image_size, color_row)
                        bitmap.Save(
                            normal_path, System.Drawing.Imaging.ImageFormat.Png
                        )
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
                        saved_files_msg += "Width: {:.2f} mm\nHeight: {:.2f} mm".format(
                            real_world_dim, real_world_dim
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
