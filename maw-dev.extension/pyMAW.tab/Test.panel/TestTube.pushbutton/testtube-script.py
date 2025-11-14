# -*- coding: utf-8 -*-
"""
Shared library for creating and updating Revit Materials,
specifically for applying surface patterns and appearance assets
like bump maps with real-world scaling.
"""

# pyRevit Imports
from pyrevit import revit, script, forms, DB
from pyrevit.revit.db.transaction import Transaction

# .NET Imports
import clr
import System
from System.Collections.Generic import IList
import traceback  # <--- ADDED FOR DETAILED ERROR LOGGING

clr.AddReference("System.Core")
clr.AddReference("System")


def _get_material_by_name(doc, name):
    """Finds an existing material by name."""
    collector = DB.FilteredElementCollector(doc).OfClass(DB.Material)
    for mat in collector:
        if mat.Name == name:
            return mat
    return None


def _find_generic_asset_template(doc):
    """
    Finds a 'Generic' Asset to use as a template for creating
    new Appearance Assets.
    Searches Document assets first, then Application (library) assets.
    (Based on logic from material_tools.py)
    """
    # 1. Search Document Assets
    doc_assets = [
        elem.GetRenderingAsset()
        for elem in DB.FilteredElementCollector(doc)
        .OfClass(DB.AppearanceAssetElement)
        .ToElements()
    ]
    generic_asset_template = next(
        (
            a
            for a in doc_assets
            if a.FindByName(DB.Visual.Generic.GenericDiffuse)
        ),
        None,
    )

    if generic_asset_template:
        return generic_asset_template

    # 2. Search Application (Library) Assets
    app_assets = doc.Application.GetAssets(DB.Visual.AssetType.Appearance)
    generic_asset_template = next(
        (
            a
            for a in app_assets
            if a.FindByName(DB.Visual.Generic.GenericDiffuse)
        ),
        None,
    )

    if generic_asset_template:
        return generic_asset_template

    # 3. Fail
    return None


def _create_new_appearance_asset(doc, asset_name):
    """
    Creates a new AppearanceAssetElement by finding a "Generic" template
    and using it as a base.
    Returns the ElementId of the new asset.
    (Based on logic from material_tools.py)
    """
    # Find a "Generic" asset to use as a template
    generic_asset_template = _find_generic_asset_template(doc)

    if not generic_asset_template:
        forms.alert("Could not find any 'Generic' appearance asset to duplicate.")
        return DB.ElementId.InvalidElementId

    try:
        # Create the new AppearanceAssetElement
        new_asset_elem = DB.AppearanceAssetElement.Create(
            doc, asset_name, generic_asset_template
        )
        return new_asset_elem.Id
    except Exception as e:
        print("Error creating new appearance asset: {}".format(e))
        return DB.ElementId.InvalidElementId


