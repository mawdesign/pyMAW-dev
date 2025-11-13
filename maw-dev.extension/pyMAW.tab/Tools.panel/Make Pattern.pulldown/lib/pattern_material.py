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

clr.AddReference("System.Core")
clr.AddReference("System")


def _get_material_by_name(doc, name):
    """Finds an existing material by name."""
    collector = DB.FilteredElementCollector(doc).OfClass(DB.Material)
    for mat in collector:
        if mat.Name == name:
            return mat
    return None


def _create_new_appearance_asset(doc, asset_name):
    """
    Creates a new AppearanceAssetElement by duplicating the "Generic" asset.
    Returns the ElementId of the new asset.
    """
    # Try to find the default "Generic" asset to duplicate
    base_asset_elem = None
    collector = DB.FilteredElementCollector(doc).OfClass(DB.AppearanceAssetElement)
    for asset_elem in collector:
        if asset_elem.Name == "Generic":
            base_asset_elem = asset_elem
            break

    if not base_asset_elem:
        # Fallback if "Generic" isn't found (highly unlikely)
        forms.alert("Could not find 'Generic' appearance asset to duplicate.")
        return DB.ElementId.InvalidElementId

    try:
        new_asset_elem = base_asset_elem.Duplicate(asset_name)
        return new_asset_elem.Id
    except Exception as e:
        print("Error duplicating appearance asset: {}".format(e))
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

    Args:
        doc (Document): The active Revit document.
        material_name (str): The name of the material to create/find.
        material_color (DB.Color): The base color for graphics.
        surface_pattern_element (DB.FillPatternElement): The pattern for the
                                                          graphics surface.
        bump_map_path (str): Absolute file path to the bump map texture.
        texture_real_world_width_int (float): Texture width in internal units (feet).
        texture_real_world_height_int (float): Texture height in internal units (feet).

    Returns:
        (DB.Material, str): (The material element, status message)
    """
    if not System.IO.File.Exists(bump_map_path):
        return None, "Bump map file not found at path: {}".format(bump_map_path)

    if not surface_pattern_element:
        return None, "Invalid surface pattern element provided."

    try:
        # --- 1. Get or Create Material ---
        material = _get_material_by_name(doc, material_name)
        is_new_material = False
        if not material:
            material = DB.Material.Create(doc, material_name)
            is_new_material = True

        with Transaction(
            "Create/Update Material: " + material_name
        ) as rvt_transaction:
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
            # We must use an AssetEditScope to modify the asset
            with DB.Visual.AssetEditScope(rendering_asset) as edit_scope:
                # Start editing the asset
                editable_asset = edit_scope.Start()

                # --- Find the Bump Map Property ---
                # This is the "slot" for the bump map
                # Schema name for bump map on a Generic asset is "Generic.BumpMap"
                bump_map_prop = editable_asset.FindByName(DB.Visual.Generic.BumpMap)

                # --- Get or Create the Texture Asset (UnifiedBitmap) ---
                # This is the "texture" that plugs into the slot
                texture_asset = None
                if bump_map_prop.GetConnectedAsset():
                    # Asset already has a texture, let's edit it
                    texture_asset = bump_map_prop.GetConnectedAsset()
                else:
                    # No texture, create a new "UnifiedBitmap" asset
                    # Note: We create this within the same edit scope
                    texture_asset = DB.Visual.Asset("UnifiedBitmap")
                    # Connect the new texture asset to the bump map slot
                    bump_map_prop.Connect(texture_asset)

                # --- Edit the Texture Asset Properties ---
                if texture_asset:
                    # 1. Set the file path
                    # Schema name is "UnifiedBitmap.Source"
                    source_prop = texture_asset.FindByName(
                        DB.Visual.UnifiedBitmap.Source
                    )
                    if source_prop:
                        source_prop.Value = bump_map_path
                    else:
                        print("Could not find 'UnifiedBitmap.Source' property")

                    # 2. Set Texture Mode to "Real World" https://www.revitapidocs.com/2025/de22f405-e0d8-e50a-096f-7e199c64fd00.htm
                    # Schema name is "UnifiedBitmap.WCSMappingType"
                    mapping_prop = texture_asset.FindByName(
                        DB.Visual.UnifiedBitmap.WCSMappingType
                    )
                    if mapping_prop:
                        mapping_prop.Value = DB.Visual.WCSMappingType.RealWorld
                    else:
                        print("Could not find 'UnifiedBitmap.WCSMappingType' property")

                    # 3. Set Real World Scale (U = Width, V = Height)
                    scale_u_prop = texture_asset.FindByName(
                        DB.Visual.UnifiedBitmap.RealWorldScaleU
                    )
                    if scale_u_prop:
                        scale_u_prop.Value = texture_real_world_width_int  # Internal feet
                    else:
                        print("Could not find 'UnifiedBitmap.RealWorldScaleU' property")

                    scale_v_prop = texture_asset.FindByName(
                        DB.Visual.UnifiedBitmap.RealWorldScaleV
                    )
                    if scale_v_prop:
                        scale_v_prop.Value = texture_real_world_height_int  # Internal feet
                    else:
                        print("Could not find 'UnifiedBitmap.RealWorldScaleV' property")
                        
                    # 4. Set Offset to 0
                    offset_u_prop = texture_asset.FindByName(
                        DB.Visual.UnifiedBitmap.RealWorldOffsetU
                    )
                    if offset_u_prop:
                        offset_u_prop.Value = 0.0
                        
                    offset_v_prop = texture_asset.FindByName(
                        DB.Visual.UnifiedBitmap.RealWorldOffsetV
                    )
                    if offset_v_prop:
                        offset_v_prop.Value = 0.0

                # Commit the changes to the asset
                edit_scope.Commit(True)

            status_msg = "Material '{}' created.".format(material_name)
            if not is_new_material:
                status_msg = "Material '{}' updated.".format(material_name)

            return material, status_msg

    except Exception as e:
        print(e)
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
    test_bump_path = forms.pick_file(
        file_ext="png",
        multi_file=False,
        title="Select a PNG file to use as the test bump map",
    )
    if not test_bump_path:
        forms.alert("Test aborted. No bump map selected.", title="Test Cancelled")
    else:
        print("Test Parameters:")
        print("  Material Name: {}".format(TEST_MATERIAL_NAME))
        print("  Pattern Name: {}".format(TEST_PATTERN_NAME))
        print("  Texture Path: {}".format(test_bump_path))
        print("  Texture Size: {}' x {}'".format(TEST_TEXTURE_WIDTH_INT, TEST_TEXTURE_HEIGHT_INT))
        
        # --- 4. Run the Function ---
        material, message = create_or_update_material(
            doc,
            TEST_MATERIAL_NAME,
            TEST_MATERIAL_COLOR,
            test_pattern,
            test_bump_path,
            TEST_TEXTURE_WIDTH_INT,
            TEST_TEXTURE_HEIGHT_INT,
        )
        
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