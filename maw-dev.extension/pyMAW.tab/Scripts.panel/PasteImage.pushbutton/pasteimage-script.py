# -*- coding: UTF-8 -*-
"""
Pastes an image from the system clipboard into the current Revit view.

Prompts the user to select an insertion point after verifying
an image exists on the clipboard. The image is temporarily saved
to disk before being imported.
"""

__title__ = "Paste Image\nfrom Clipboard"
__author__ = "MAW" # Update with your details
__doc__ = "Pastes an image from the system clipboard into the current view "\
          "at a selected point. Saves the image temporarily first."
__context__ = "doc-project" # Ensures a project document is active

# --- Imports ---
# pyRevit essentials
from pyrevit import revit, DB, UI, forms, script

# .NET assemblies for clipboard and image handling
try:
    import clr
    clr.AddReference('System.Windows.Forms')
    clr.AddReference('System.Drawing')
    import System.Windows.Forms as WinForms
    import System.Drawing.Imaging as Imaging
    from System.Collections.Generic import List
except ImportError:
    app.WriteJournalComment("MAW Could not load necessary .NET assemblies", True)
    forms.alert("Could not load necessary .NET assemblies "
                "(System.Windows.Forms, System.Drawing).\n"
                "Script cannot access the clipboard.", exitscript=True)

# Python standard libraries for temporary files and paths
import os

# --- Configuration ---
DEFAULT_IMAGE_FORMAT = Imaging.ImageFormat.Png # Use PNG for saving temp file (supports transparency)
TEMP_FILE_SUFFIX = "png"
TEMP_FILE_NAME = "paste_img"
DEBUG = False

# --- Get Revit objects ---
doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView
app = __revit__.Application

if not view:
    app.WriteJournalComment("MAW No active view found.", True)
    forms.alert("No active view found. Please open a view.", exitscript=True)

# Check if the view can host images (e.g., Drafting Views, Sheets, Legends)
# Add more view types if needed
allowed_view_types = [
    DB.ViewType.DraftingView,
    DB.ViewType.Legend,
    DB.ViewType.Detail,
    DB.ViewType.FloorPlan, # Often allowed but might depend on settings
    DB.ViewType.CeilingPlan, # Often allowed but might depend on settings
    DB.ViewType.Elevation, # Often allowed but might depend on settings
    DB.ViewType.Section, # Often allowed but might depend on settings
    DB.ViewType.DrawingSheet,
]
if view.ViewType not in allowed_view_types:
    view_type = str(view.ViewType)
    view_type = "3D View" if view_type == "ThreeD" else view_type
    app.WriteJournalComment("MAW The current view type ('{}') may not support image imports.".format(view_type), True)
    forms.alert("The current view type ('{}') may not support image imports.\n\n"
                "Try using a Drafting View, Legend, Detail View, or Sheet.".format(view_type),
                exitscript=True)


# --- Clipboard Handling ---
temp_file_path = None