def create_or_update_material(
    doc,
    material_name,
    material_color,
    surface_pattern_element,
    bump_map_path,
    texture_real_world_width_int,
    texture_real_world_height_int,
):
    """
    Creates a new material or updates an existing one with graphics
    and appearance properties.
    """
    if (
        not bump_map_path
        or not System.IO.File.Exists(bump_map_path)
    ):
        return None, "Bump map file not found at path: {}".format(bump_map_path)

    if not surface_pattern_element:
        return None, "Invalid surface pattern element provided."

    try:
        # --- 1. Get or Create Material ---
        material = _get_material_by_name(doc, material_name)
        is_new_material = False

        # All modifications, including material creation, must be inside.
        with Transaction(
            "Create/Update Material: " + material_name
        ) as rvt_transaction:

            if not material:
                material_id = DB.Material.Create(doc, material_name)
                material = doc.GetElement(material_id)
                is_new_material = True

            # --- 2. Set Graphics Properties ---
            material.Color = material_color
            material.SurfaceForegroundPatternId = surface_pattern_element.Id
            # Set pattern color to black (common for roofing)
            material.SurfaceForegroundPatternColor = DB.Color(0, 0, 0)
            material.Transparency = 0
            material.UseRenderAppearanceForShading = True

            # --- 3. Get or Create Appearance Asset ---
            appearance_asset_id = material.AppearanceAssetId
            if appearance_asset_id == DB.ElementId.InvalidElementId:
                # Material has no appearance, create one
                appearance_asset_id = _create_new_appearance_asset(
                    doc, material_name + " Appearance"
                )
                if appearance_asset_id != DB.ElementId.InvalidElementId:
                    material.AppearanceAssetId = appearance_asset_id
                else:
                    rvt_transaction.RollBack()
                    return None, "Failed to create new appearance asset."

            appearance_asset_elem = doc.GetElement(appearance_asset_id)
            rendering_asset = appearance_asset_elem.GetRenderingAsset()

            # --- 4. Edit the Appearance Asset (The Hard Part) ---
            with DB.Visual.AppearanceAssetEditScope(doc) as edit_scope:
                # Start editing the asset
                editable_asset = edit_scope.Start(appearance_asset_id)

                # --- ADDED: Reset properties to default (from ref file) ---
                prop_bool = editable_asset.FindByName(
                    DB.Visual.Generic.CommonTintToggle
                )
                if prop_bool:
                    prop_bool.Value = True

                prop_bool = editable_asset.FindByName(
                    DB.Visual.Generic.GenericIsMetal
                )
                if prop_bool:
                    prop_bool.Value = False

                prop_double = editable_asset.FindByName(
                    DB.Visual.Generic.GenericDiffuseImageFade
                )
                if prop_double and prop_double.IsEditable:
                    prop_double.Value = 0.0

                prop_double = editable_asset.FindByName(
                    DB.Visual.Generic.GenericTransparency
                )
                if prop_double and prop_double.IsEditable:
                    prop_double.Value = 0.0

                prop_double = editable_asset.FindByName(
                    DB.Visual.Generic.GenericGlossiness
                )
                if prop_double and prop_double.IsEditable:
                    prop_double.Value = 0.1

                prop_double = editable_asset.FindByName(
                    DB.Visual.Generic.GenericReflectivityAt0deg
                )
                if prop_double and prop_double.IsEditable:
                    prop_double.Value = 0.1

                prop_double = editable_asset.FindByName(
                    DB.Visual.Generic.GenericReflectivityAt90deg
                )
                if prop_double and prop_double.IsEditable:
                    prop_double.Value = 0.0

                prop_color = editable_asset.FindByName(
                    DB.Visual.Generic.CommonTintColor
                )
                if prop_color:
                    prop_color.SetValueAsColor(DB.Color(127, 127, 127))

                prop_color = editable_asset.FindByName(
                    DB.Visual.Generic.GenericDiffuse
                )
                if prop_color:
                    prop_color.SetValueAsDoubles([0.95, 0.95, 0.9, 1.0])
                    connected_color_asset = prop_color.GetSingleConnectedAsset()
                    if connected_color_asset:
                        # Find the target asset path property
                        color_bitmap_property = connected_color_asset.FindByName(DB.Visual.UnifiedBitmap.UnifiedbitmapBitmap) # AssetPropertyString
                        # ensure no image from copied material asset
                        if color_bitmap_property:
                            color_bitmap_property.Value = ""

                # --- Find the Bump Map Property ---
                bump_map_prop = editable_asset.FindByName(
                    DB.Visual.Generic.GenericBumpMap
                )
                if not bump_map_prop:
                    print("Could not find 'Generic.BumpMap' property")
                    edit_scope.Cancel()
                    return None, "Could not find 'Generic.BumpMap' property"
                    
                # --- Get or Create the Texture Asset (UnifiedBitmap) ---
                texture_asset = None
                if bump_map_prop.GetSingleConnectedAsset():
                    texture_asset = bump_map_prop.GetSingleConnectedAsset()
                else:
                    # Create and connect a new UnifiedBitmap
                    bump_map_prop.AddConnectedAsset(
                        DB.Visual.UnifiedBitmap.__name__
                    )
                    texture_asset = bump_map_prop.GetSingleConnectedAsset()

                # --- Edit the Texture Asset Properties (Merged Logic) ---
                if texture_asset:
                    # 1. Set the file path (from reference file)
                    source_prop = texture_asset.FindByName(
                        DB.Visual.UnifiedBitmap.UnifiedbitmapBitmap
                    )
                    if source_prop:
                        if source_prop.IsValidValue(bump_map_path):
                            source_prop.Value = bump_map_path
                        else:
                            print(
                                "Warning: Invalid value for bump map path: {}".format(
                                    bump_map_path
                                )
                            )
                    else:
                        print(
                            "Could not find 'UnifiedBitmap.UnifiedbitmapBitmap' property"
                        )

                    # # 2. Set Texture Mode to "Real World"
                    # mapping_prop = texture_asset.FindByName(
                        # DB.Visual.UnifiedBitmap.WCSMappingType
                    # )
                    # if mapping_prop:
                        # mapping_prop.Value = DB.Visual.WCSMappingType.RealWorld
                    # else:
                        # print(
                            # "Could not find 'UnifiedBitmap.WCSMappingType' property"
                        # )

                    # 3. Set Real World Scale (U = Width, V = Height)
                    scale_u_prop = texture_asset.FindByName(
                        DB.Visual.UnifiedBitmap.TextureRealWorldScaleX
                    )
                    if scale_u_prop:
                        scale_u_prop.Value = (
                            texture_real_world_width_int * 12 # image scale seems to be in inches?
                        )
                    else:
                        print(
                            "Could not find 'UnifiedBitmap.RealWorldScaleU' property"
                        )

                    scale_v_prop = texture_asset.FindByName(
                        DB.Visual.UnifiedBitmap.TextureRealWorldScaleY
                    )
                    if scale_v_prop:
                        scale_v_prop.Value = (
                            texture_real_world_height_int * 12 # image scale seems to be in inches?
                        )
                    else:
                        print(
                            "Could not find 'UnifiedBitmap.RealWorldScaleV' property"
                        )

                    # 4. Set Offset to 0
                    offset_u_prop = texture_asset.FindByName(
                        DB.Visual.UnifiedBitmap.TextureRealWorldOffsetX
                    )
                    if offset_u_prop:
                        offset_u_prop.Value = 0.0

                    offset_v_prop = texture_asset.FindByName(
                        DB.Visual.UnifiedBitmap.TextureRealWorldOffsetY
                    )
                    if offset_v_prop:
                        offset_v_prop.Value = 0.0
                else:
                    print("Could not create or find connected texture asset.")

                # Commit the changes to the asset
                edit_scope.Commit(True)

            status_msg = "Material '{}' created.".format(material_name)
            if not is_new_material:
                status_msg = "Material '{}' updated.".format(material_name)

            return material, status_msg

    except Exception as e:
        # --- ADDED FULL TRACEBACK LOGGING ---
        print("--- ERROR IN create_or_update_material ---")
        print(traceback.format_exc())
        print("--- END ERROR ---")
        return None, "Failed to create/update material: {}".format(e)


