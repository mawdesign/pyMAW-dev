# -*- coding: utf-8 -*-
"""
Normal and Bump Map Generator for Corrugated and Trapezoidal Profiles (IronPython).

This script is compatible with pyRevit's IronPython 2.7 environment.
It uses rpw FlexForm for user input and the .NET System.Drawing library
for image generation, removing the need for NumPy and Pillow. It can also
create a corresponding Revit Model Fill Pattern.

It calculates the required image size to ensure a tileable texture
that represents a real-world area of at least 300mm with at least 3 repeats.
Finally, it prompts the user to save the file(s) and displays the
real-world dimensions for use in Revit's material editor.
"""

# Required Imports
import sys
import os
from math import pi, cos, sin, ceil, sqrt

# .NET Imports for Image Generation
import clr
clr.AddReference('System.Drawing')
from System.Drawing import Bitmap, Color
from System.Drawing.Imaging import ImageFormat

from pyrevit import forms, DB, revit, HOST_APP
from pyrevit.revit.db.transaction import Transaction
from rpw import ui
from rpw.ui.forms import (FlexForm, Label, ComboBox, TextBox, Separator,
                          Button, CheckBox)


def validate_trapezoid_inputs(values):
    """Validates that trapezoid dimensions are geometrically possible."""
    try:
        rib_width = float(values['trap_rib_width'])
        top_width = float(values['trap_top_width'])
        spacing = float(values['trap_spacing'])

        if (rib_width + top_width) >= spacing:
            ui.forms.Alert(
                "Invalid Dimensions",
                header="The sum of 'Rib Width' and 'Top Width' must be less than the 'Rib Spacing'.",
                exit=True
            )
        return True
    except (ValueError, TypeError):
        ui.forms.Alert("Invalid Input", header="Please enter valid numbers for all dimensions.", exit=True)
        return False


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

def create_revit_fill_pattern(doc, pattern_name, profile_type, values):
    """
    Creates or retrieves a Revit model fill pattern with parallel lines.
    For Corrugated: Creates one line per repeat.
    For Trapezoidal: Creates two lines per repeat (at base of rib).
    Returns (FillPatternElement, status_message)
    """
    # Check if a model pattern with this name already exists
    existing = DB.FillPatternElement.GetFillPatternElementByName(doc, DB.FillPatternTarget.Model, pattern_name)
    if existing:
        return existing, "already exists"

    try:
        # Create the fill pattern definition
        fill_pattern = DB.FillPattern(pattern_name, DB.FillPatternTarget.Model, DB.FillPatternHostOrientation.ToHost)
        grids = []

        if profile_type == 'Corrugated':
            spacing_mm = float(values['corr_spacing'])
            spacing_feet = spacing_mm / 304.8

            # Create a single grid of parallel vertical lines
            grid1 = DB.FillGrid()
            grid1.Angle = pi / 2  # Vertical lines
            grid1.Origin = DB.UV(0, 0)
            grid1.Offset = spacing_feet # Distance between lines
            grid1.Shift = 0
            grid1.SetSegments([]) # Solid line
            grids.append(grid1)

        elif profile_type == 'Trapezoidal':
            spacing_mm = float(values['trap_spacing'])
            rib_width_mm = float(values['trap_rib_width'])
            
            spacing_feet = spacing_mm / 304.8
            rib_width_feet = rib_width_mm / 304.8

            # Grid 1: First line of the pair
            grid1 = DB.FillGrid()
            grid1.Angle = pi / 2
            grid1.Origin = DB.UV(0, 0)
            grid1.Offset = spacing_feet # The PAIR repeats at this offset
            grid1.Shift = 0
            grid1.SetSegments([])
            grids.append(grid1)
            
            # Grid 2: Second line of the pair, offset by the rib width
            grid2 = DB.FillGrid()
            grid2.Angle = pi / 2
            grid2.Origin = DB.UV(rib_width_feet, 0) # Offset from the first line
            grid2.Offset = spacing_feet # The PAIR repeats at this offset
            grid2.Shift = 0
            grid2.SetSegments([])
            grids.append(grid2)

        fill_pattern.SetFillGrids(grids)

        # Create the fill pattern element inside a transaction
        with Transaction('Create Fill Pattern: ' + pattern_name) as rvt_transaction:
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
    param_id  = DB.ElementId(DB.BuiltInParameter.ALL_MODEL_TYPE_NAME)
    param_val = DB.ParameterValueProvider(param_id)
    condition = DB.FilterStringEquals()
    if HOST_APP.is_older_than(2022):
        filter_rule = DB.FilterStringRule(param_val, condition, filled_region_name, True)
    else:
        filter_rule = DB.FilterStringRule(param_val, condition, filled_region_name)
    
    filled_region_filter = DB.ElementParameterFilter(filter_rule)
    existing_type = DB.FilteredElementCollector(doc).OfClass(DB.FilledRegionType)\
        .WherePasses(filled_region_filter).FirstElement()
    if existing_type:
        return False, "already exists"

    try:
        with Transaction('Create Filled Region Type: ' + filled_region_name) as t:
            # Get a default type to duplicate
            default_type_id = doc.GetDefaultElementTypeId(DB.ElementTypeGroup.FilledRegionType)
            default_type = doc.GetElement(default_type_id)
            
            if not default_type:
                # Fallback to finding any solid fill
                solid_fill_id = DB.FilledRegionType.GetBuiltInFilledRegionTypeId(DB.BuiltInFilledRegionType.SolidBlack)
                default_type = doc.GetElement(solid_fill_id)

            new_type = default_type.Duplicate(filled_region_name)
            
            # Set the foreground pattern
            new_type.ForegroundPatternId = fill_pattern_element.Id
            new_type.ForegroundPatternColor = DB.Color(0, 0, 0) # Black lines
            
            # Ensure background is transparent
            new_type.BackgroundPatternId = DB.ElementId(-1) #None
            new_type.BackgroundPatternColor = DB.Color(0, 0, 0) # Black
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