try:
    # Check if clipboard contains an image
    if not WinForms.Clipboard.ContainsImage():
        app.WriteJournalComment("MAW No image found on the clipboard.", True)
        forms.alert("No image found on the clipboard.", exitscript=True)

    # Get image from clipboard
    clipboard_image = WinForms.Clipboard.GetImage()
    if not clipboard_image:
        app.WriteJournalComment("MAW Could not retrieve image data from the clipboard.", True)
        forms.alert("Could not retrieve image data from the clipboard.", exitscript=True)

    # Save image to a temporary file
    try:
        temp_file_path = script.get_document_data_file(TEMP_FILE_NAME, TEMP_FILE_SUFFIX)
        clipboard_image.Save(temp_file_path, DEFAULT_IMAGE_FORMAT)
        app.WriteJournalComment("MAW Image temporarily saved to: {}".format(temp_file_path), True)
        if DEBUG:
            print("MAW Image temporarily saved to: {}".format(temp_file_path))
    except Exception as save_ex:
        app.WriteJournalComment("MAW Failed to save image from clipboard to temporary file:\n{}".format(save_ex), True)
        forms.alert("Failed to save image from clipboard to temporary file:\n{}".format(save_ex), exitscript=True)
    # Optionally clear the clipboard
    # finally:
        # # Explicitly dispose of the GDI+ image object
        # if clipboard_image:
            # clipboard_image.Dispose()

    # Check if temp file was created before proceeding
    if not temp_file_path or not os.path.exists(temp_file_path):
        app.WriteJournalComment("MAW Failed to create or access the temporary image file.", True)
        forms.alert("Failed to create or access the temporary image file.", exitscript=True)

    # --- User Interaction ---
    # Prompt user to pick an insertion point
    try:
        prompt = "Select insertion point for the clipboard image"
        image_location = uidoc.Selection.PickPoint(prompt)
        image_placement = DB.ImagePlacementOptions(image_location, DB.BoxPlacement.BottomLeft)
    except Exception as pick_ex: # Catches user pressing Esc ('Operation canceled by user.')
        if "cancel" in str(pick_ex).lower():
            app.WriteJournalComment("MAW Operation cancelled by user during point selection.", True)
            if DEBUG:
                print("MAW Operation cancelled by user during point selection.")
        else:
            app.WriteJournalComment("MAW An error occurred while picking the point:\n{}".format(pick_ex), True)
            forms.alert("An error occurred while picking the point:\n{}".format(pick_ex))
        # Exitscript requires cleanup of temp file here
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                app.WriteJournalComment("MAW Cleaned up temporary file after cancellation.", True)
                if DEBUG:
                    print("MAW Cleaned up temporary file after cancellation.")
            except Exception as clean_ex:
                app.WriteJournalComment("MAW Warning: Failed to delete temp file '{}' after cancellation: {}".format(temp_file_path, clean_ex), True)
                if DEBUG:
                    print("MAW Warning: Failed to delete temp file '{}' after cancellation: {}".format(temp_file_path, clean_ex))
        script.exit() # Use pyrevit's exit function

    # --- Revit Import ---
    # Import the image into Revit
    link_image = False # False = Embed the image; True = Link the image file
    image_options = DB.ImageTypeOptions(temp_file_path, False, DB.ImageTypeSource.Link if link_image else DB.ImageTypeSource.Import)

    with revit.Transaction("pyRevit: Import Image from Clipboard"):
        image_type = DB.ImageType.Create(doc, image_options)
        image = DB.ImageInstance.Create(doc, view, image_type.Id, image_placement)

        if not image:
            app.WriteJournalComment("MAW Failed to import the image into Revit. The temporary file might be invalid or the view incompatible.", True)
            forms.alert("Failed to import the image into Revit. The temporary file might be invalid or the view incompatible.")
            # Keep temp file for inspection if import fails? Or delete? Let's delete.
        else:
            app.WriteJournalComment("MAW Image imported successfully into view: '{}'".format(view.Name), True)
            if DEBUG:
                print("MAW Image imported successfully into view: '{}'".format(view.Name))
            # Select the inserted image
            uidoc.Selection.SetElementIds(List[DB.ElementId]([image.Id]))


except Exception as main_ex:
    # General error handling
    forms.alert("An unexpected error occurred:\n{}".format(main_ex))

finally:
    # --- Cleanup ---
    # Delete the temporary file regardless of success or failure (after import attempt)
    if temp_file_path and os.path.exists(temp_file_path):
        try:
            os.remove(temp_file_path)
            app.WriteJournalComment("MAW Temporary image file cleaned up.", True)
            if DEBUG:
                print("MAW Temporary image file cleaned up.")
        except Exception as clean_ex:
            # Log warning, but don't stop script execution if already failed
            app.WriteJournalComment("MAW Warning: Failed to delete temporary file '{}': {}".format(temp_file_path, clean_ex), True)
            if DEBUG:
                print("MAW Warning: Failed to delete temporary file '{}': {}".format(temp_file_path, clean_ex))