# --- TEST HARNESS ---
# This part only runs if you execute this script directly
if __name__ == "__main__":
    doc = revit.doc
    uidoc = revit.uidoc

    print("Running Material Generator Test...")

    # --- 1. Set Up Test Data ---
    TEST_MATERIAL_NAME = "Test Roofing Material"
    TEST_MATERIAL_COLOR = DB.Color(150, 150, 150)
    TEST_PATTERN_NAME = "Vertical"  # <--- MUST exist in your project
    TEST_TEXTURE_WIDTH_INT = 2.0  # 2.0 feet
    TEST_TEXTURE_HEIGHT_INT = 2.0  # 2.0 feet

    # --- 2. Get Test Fill Pattern ---
    test_pattern = DB.FillPatternElement.GetFillPatternElementByName(
        doc, DB.FillPatternTarget.Model, TEST_PATTERN_NAME
    )
    if not test_pattern:
        forms.alert(
            "Test aborted. Please create a Model Fill Pattern named '{}' to run this test.".format(
                TEST_PATTERN_NAME
            ),
            title="Test Setup Error",
            exitscript=True,
        )

    # --- 3. Get Test Bump Map ---
    # test_bump_path = forms.pick_file(
        # file_ext="png",
        # multi_file=False,
        # title="Select a PNG file to use as the test bump map",
    # )
    test_bump_path = r"C:\Users\warwickm\Downloads\Standing Seam-2@8_bump-24in.png"
    if not test_bump_path:
        forms.alert("Test aborted. No bump map selected.", title="Test Cancelled")
    else:
        print("Test Parameters:")
        print("  Material Name: {}".format(TEST_MATERIAL_NAME))
        print("  Pattern Name: {}".format(TEST_PATTERN_NAME))
        print("  Texture Path: {}".format(test_bump_path))
        print(
            "  Texture Size: {}' x {}'".format(
                TEST_TEXTURE_WIDTH_INT, TEST_TEXTURE_HEIGHT_INT
            )
        )

        # --- 4. Run the Function ---
        # Added try/except here as well to catch any errors
        try:
            # --- FIXED ARGUMENT LIST ---
            material, message = create_or_update_material(
                doc,
                TEST_MATERIAL_NAME,
                TEST_MATERIAL_COLOR,
                test_pattern,
                test_bump_path,
                TEST_TEXTURE_WIDTH_INT,
                TEST_TEXTURE_HEIGHT_INT,
            )
        except Exception as e:
            # --- ADDED FULL TRACEBACK LOGGING ---
            print("--- ERROR IN TEST HARNESS CALL ---")
            print(traceback.format_exc())
            print("--- END ERROR ---")
            material = None
            message = "Test harness caught an exception: {}".format(e)

        # --- 5. Report Results ---
        if material:
            print(message)
            forms.alert(message, title="Test Complete")
            # Select and show the new material in the project browser
            uidoc.Selection.SetElementIds(
                System.Array[DB.ElementId]([material.Id])
            )
            uidoc.ShowElements(material.Id)
        else:
            print("Test Failed: {}".format(message))
            forms.alert(message, title="Test Failed")

    print("Test finished.")