def get_trapezoidal_vector_func(rib_width_mm, top_width_mm, spacing_mm, height_mm, num_repeats):
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


def get_trapezoidal_height_func(rib_width_mm, top_width_mm, spacing_mm, height_mm, num_repeats):
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


def show_ui_and_generate():
    """Defines and shows the FlexForm UI, then triggers generation."""
    components = [
        Label('Select Roofing Profile and Dimensions (in mm)'),
        ComboBox('profile_type', {'Corrugated': 'Corrugated', 'Trapezoidal': 'Trapezoidal'}),
        Separator(),
        Label('CORRUGATED PROFILE SETTINGS:'),
        Label('Rib Spacing:'),
        TextBox('corr_spacing', Text="76", default="76"),
        Label('Rib Height:'),
        TextBox('corr_height', Text="20", default="20"),
        Separator(),
        Label('TRAPEZOIDAL PROFILE SETTINGS:'),
        Label('Rib Width (Bottom):'),
        TextBox('trap_rib_width', Text="70", default="70"),
        Label('Top Width:'),
        TextBox('trap_top_width', Text="20", default="20"),
        Label('Rib Spacing:'),
        TextBox('trap_spacing', Text="130", default="130"),
        Label('Profile Height:'),
        TextBox('trap_height', Text="40", default="40"),
        Separator(),
        Label('SELECT OUTPUTS:'),
        CheckBox('gen_normal', 'Generate Normal Map', default=True),
        CheckBox('gen_bump', 'Generate Bump Map', default=True),
        CheckBox('gen_pattern', 'Create Revit Model Fill Pattern', default=False),
        CheckBox('gen_fillregion', 'Create Revit Filled Region', default=False),
        Separator(),
        Button('Generate')
    ]
    form = FlexForm('Map Generator', components)
    form.show()

    if not form.values:
        return

    values = form.values
    if not values['gen_normal'] and not values['gen_bump'] and not values['gen_pattern']:
        forms.alert("No outputs selected. Nothing to generate.", title="Action Cancelled")
        return

    profile_type = values['profile_type']
    image_size = 1024
    default_filename = ""
    pattern_name = ""
    spacing = 0.0
    
    try:
        if profile_type == 'Corrugated':
            spacing = float(values['corr_spacing'])
            height = float(values['corr_height'])
            default_filename = "Corrugate-{}x{}_normal.png".format(int(spacing), int(height))
            pattern_name = "Corrugate {}x{}".format(int(spacing), int(height))
            
            real_world_dim, repeats = calculate_dimensions(spacing)
            normal_vector_func = get_corrugated_vector_func(spacing, height, repeats)
            bump_height_func = get_corrugated_height_func(height, repeats)
            
        elif profile_type == 'Trapezoidal':
            validate_trapezoid_inputs(values)
            rib_width = float(values['trap_rib_width'])
            top_width = float(values['trap_top_width'])
            spacing = float(values['trap_spacing'])
            height = float(values['trap_height'])
            default_filename = "Trapezoidal-{}x{}@{}_normal.png".format(int(rib_width), int(height), int(spacing))
            pattern_name = "Trapezoidal {}x{}@{}".format(int(rib_width), int(height), int(spacing))

            real_world_dim, repeats = calculate_dimensions(spacing)
            normal_vector_func = get_trapezoidal_vector_func(rib_width, top_width, spacing, height, repeats)
            bump_height_func = get_trapezoidal_height_func(rib_width, top_width, spacing, height, repeats)

    except (ValueError, TypeError):
        ui.forms.Alert("Invalid Input", header="Please ensure all dimension fields contain valid numbers.", exit=True)
        return
    except Exception as e:
        ui.forms.Alert("An unexpected error occurred during setup.", header=str(e), exit=True)
        return

    # --- Create Fill Pattern and/or Filled Region if requested ---
    pattern_created_msg = ""
    fill_region_created_msg = ""
    pattern_element = None
    
    if values['gen_pattern'] or values['gen_fillregion']:
        # Need to get/create the pattern if either is checked
        pattern_element, reason = create_revit_fill_pattern(revit.doc, pattern_name, profile_type, values)
        
        if values['gen_pattern']: # Only report pattern status if user asked for it
            if pattern_element:
                pattern_created_msg = "\n\nFill Pattern '{}' {}.".format(pattern_name, reason)
            else:
                pattern_created_msg = "\n\nFill Pattern '{}' not created (Reason: {}).".format(pattern_name, reason)

        if values['gen_fillregion']:
            if pattern_element:
                success, fr_reason = create_filled_region_type(revit.doc, pattern_name, pattern_element)
                if success:
                    fill_region_created_msg = "\nFilled Region Type '{}' created successfully.".format(pattern_name)
                else:
                    fill_region_created_msg = "\nFilled Region Type '{}' not created (Reason: {}).".format(pattern_name, fr_reason)
            else:
                fill_region_created_msg = "\nFilled Region Type not created (Fill Pattern '{}' could not be found or created).".format(pattern_name)

    # --- Generate and Save Image Files if requested ---
    saved_files_msg = ""
    if values['gen_normal'] or values['gen_bump']:
        save_path = forms.save_file(files_filter='PNG Image (*.png)|*.png',
                                    title="Save Normal Map Image",
                                    default_name=default_filename)
        
        if save_path:
            saved_files = []
            try:
                # Generate and save Normal Map
                if values['gen_normal']:
                    color_row = generate_color_row(image_size, normal_vector_func)
                    bitmap = create_bitmap_from_row(image_size, color_row)
                    bitmap.Save(save_path, ImageFormat.Png)
                    saved_files.append(save_path)

                # Generate and save Bump Map
                if values['gen_bump']:
                    base, ext = os.path.splitext(save_path)
                    if base.endswith('_normal'):
                        bump_path = base.replace('_normal', '_bump') + ext
                    else:
                        bump_path = base + '_bump' + ext

                    color_row = generate_color_row(image_size, bump_height_func)
                    bitmap = create_bitmap_from_row(image_size, color_row)
                    bitmap.Save(bump_path, ImageFormat.Png)
                    saved_files.append(bump_path)
                
                if saved_files:
                    saved_files_msg = "Files saved successfully:\n" + "\n".join(saved_files)
                    saved_files_msg += "\n\nFor use in the Revit material editor, set the texture map size to:\n"
                    saved_files_msg += "Width: {:.2f} mm\nHeight: {:.2f} mm".format(real_world_dim, real_world_dim)

            except Exception as e:
                ui.forms.Alert(str(e), title="Error Saving File")
    
    # --- Show Final Summary ---
    final_message = (saved_files_msg + pattern_created_msg + fill_region_created_msg).strip()
    if final_message:
        forms.alert(final_message, title="Generation Complete")


# Main execution point
if __name__ == '__main__':
    show_ui_and_generate()

