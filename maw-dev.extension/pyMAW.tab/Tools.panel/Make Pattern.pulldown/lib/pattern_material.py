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
        (a for a in doc_assets if a.FindByName(DB.Visual.Generic.GenericDiffuse)),
        None,
    )

    if generic_asset_template:
        return generic_asset_template

    # 2. Search Application (Library) Assets
    app_assets = doc.Application.GetAssets(DB.Visual.AssetType.Appearance)
    generic_asset_template = next(
        (a for a in app_assets if a.FindByName(DB.Visual.Generic.GenericDiffuse)),
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
    if not bump_map_path or not System.IO.File.Exists(bump_map_path):
        return None, "Bump map file not found at path: {}".format(bump_map_path)

    if not surface_pattern_element:
        return None, "Invalid surface pattern element provided."

    try:
        # --- 1. Get or Create Material ---
        material = _get_material_by_name(doc, material_name)
        is_new_material = False

        # All modifications, including material creation, must be inside.
        with Transaction("Create/Update Material: " + material_name) as rvt_transaction:

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
                    prop_bool.Value = False

                prop_bool = editable_asset.FindByName(DB.Visual.Generic.GenericIsMetal)
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
                    prop_double.Value = 0.50

                prop_double = editable_asset.FindByName(
                    DB.Visual.Generic.GenericReflectivityAt0deg
                )
                if prop_double and prop_double.IsEditable:
                    prop_double.Value = 0.2

                prop_double = editable_asset.FindByName(
                    DB.Visual.Generic.GenericReflectivityAt90deg
                )
                if prop_double and prop_double.IsEditable:
                    prop_double.Value = 0.5

                prop_color = editable_asset.FindByName(
                    DB.Visual.Generic.CommonTintColor
                )
                if prop_color:
                    prop_color.SetValueAsColor(DB.Color(127, 127, 127))

                prop_color = editable_asset.FindByName(DB.Visual.Generic.GenericDiffuse)
                if prop_color:
                    prop_color.SetValueAsColor(material_color)
                    connected_color_asset = prop_color.GetSingleConnectedAsset()
                    if connected_color_asset:
                        # Find the target asset path property
                        color_bitmap_property = connected_color_asset.FindByName(
                            DB.Visual.UnifiedBitmap.UnifiedbitmapBitmap
                        )  # AssetPropertyString
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
                    bump_map_prop.AddConnectedAsset(DB.Visual.UnifiedBitmap.__name__)
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

                    scale_u_prop = texture_asset.FindByName(
                        DB.Visual.UnifiedBitmap.TextureRealWorldScaleX
                    )
                    if scale_u_prop:
                        scale_u_prop.Value = (
                            texture_real_world_width_int
                            * 12  # image scale seems to be in inches?
                        )
                    else:
                        print("Could not find 'UnifiedBitmap.RealWorldScaleU' property")

                    scale_v_prop = texture_asset.FindByName(
                        DB.Visual.UnifiedBitmap.TextureRealWorldScaleY
                    )
                    if scale_v_prop:
                        scale_v_prop.Value = (
                            texture_real_world_height_int
                            * 12  # image scale seems to be in inches?
                        )
                    else:
                        print("Could not find 'UnifiedBitmap.RealWorldScaleV' property")

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
            uidoc.Selection.SetElementIds(System.Array[DB.ElementId]([material.Id]))
            uidoc.ShowElements(material.Id)
        else:
            print("Test Failed: {}".format(message))
            forms.alert(message, title="Test Failed")

    print("Test finished.")