### END HERE

# # -*- coding: utf-8 -*-
# """
# BIM Parameter Tools - Revit API Formatting Tester

# This script provides a simple UI to test the UnitFormatUtils.Format method.
# It allows a user to input a raw value, a spec ForgeTypeId, a unit ForgeTypeId,
# and formatting options to see the resulting string from the Revit API.

# This is useful for understanding how Revit handles rounding, symbols, and
# other formatting rules before implementing them in a larger tool.
# """
# # ------------------------------------------------------------------------------
# # Preamble
# # ------------------------------------------------------------------------------
# __title__ = "Format Tester"
# __author__ = "BIM Parameter Tools Contributor"
# __doc__ = "A simple tool to test the Revit API's UnitFormatUtils.Format method."

# # ------------------------------------------------------------------------------
# # Imports
# # ------------------------------------------------------------------------------
# # Import necessary components from pyRevit and standard libraries
# from pyrevit import forms
# from pyrevit import revit, script
# from rpw.ui.forms import (FlexForm, Label, ComboBox, TextBox, Separator,
                            # Button, CheckBox)

# # Import Revit API components for unit formatting
# from Autodesk.Revit.DB import ForgeTypeId, UnitUtils, UnitFormatUtils, FormatOptions, FormatValueOptions

# # ------------------------------------------------------------------------------
# # Main Script Logic
# # ------------------------------------------------------------------------------

# def test_formatter():
    # """
    # Prompts the user for input and displays the formatted string.
    # """
    # # 1. Get input from the user using a simple pyRevit form.
    # # We provide default values that are known to work for easy testing.
    # components = [Label("Enter details to test the UnitFormatUtils.Format method:"),
                    # Label("value"),
                    # TextBox("value", Text="1234.5004"),
                    # Label("spec_id"),
                    # TextBox("spec_id", Text="autodesk.spec.aec:length-1.0.0"),
                    # Label("unit_id"),
                    # TextBox("unit_id", Text="autodesk.unit.unit:millimeters-1.0.1"),
                    # Label("decimals"),
                    # TextBox("decimals", Text="2"),
                    # CheckBox("suppress_trailing_zeros","suppress_trailing_zeros"),
                    # Separator(),
                    # Button("Okay"),
                    # ]
    # res = FlexForm("Unit Format Tester", components)

    # # Exit if the user cancels the form
    # if not res.show():
        # print("Operation cancelled.")
        # return

    # # 2. Parse and validate the user's input.
    # try:
        # value_to_format = float(res.values["value"])
        # decimal_places = int(res.values["decimals"])
        # spec_type_id = ForgeTypeId(res.values["spec_id"])
        # unit_type_id = ForgeTypeId(res.values["unit_id"])
        # suppress_trailing_zeros = res.values["suppress_trailing_zeros"]
        # value_to_format = UnitUtils.ConvertToInternalUnits(value_to_format, unit_type_id)
    # except (ValueError, TypeError) as e:
        # forms.alert("Invalid input. Please ensure the value and decimals are numbers and the IDs are correct.\n\nError: {}".format(e))
        # return

    # print("--- Input Data ---")
    # print("Value: {}".format(value_to_format))
    # print("Spec ID: {}".format(spec_type_id.TypeId))
    # print("Unit ID: {}".format(unit_type_id.TypeId))
    # print("Decimals: {}".format(decimal_places))
    # print("Suppress Trailing Zeros: {}".format(suppress_trailing_zeros))
    # print("--------------------")

    # # 3. Create and configure the FormatOptions object.
    # # This object tells the API how we want the final string to look.
    # try:
        # # Get the default format options for the specified unit
        # units = revit.doc.GetUnits()
        # format_options = units.GetFormatOptions(spec_type_id)

        # # We must set UseDefault to False to apply our custom settings.
        # format_options.UseDefault = False
        # # https://www.revitapidocs.com/2022/4b317c87-727e-b8e9-3f0b-2b5479090fb7.htm
        # format_options.SetUnitTypeId(unit_type_id)
        
        # # Set the rounding precision
        # format_options.Accuracy = 1.0 / (10 ** decimal_places)
        
        # # Set other common formatting properties
        # format_options.SuppressTrailingZeros = suppress_trailing_zeros
        # format_options.SuppressLeadingZeros = False

        # # Check if the unit can have a symbol and, if so, apply the first one.
        # # This is the key to showing units like "mm", "m²", etc.
        # if format_options.CanHaveSymbol():
            # # GetValidSymbols() returns a list of ForgeTypeIds for symbols
            # valid_symbols = format_options.GetValidSymbols()
            # if valid_symbols and valid_symbols.Count > 1:
                # # Set the symbol to the first one in the list
                # format_options.SetSymbolTypeId(valid_symbols[1])
                # print("Applied symbol: {}".format(valid_symbols[1].TypeId))
            # else:
                # print("Unit can have a symbol, but none were found.")
        # else:
            # print("This unit type does not support symbols.")

    # except Exception as e:
        # print("Failed to create or configure FormatOptions.\n"
              # "Please check if the Unit ID is valid.\n\nError: {}".format(e))
        # raise e
        # return

    # # 5. Call the main formatting function from the Revit API.
    # try:
        # # The 'SuppressSpaces' argument is a boolean that controls spacing
        # # between the number and the symbol. We set it to False for readability.
        # format_value_options = FormatValueOptions()
        # format_value_options.SetFormatOptions(format_options)
        # formatted_string = UnitFormatUtils.Format(
            # units,
            # spec_type_id,
            # value_to_format,
            # False, # forEditing
            # format_value_options # FormatValueOptions
        # )

        # # 6. Display the final result to the user.
        # print("Formatted String: '{}'".format(formatted_string))
        # forms.alert(
            # "Input Value: {}\nFormatted String: {}".format(value_to_format, formatted_string),
            # title="Formatting Result"
        # )

    # except Exception as e:
        # print("An error occurred during formatting.\n"
              # "Please ensure the Spec ID is compatible with the Unit ID.\n\n"
              # "Error: {}".format(e))
        # raise e


# # ------------------------------------------------------------------------------
# # Script Execution
# # ------------------------------------------------------------------------------
# if __name__ == "__main__":
    # test_formatter()


# # -*- coding: UTF-8 -*-

# # from pyrevit import HOST_APP
# # from pyrevit import revit
# # from pyrevit import DB, UI
# from pyrevit import forms

# # from pyrevit.revit import query
# # from pyrevit.framework import List
# # from pyrevit.revit import Transaction
# # from pyrevit.revit.db.transaction import Transaction
# # from pyrevit.revit import create
# # from pyrevit import script
# # from pyrevit import EXEC_PARAMS
# # from rpws import RevitServer
# # import os
# # import json
# # import xlrd
# # import re
# # import sys


# # create a python function to extract a vector outline from a black and white image

# """
# Creating a vector outline from a black and white image involves several 
# steps, including image processing to detect edges and then vectorizing 
# those edges. One popular library for image processing in Python is OpenCV, 
# and for vector graphics, you can use libraries like `svgwrite` or `shapely`.

# Here’s a step-by-step function that uses OpenCV to detect edges and then 
# converts those edges to a vector format using `svgwrite`.

# First, make sure you have the necessary libraries installed:
# ```sh
# pip install opencv-python-headless numpy svgwrite
# ```

# Now, here's the Python function to extract a vector outline from a black 
# and white image:
# """
# import cv2
# import numpy as np
# import svgwrite


# def extract_vector_outline(image_path, output_svg_path):
    # # Load the image
    # image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

    # # Check if the image is loaded properly
    # if image is None:
        # raise ValueError(f"Image at path {image_path} could not be loaded.")

    # # Detect edges using Canny edge detector
    # edges = cv2.Canny(image, 100, 200)

    # # Find contours from the edges
    # contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # # Create an SVG drawing
    # dwg = svgwrite.Drawing(output_svg_path, profile="tiny")

    # # Add contours to the SVG drawing
    # for contour in contours:
        # # Convert contour to a list of tuples
        # points = [(point[0][0], point[0][1]) for point in contour]
        # # Add the contour as a polyline to the SVG drawing
        # dwg.add(dwg.polyline(points, stroke=svgwrite.rgb(0, 0, 0, "%"), fill="none"))

    # # Save the SVG file
    # dwg.save()


# # Example usage
# extract_vector_outline("input_image.png", "output_vector.svg")
# """
# ### Explanation:
# 1. **Loading the Image**: The function reads the image in grayscale mode 
# using `cv2.imread()`.
# 2. **Edge Detection**: The `cv2.Canny()` function is used to detect edges 
# in the image. The thresholds (100 and 200) can be adjusted based on the 
# image characteristics.
# 3. **Finding Contours**: The `cv2.findContours()` function retrieves the 
# contours from the edge-detected image. `cv2.RETR_EXTERNAL` retrieves only 
# the external contours, and `cv2.CHAIN_APPROX_SIMPLE` compresses horizontal, 
# vertical, and diagonal segments and leaves only their end points.
# 4. **Creating SVG**: The `svgwrite` library is used to create an SVG file. 
# Each contour is added as a polyline to the SVG drawing.
# 5. **Saving the SVG**: The `dwg.save()` function saves the SVG file to the 
# specified path.

# This function should work for most simple black and white images to extract 
# vector outlines. For more complex images or specific use cases, additional 
# processing steps might be required.

# To extract a vector outline from a black and white image in Python, you can 
# use libraries like OpenCV for image processing and NumPy for handling 
# arrays. The process typically involves the following steps:

# 1. Load the image.
# 2. Convert it to grayscale (if it isn't already).
# 3. Apply edge detection to find the outlines.
# 4. Use contour detection to extract the vector outline.
# 5. Optionally, draw the contours on a blank canvas.

# Here's a simple implementation of these steps:

# """
# import cv2
# import numpy as np


# def extract_vector_outline(image_path, output_path):
    # # Load the image
    # image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

    # # Check if the image is loaded properly
    # if image is None:
        # raise ValueError("Image not found or unable to load.")

    # # Apply GaussianBlur to reduce noise and improve edge detection
    # blurred = cv2.GaussianBlur(image, (5, 5), 0)

    # # Use Canny edge detection to find edges
    # edges = cv2.Canny(blurred, 50, 150)

    # # Find contours from the edges
    # contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # # Create a blank image to draw contours
    # outline_image = np.zeros_like(image)

    # # Draw contours on the blank image
    # cv2.drawContours(outline_image, contours, -1, (255), thickness=cv2.FILLED)

    # # Save the output image
    # cv2.imwrite(output_path, outline_image)

    # return contours  # Returning contours for further processing if needed


# # Example usage
# if __name__ == "__main__":
    # input_image_path = "path_to_your_image.jpg"
    # output_image_path = "output_vector_outline.png"

    # contours = extract_vector_outline(input_image_path, output_image_path)
    # print(f"Extracted {len(contours)} contours.")
# """

# ### Explanation:
# - **Loading the Image**: The image is loaded in grayscale mode.
# - **Gaussian Blur**: This step helps reduce noise which can affect edge 
# detection.
# - **Canny Edge Detection**: This algorithm detects edges in the image.
# - **Contour Detection**: Contours are detected from the edges.
# - **Drawing Contours**: The contours are drawn on a blank image.
# - **Saving the Result**: The result is saved as a new image file.

# ### Requirements:
# Make sure you have the required libraries installed. You can install them 
# using pip:

# ```bash
# pip install opencv-python numpy
# ```

# ### Note:
# - Adjust the parameters in `Canny` and `GaussianBlur` for different images 
# to get better results.
# - This function assumes that the input image is a black-and-white image. If 
# you have a colored image, you may need to convert it to grayscale first.

# Certainly! A flood fill algorithm is often used in image processing to 
# determine the area connected to a given node in a multi-dimensional array. 
# Below is a Python function that implements the flood fill algorithm using 
# recursion. This function takes an image (as a 2D list or a NumPy array) and 
# a starting point (x, y) and returns a mask indicating the filled area.

# Here's a simple implementation using NumPy:

# ```python
# import numpy as np
# """


# def flood_fill(image, start_point, target_color=None):
    # """
    # Perform a flood fill on the image starting from the start_point.

    # Parameters:
        # image (numpy.ndarray): The input image as a 2D array.
        # start_point (tuple): The (x, y) coordinates to start the flood fill.
        # target_color (int or tuple): The color to fill with. If None, it 
            # will fill with the color of the start point.

    # Returns:
        # numpy.ndarray: A mask indicating the filled area.
    # """
    # # Get the dimensions of the image
    # height, width = image.shape[:2]

    # # Get the color at the start point
    # x, y = start_point
    # if target_color is None:
        # target_color = image[x, y]

    # # Create a mask to keep track of the filled areas
    # mask = np.zeros_like(image, dtype=bool)

    # # Define the flood fill function
    # def fill(x, y):
        # # Check if the current position is out of bounds
        # if x < 0 or x >= height or y < 0 or y >= width:
            # return
        # # Check if the current position is already filled or not the target color
        # if mask[x, y] or not np.array_equal(image[x, y], target_color):
            # return

        # # Fill the current position
        # mask[x, y] = True

        # # Recursively fill in all four directions
        # fill(x + 1, y)  # Down
        # fill(x - 1, y)  # Up
        # fill(x, y + 1)  # Right
        # fill(x, y - 1)  # Left

    # # Start the flood fill
    # fill(x, y)

    # return mask


# # Example usage
# if __name__ == "__main__":
    # # Create a sample image (3x3 with different colors)
    # image = np.array([[1, 1, 0], [1, 0, 0], [0, 0, 0]])

    # start_point = (1, 1)  # Starting point for flood fill
    # mask = flood_fill(image, start_point)

    # print("Original Image:")
    # print(image)
    # print("Flood Fill Mask:")
    # print(mask)
# """

# ### Explanation:
# - The `flood_fill` function initializes the flood fill process by checking 
# the color of the starting point.
# - It uses a nested `fill` function to perform the recursive filling. It 
# checks boundaries and whether the pixel has already been filled or matches 
# the target color.
# - The mask is a boolean array of the same shape as the input image, where 
# `True` indicates a filled pixel.

# ### Note:
# - The function assumes that the input image is in a format that can be 
# represented as a 2D array (e.g., grayscale or binary). If working with 
# colored images, you might need to adapt the color comparison accordingly.
# - For large images or deep recursion, consider implementing an iterative 
# approach to avoid stack overflow issues.

# Creating a paint fill (also known as flood fill) algorithm in Python can be 
# accomplished using various libraries, such as OpenCV or PIL (Pillow). Below 
# is an example of how you can implement a flood fill algorithm using the 
# OpenCV library. This function will take an image and a point (x, y) as 
# input and fill the area with a specified color.

# First, ensure you have OpenCV installed. You can install it using pip if 
# you haven't done so:

# ```bash
# pip install opencv-python
# ```

# Here's the code for the flood fill function:

# """
# import cv2
# import numpy as np


# def flood_fill(image_path, point, fill_color):
    # # Read the image
    # image = cv2.imread(image_path)

    # # Check if the image is loaded
    # if image is None:
        # print("Error: Could not read the image.")
        # return None

    # # Convert the fill color from RGB to BGR (OpenCV uses BGR format)
    # fill_color = (
        # fill_color[2],
        # fill_color[1],
        # fill_color[0],
    # )  # Convert from RGB to BGR

    # # Get the coordinates of the point
    # x, y = point

    # # Perform the flood fill operation
    # # Use the flags cv2.FLOODFILL_MASK_ONLY to create a mask
    # mask = np.zeros((image.shape[0] + 2, image.shape[1] + 2), np.uint8)
    # cv2.floodFill(image, mask, (x, y), fill_color)

    # # Save or display the result
    # cv2.imshow("Flood Fill Result", image)
    # cv2.waitKey(0)
    # cv2.destroyAllWindows()

    # return image


# # Example usage
# if __name__ == "__main__":
    # image_path = "path/to/your/image.jpg"  # Specify the path to your image
    # point = (100, 100)  # Specify the point (x, y) where the flood fill should start
    # fill_color = (255, 0, 0)  # Specify the fill color in RGB (red in this case)

    # flood_fill(image_path, point, fill_color)
# """

# ### Explanation:
# - **Image Loading**: The function reads an image from the specified path 
# using `cv2.imread`.
# - **Fill Color**: The fill color is converted from RGB to BGR since OpenCV 
# uses the BGR format.
# - **Flood Fill**: The `cv2.floodFill` function is used to fill the area 
# starting from the specified point. It creates a mask to manage the area 
# that will be filled.
# - **Display**: The resulting image is displayed in a window.

# ### Usage:
# - Replace `'path/to/your/image.jpg'` with the path to your image file.
# - Adjust the `point` variable to the pixel coordinates where you want to 
# start the fill.
# - Change the `fill_color` to your desired RGB color.

# ### Note:
# Make sure that the point you provide is within the bounds of the image. If 
# the point is outside the image, the function will not work correctly.
# """

# """
# Creating a filled region in Revit using an SVG outline involves several 
# steps, including parsing the SVG file, converting its coordinates to 
# Revit's coordinate system, and then creating the filled region. pyRevit can 
# help in automating these steps. Below you will find a step-by-step example 
# of how to achieve this.

# Ensure you have pyRevit installed and set up, and you are familiar with 
# basic Revit API concepts.

# ### Step-by-Step Guide

# 1. **Install SVG Parser Package**:
   # You will be using `svgpathtools` to parse the SVG file and extract the 
# path coordinates. Ensure you have it installed.
   # ```sh
   # pip install svgpathtools
   # ```

# 2. **pyRevit Script**:
   # Here is a complete script to create a filled region from an SVG outline:

# """
# import clr

# clr.AddReference("RevitAPI")
# clr.AddReference("RevitServices")
# clr.AddReference("RevitNodes")
# clr.AddReference("RevitAPIUI")
# clr.AddReference("Revit")
# clr.AddReference("System")

# from Autodesk.Revit.DB import *
# from RevitServices.Persistence import DocumentManager
# from RevitServices.Transactions import TransactionManager
# from svgpathtools import svg2paths
# from System.Collections.Generic import List
# import os

# # Get the current document
# doc = DocumentManager.Instance.CurrentDBDocument

# # Load the SVG file and extract paths
# svg_file_path = r"path_to_your_svg_file.svg"
# paths, attributes = svg2paths(svg_file_path)


# # Function to convert SVG path to Revit CurveArray
# def convert_svg_to_revit_curves(svg_path, scale=1.0):
    # curves = List[Curve]()
    # for segment in svg_path:
        # start = XYZ(segment.start.real * scale, segment.start.imag * scale, 0)
        # end = XYZ(segment.end.real * scale, segment.end.imag * scale, 0)
        # if isinstance(segment, svgpathtools.Line):
            # line = Line.CreateBound(start, end)
            # curves.Add(line)
        # elif isinstance(segment, svgpathtools.CubicBezier):
            # control1 = XYZ(
                # segment.control1.real * scale, segment.control1.imag * scale, 0
            # )
            # control2 = XYZ(
                # segment.control2.real * scale, segment.control2.imag * scale, 0
            # )
            # bezier = HermiteSpline.Create([start, control1, control2, end], False)
            # curves.Add(bezier)
    # return curves


# # Convert the first path to Revit curves
# if paths:
    # revit_curves = convert_svg_to_revit_curves(paths[0])

# # Create a filled region in Revit
# TransactionManager.Instance.EnsureInTransaction(doc)

# filled_region_type = (
    # FilteredElementCollector(doc).OfClass(FilledRegionType).FirstElement()
# )
# view = doc.ActiveView
# new_filled_region = FilledRegion.Create(
    # doc, filled_region_type.Id, view.Id, revit_curves
# )

# TransactionManager.Instance.TransactionTaskDone()

# print("Filled region created from SVG outline.")
# """

# ### Important Points:
# - **Path Parsing**: This script uses the `svgpathtools` library to parse 
# the SVG file and extract path data.
# - **Coordinate Conversion**: The `convert_svg_to_revit_curves` function 
# converts each SVG segment to a Revit curve.
# - **Transaction Management**: Transactions are used to ensure safe and 
# atomic operations in Revit.
# - **Filled Region Type**: The script retrieves a filled region type from 
# the document; you may need to adjust this to match your specific 
# requirements.

# ### How to Run:
# 1. Save this script in the pyRevit `extensions` directory.
# 2. Change the `svg_file_path` to the path of your SVG file.
# 3. Load the script into Revit through pyRevit and run it.

# This basic example assumes the SVG consists of simple line and cubic Bezier 
# segments. More complex SVG features might require additional handling and 
# translation to Revit's API.
# """


# def main():
    # doc = revit.doc
    # app = __revit__.Application
    # fam = doc.FamilyManager
    # text = ""

    # # get shared parameters
    # sharedParams = {}
    # sharedParamFile = app.OpenSharedParameterFile()
    # for sg in sharedParamFile.Groups:
        # sgName = sg.Name
        # for sp in sg.Definitions:
            # if sp.Description:
                # sharedParams[sp.Name] = sp
                # text += "[{}] {}\r\n;{}\r\n".format(sp.Name, sp.GUID, sp.Description)
    # forms.alert(text)


# if EXEC_PARAMS.config_mode:
    # # Settings (shift-click)
    # forms.alert("Boo")
# else:
    # main()

# # This script performs flood fill as before, but after filling the region, it uses the findContours function to find the
# # outlines of the filled region. The outlines are returned as a list of contours.

# # Please note that this function will return multiple contours if the filled region is non-convex or consists of 
# # multiple connected components. You may want to choose one or process all of them as per your requirement.

# import cv2
# import numpy as np

# # Assuming the input is a binary image.
# def flood_fill_and_outline(img, point):
    # h, w = img.shape[:2]
    # mask = np.zeros((h + 2, w + 2), np.uint8)

    # # Perform flood fill
    # cv2.floodFill(img, mask, point, 255, 0, 0, flags=4 | cv2.FLOODFILL_FIXED_RANGE)

    # # Find the contours of the filled region
    # contours, hierarchy = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # return contours

# # Usage:
# img = np.zeros((500, 500, 3), np.uint8)
# point = (200, 200)
# contours = flood_fill_and_outline(img, point)