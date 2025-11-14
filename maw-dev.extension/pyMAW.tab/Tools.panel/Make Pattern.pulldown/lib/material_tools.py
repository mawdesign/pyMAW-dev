# -*- coding: utf-8 -*-
# WORKING_PATH = r"C:\Users\warwickm\Downloads"
# region Imports
import os
import json
import clr
import traceback
import io
from collections import OrderedDict

# Add Revit API references
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

# Import Revit namespaces
from Autodesk.Revit import DB
from Autodesk.Revit import UI as RUI
from Autodesk.Revit.DB import Visual as RDV
from Autodesk.Revit.ApplicationServices import Application
# endregion

# --- USER CONFIGURATION ---
# PLEASE SET THIS PATH to your desired working folder for logs and bitmaps
WORKING_PATH = r"C:\temp\pyRevit_Material_Tools"
# --------------------------


# #############################################################################
# Main Functions (Translated from VB)
# #############################################################################

def get_revit_appearance_assets(doc, app):
    """
    Lists all Revit Library Material Appearance Assets.
    Can't get Physical (Structural) or Thermal Property Sets this way
    due to current API limitations.
    """
    print("Starting: Get Revit Appearance Assets...")

    # Ensure working path exists
    if not os.path.exists(WORKING_PATH):
        os.makedirs(WORKING_PATH)

    # start a log file:
    log_file_path = os.path.join(WORKING_PATH, "Revit Material Assets.txt")
    json_file_path = os.path.join(WORKING_PATH, "Revit Material Assets.json")

    # This dictionary will hold all our data instead of an XML
    json_output = OrderedDict()

    # Why are these material Assets accessed through the Application?
    # Because they're not the document assets, they're from a built-in Autodesk Asset Library
    # and where does this library exist anyway? Library name is the same for every appearance asset returned
    # regardless of them coming from the app level or the document level and it doesn't match any file name in the system
    app_assets = app.GetAssets(RDV.AssetType.Appearance)

    log_lines = [
        "All Revit Material Appearance Assets\n",
        "Number of Library Assets:  {}\n".format(app_assets.Count)
    ]

    json_output['Source'] = "Revit Appearance Asset Library"
    json_output['Count'] = app_assets.Count
    json_output['Schemas'] = []

    # create a dictionary that contains keys from the base schemas
    # and values containing dictionaries whose keys are the AssetName
    # and whose values are the assets themselves
    dict_asset_type = {}

    for this_asset in app_assets:
        schema_type_prop = this_asset.FindByName(RDV.SchemaCommon.BaseSchema)
        if isinstance(schema_type_prop, RDV.AssetPropertyString):
            schema_name = schema_type_prop.Value
        else:
            schema_name = "Unknown"

        # if this schema type doesn't exist in the dictionary then create it and add it
        if schema_name not in dict_asset_type:
            dict_asset_type[schema_name] = {}

        dict_asset_type[schema_name][this_asset.Name] = this_asset

    # Sort schemas by name for consistent output
    sorted_schema_names = sorted(dict_asset_type.keys())

    for schema_name in sorted_schema_names:
        schema_assets = dict_asset_type[schema_name]
        sorted_asset_names = sorted(schema_assets.keys())
        
        log_lines.append("\tAsset Schema Type: {} \t| Count: {}".format(schema_name, len(schema_assets)))
        
        schema_node = OrderedDict()
        schema_node['Type'] = schema_name
        schema_node['Count'] = len(schema_assets)
        schema_node['Assets'] = []

        for asset_name in sorted_asset_names:
            this_asset = schema_assets[asset_name]
            log_lines.append("\n\t\tAsset Name: {}  |  Size: {}".format(asset_name, this_asset.Size))

            asset_node = OrderedDict()
            asset_node['Name'] = asset_name
            asset_node['Size'] = this_asset.Size
            
            # use asset.size to ensure that we have something to process
            if this_asset.Size > 0:
                asset_node['Properties'] = _get_asset_properties(this_asset, log_lines, 2)
            
            schema_node['Assets'].append(asset_node)
            
        json_output['Schemas'].append(schema_node)

    # question: why can't we get Physical (Structural) and Thermal
    # library assets using similar methods?

    # finalize the log files
    try:
        with io.open(log_file_path, 'w', encoding='utf-8') as f:
            f.writelines(log_lines)
        print("Text log written to: {}".format(log_file_path))

        with io.open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(json_output, f, indent=4)
        print("JSON log written to: {}".format(json_file_path))

    except Exception as e:
        print("Error writing log files: {}".format(e))
        
    print("Finished: Get Revit Appearance Assets.")


def get_doc_material_assets(doc, include_parameters=True):
    """
    Lists all document material assets: Appearance, Physical (Structural) PSE, and Thermal PSE
    still can't firmly determine difference between Structural and Thermal Property Set Elements
    without getting a material first, then pulling them specifically from that
    """
    print("Starting: Get Document Material Assets...")

    # Ensure working path exists
    if not os.path.exists(WORKING_PATH):
        os.makedirs(WORKING_PATH)

    # start a log file:
    doc_name = doc.Title if doc.Title else "Doc"
    log_file_path = os.path.join(WORKING_PATH, "{} Material Assets.txt".format(doc_name))
    json_file_path = os.path.join(WORKING_PATH, "{} Material Assets.json".format(doc_name))

    log_lines = ["\nAll Document Material Assets\n"]

    json_output = OrderedDict()
    json_output['Source'] = doc_name
    json_output['Categories'] = []

    # --- Appearance Assets ---
    # must inherit from Element for filtered element collector so we need the document element level,
    # then use that to get the underlying Asset
    asset_collector = DB.FilteredElementCollector(doc).OfClass(DB.AppearanceAssetElement)
    all_appearance_assets = asset_collector.ToElements()

    log_lines.append("\n**Appearance Assets:  {}\n".format(all_appearance_assets.Count))

    appearance_category_node = OrderedDict()
    appearance_category_node['Name'] = "Appearance Assets"
    appearance_category_node['Count'] = all_appearance_assets.Count
    appearance_category_node['Schemas'] = []

    dict_asset_type = {}

    for this_asset_elem in all_appearance_assets:
        this_asset = this_asset_elem.GetRenderingAsset()
        schema_str = "Unknown"
        schema_type = this_asset.FindByName(RDV.SchemaCommon.BaseSchema)
        if isinstance(schema_type, RDV.AssetPropertyString):
            schema_str = schema_type.Value

        # if this schema type doesn't exist in the dictionary then create it and add it
        if schema_str not in dict_asset_type:
            dict_asset_type[schema_str] = {}

        if this_asset_elem.Name not in dict_asset_type[schema_str]:
            dict_asset_type[schema_str][this_asset_elem.Name] = this_asset_elem

    sorted_schema_names = sorted(dict_asset_type.keys())

    for schema_name in sorted_schema_names:
        schema_assets = dict_asset_type[schema_name]
        sorted_asset_names = sorted(schema_assets.keys())
        
        log_lines.append("\tAsset Schema Type: {} \t| Count: {}".format(schema_name, len(schema_assets)))
        
        schema_node = OrderedDict()
        schema_node['Type'] = schema_name
        schema_node['Count'] = len(schema_assets)
        schema_node['Elements'] = []

        for asset_name in sorted_asset_names:
            this_asset_elem = schema_assets[asset_name]
            log_lines.append("\t\tAsset Name: {}  | UniqueId: {}".format(asset_name, this_asset_elem.UniqueId))

            elem_json_node = OrderedDict()
            elem_json_node['Name'] = asset_name
            elem_json_node['UniqueId'] = this_asset_elem.UniqueId

            if this_asset_elem.Parameters.Size > 0:
                log_lines.append("\t\t\t -- Pset Parameters:  {}".format(this_asset_elem.Parameters.Size))
                if include_parameters:
                    param_info = _log_parameters(this_asset_elem.Parameters, doc, log_lines, 4)
                    elem_json_node['Parameters'] = param_info
                    log_lines.append("\t\t\t -- End Parameters\n")

            this_asset = this_asset_elem.GetRenderingAsset()
            
            asset_json_node = OrderedDict()
            asset_json_node['Name'] = this_asset.Name
            asset_json_node['Size'] = this_asset.Size

            # use asset.size to ensure that we have something to process
            if this_asset.Size > 0:
                asset_json_node['Properties'] = _get_asset_properties(this_asset, log_lines, 3)
            
            elem_json_node['Asset'] = asset_json_node
            schema_node['Elements'].append(elem_json_node)
            log_lines.append("\n")

        log_lines.append("\n")
        appearance_category_node['Schemas'].append(schema_node)
    
    json_output['Categories'].append(appearance_category_node)


    # --- Property Set Assets (Physical/Thermal) ---
    pset_collector = DB.FilteredElementCollector(doc).OfClass(DB.PropertySetElement)
    all_property_assets = pset_collector.ToElements()

    log_lines.append("\n**Property Set Assets:  {}\n".format(all_property_assets.Count))

    property_category_node = OrderedDict()
    property_category_node['Name'] = "Property Set Assets"
    property_category_node['Count'] = all_property_assets.Count
    property_category_node['Schemas'] = []

    # try to categorize the returns for selection by type (stru or Thermal) when duplicating an asset
    # although this would double the processing time
    
    dict_pset_type = {
        "Structural": {},
        "Thermal": {},
        "Unknown": {}
    }

    for this_asset_elem in all_property_assets:
        # place tests here and place Assets in appropriate list
        therm_asset = None
        struc_asset = None
        try_other = False

        test_param = this_asset_elem.get_Parameter(DB.BuiltInParameter.PROPERTY_SET_KEYWORDS)
        if test_param:
            # we have to test it
            param_val = test_param.AsString()
            if param_val:
                param_val_lower = param_val.lower()
                if 'structural' in param_val_lower:
                    struc_asset = this_asset_elem.GetStructuralAsset()
                elif 'thermal' in param_val_lower:
                    therm_asset = this_asset_elem.GetThermalAsset()
                else:
                    # it's an unknown PSE class that we probably shouldn't collect for reuse
                    # (but we may need to know it's name to avoid any naming conflicts against either type)
                    try_other = True
            else:
                try_other = True
        else:
            # it may be an older material and we think it's structural because
            # older structural Psets didn't seem to have it, but we don't know for sure
            # either way we shouldn't be using it to duplicate, although we may want replace it???
            # (but we may need to know it's name to avoid any naming conflicts)
            try_other = True

        if try_other:
            # use a Try... Catch... block to see if it can be
            # turned into a thermal asset that way, and if not it will most likely cast to structural
            try:
                therm_asset = this_asset_elem.GetThermalAsset()
            except Exception:
                try:
                    struc_asset = this_asset_elem.GetStructuralAsset()
                except Exception:
                    # do nothing
                    pass

        if therm_asset:
            if therm_asset.Name not in dict_pset_type["Thermal"]:
                dict_pset_type["Thermal"][therm_asset.Name] = this_asset_elem
        elif struc_asset:
            if struc_asset.Name not in dict_pset_type["Structural"]:
                dict_pset_type["Structural"][struc_asset.Name] = this_asset_elem
        else:
            # should not need this since all Pset elements seen to be able to convert to structural
            if this_asset_elem.Name not in dict_pset_type["Unknown"]:
                dict_pset_type["Unknown"][this_asset_elem.Name] = this_asset_elem
                
    for schema_name, schema_assets in dict_pset_type.items():
        if schema_assets:
            sorted_asset_names = sorted(schema_assets.keys())
            log_lines.append("\tAsset Type: {} \t| Count: {}".format(schema_name, len(schema_assets)))
            
            schema_node = OrderedDict()
            schema_node['Type'] = schema_name
            schema_node['Count'] = len(schema_assets)
            schema_node['Elements'] = []

            for asset_name in sorted_asset_names:
                this_asset_elem = schema_assets[asset_name]
                log_lines.append("\t\tAsset Name: {}".format(asset_name))
                
                elem_json_node = OrderedDict()
                elem_json_node['Name'] = asset_name
                elem_json_node['UniqueId'] = this_asset_elem.UniqueId

                if this_asset_elem.Parameters.Size > 0:
                    log_lines.append("\t\t\t -- Pset Parameters:  {}".format(this_asset_elem.Parameters.Size))
                    if include_parameters:
                        param_info = _log_parameters(this_asset_elem.Parameters, doc, log_lines, 4)
                        elem_json_node['Parameters'] = param_info
                        log_lines.append("\t\t\t -- End Parameters\n")

                if schema_name == "Structural":
                    struc_asset = this_asset_elem.GetStructuralAsset()
                    elem_json_node['Asset'] = _get_structural_asset_info(struc_asset, log_lines, 3)
                elif schema_name == "Thermal":
                    therm_asset = this_asset_elem.GetThermalAsset()
                    elem_json_node['Asset'] = _get_thermal_asset_info(therm_asset, log_lines, 3)
                
                schema_node['Elements'].append(elem_json_node)
            
            log_lines.append("\n")
            property_category_node['Schemas'].append(schema_node)

    json_output['Categories'].append(property_category_node)

    # finalize the log files
    try:
        with io.open(log_file_path, 'w', encoding='utf-8') as f:
            f.writelines(log_lines)
        print("Text log written to: {}".format(log_file_path))

        with io.open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(json_output, f, indent=4)
        print("JSON log written to: {}".format(json_file_path))
            
    except Exception as e:
        print("Error writing log files: {}".format(e))
        
    print("Finished: Get Document Material Assets.")


def get_doc_materials(doc, include_parameters=True):
    """
    Lists all document materials and their connected assets.
    """
    print("Starting: Get Document Materials...")

    # Ensure working path exists
    if not os.path.exists(WORKING_PATH):
        os.makedirs(WORKING_PATH)
        
    # start a log file:
    doc_name = doc.Title if doc.Title else "Doc"
    log_file_path = os.path.join(WORKING_PATH, "{} Materials.txt".format(doc_name))
    json_file_path = os.path.join(WORKING_PATH, "{} Materials.xml".format(doc_name))
    
    log_lines = []

    mat_collector = DB.FilteredElementCollector(doc).OfClass(DB.Material)
    all_mats = mat_collector.ToElements()

    log_lines.append("\nAll Document Materials:  {}\n\n".format(all_mats.Count))

    json_output = OrderedDict()
    json_output['Source'] = doc_name
    json_output['Count'] = all_mats.Count
    json_output['Classes'] = []

    dict_mat_type = {}
    for this_mat in all_mats:
        # if this schema type doesn't exist in the dictionary then create it and add it
        class_name = this_mat.MaterialClass if this_mat.MaterialClass else "Unknown"
        
        if class_name not in dict_mat_type:
            dict_mat_type[class_name] = {}
        
        if this_mat.Name not in dict_mat_type[class_name]:
            dict_mat_type[class_name][this_mat.Name] = this_mat

    sorted_class_names = sorted(dict_mat_type.keys())

    for class_name in sorted_class_names:
        class_mats = dict_mat_type[class_name]
        sorted_mat_names = sorted(class_mats.keys())
        
        log_lines.append("\tMaterial Class: {} \t| Count: {}\n".format(class_name, len(class_mats)))
        
        class_node = OrderedDict()
        class_node['Type'] = class_name
        class_node['Count'] = len(class_mats)
        class_node['Materials'] = []

        for mat_name in sorted_mat_names:
            log_lines.append("\t\tMaterial Name:  {}\n".format(mat_name))
            
            this_material = class_mats[mat_name]
            
            # get the info here
            mat_info = _get_material_info(doc, this_material, log_lines, 3, include_parameters)
            class_node['Materials'].append(mat_info)

            log_lines.append("\n")
        log_lines.append("\n")
        json_output['Classes'].append(class_node)

    # finalize the log files
    try:
        with io.open(log_file_path, 'w', encoding='utf-8') as f:
            f.writelines(log_lines)
        print("Text log written to: {}".format(log_file_path))

        with io.open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(json_output, f, indent=4)
        print("JSON log written to: {}".format(json_file_path))

    except Exception as e:
        print("Error writing log files: {}".format(e))
        
    print("Finished: Get Document Materials.")


def create_simple_material(doc, create_report=True):
    """
    Creates a material using what we've learned.
    """
    print("Starting: Create Simple Material...")
    
    # Ensure working path exists for bitmaps and potential report
    if not os.path.exists(WORKING_PATH):
        os.makedirs(WORKING_PATH)
        print("Warning: Created working path at: {}".format(WORKING_PATH))
        print("Please add bitmap files ('Concrete.Cast-In-Place.Exposed Aggregate.Medium.jpg' and '...bump.jpg') to this folder.")
        
    # collect our resources to test for naming conflicts and for reuse
    # region Collect resources

    all_mats = DB.FilteredElementCollector(doc).OfClass(DB.Material).ToElements()
    dict_mat = {m.Name: m for m in all_mats}

    all_appearance_assets = DB.FilteredElementCollector(doc).OfClass(DB.AppearanceAssetElement).ToElements()
    dict_asset_elem = {a.Name: a for a in all_appearance_assets}
    
    list_asset = []
    for this_asset_elem in all_appearance_assets:
        try:
            list_asset.append(this_asset_elem.GetRenderingAsset())
        except Exception:
            # do nothing, just keep going and add the next, we don't need everything
            pass

    all_property_assets = DB.FilteredElementCollector(doc).OfClass(DB.PropertySetElement).ToElements()

    dict_therm = {}
    dict_struct = {}
    dict_unknown = {}

    for this_asset_elem in all_property_assets:
        # place tests here and place Assets in appropriate list
        therm_asset = None
        struc_asset = None
        try_other = False

        test_param = this_asset_elem.get_Parameter(DB.BuiltInParameter.PROPERTY_SET_KEYWORDS)
        if test_param:
            # we have to test it
            param_val = test_param.AsString()
            if param_val:
                param_val_lower = param_val.lower()
                if 'structural' in param_val_lower:
                    struc_asset = this_asset_elem.GetStructuralAsset()
                elif 'thermal' in param_val_lower:
                    therm_asset = this_asset_elem.GetThermalAsset()
                else:
                    # it has the parameter but doesn't have one of the required keywords
                    # so we'll use the try... catch method testing for ability to return the thermal PSE
                    try_other = True
            else:
                try_other = True
        else:
            # it may be an older material and we think it will be structural because older Physical only Psets
            # didn't seem to have this parameter and all seem to default to struct, although we don't know for sure
            # so we'll use the try... catch method testing for ability to return the thermal PSE
            try_other = True
            
        if try_other:
            # use a Try... Catch... block to see if it can be
            # turned into a thermal PSE asset that way, and if not it will most likely cast to structural
            try:
                therm_asset = this_asset_elem.GetThermalAsset()
            except Exception:
                try:
                    struc_asset = this_asset_elem.GetStructuralAsset()
                except Exception:
                    pass # do nothing since the next block will wrap it

        if therm_asset:
            if therm_asset.Name not in dict_therm:
                dict_therm[therm_asset.Name] = this_asset_elem
        elif struc_asset:
            if struc_asset.Name not in dict_struct:
                dict_struct[struc_asset.Name] = this_asset_elem
        else:
            # should not need this since all Pset elements seen to be able to convert to structural
            # but we keep it in just in case so we can double check for naming conflicts when creating our Psets
            if this_asset_elem.Name not in dict_unknown:
                dict_unknown[this_asset_elem.Name] = this_asset_elem

    all_pats = DB.FilteredElementCollector(doc).OfClass(DB.FillPatternElement).ToElements()
    dict_pat = {p.GetFillPattern().Name: p for p in all_pats}

    # endregion

    # region Schema Mapping for lookup
    
    # Dim thisAsset As RDV.Asset = thisAssetElem.GetRenderingAsset
    # Dim schemaName As String
    # Dim schemaType As RDV.AssetProperty = thisAsset.FindByName(RDV.SchemaCommon.BaseSchema)
    # Dim thisProp As RDV.AssetPropertyString = TryCast(schemaType, RDV.AssetPropertyString)
    # If thisProp IsNot Nothing Then
    # 	schemaName = thisProp.Value
    # End If
    
    # Try
    # 	schemaName = TryCast(thisAsset.FindByName(RDV.SchemaCommon.BaseSchema), RDV.AssetPropertyString).Value
    # 	'would this do the same?
    # 	'schemaName = thisAsset.FindByName(RDV.SchemaCommon.BaseSchema).Value
    # Catch ex As Exception
    # 	schemaName = "Unknown"
    # End Try
    
    # 	'find values using:
    # Select Case schemaName
    # 	Case "CeramicSchema"
    # 			'RDV.Ceramic
    # 	Case "ConcreteSchema"
    # 			'RDV.Concrete
    # 	Case "DecalAppearanceSchema"
    # 			'??
    # 	Case "DecalSchema"
    # 			'??
    # 	Case "GenericSchema"
    # 			'RDV.Generic
    # 	Case "GlazingSchema"
    # 			'RDV.Glazing
    # 	Case "HardwoodSchema"
    # 			'RDV.Hardwood
    # 	Case "MasonryCMUSchema"
    # 			'RDV.MasonryCMU
    # 	Case "MetallicPaintSchema"
    # 			'RDV.MetallicPaint
    # 	Case "MetalSchema"
    # 			'RDV.Metal
    # 	Case "MirrorSchema"
    # 			'RDV.Mirror
    # 	Case "PlasticVinylSchema"
    # 			'RDV.PlasticVinyl
    # 	Case "PrismGlazingSchema"
    # 			'RDV.AdvancedGlazing
    # 	Case "PrismLayeredSchema"
    # 			'RDV.AdvancedLayered
    # 	Case "PrismMetalSchema"
    # 			'RDV.AdvancedMetal
    # 	Case "PrismOpaqueSchema"
    # 			'RDV.AdvancedOpaque
    # 	Case "PrismTransparentSchema"
    # 			'RDV.AdvancedTransparent
    # 	Case "PrismWoodSchema"
    # 			'RDV.AdvancedWood
    # 	Case "SolidGlassSchema"
    # 			'RDV.SolidGlass
    # 	Case "StoneSchema"
    # 			'RDV.Stone
    # 	Case "TilingAppearanceSchema"
    # 			'??
    # 	Case "TilingPatternSchema"
    # 			'??
    # 	Case "WallPaintSchema"
    # 			'RDV.WallPaint
    # 	Case "WaterSchema"
    # 		'RDV.Water
    # 	Case Else 'this never happens just including for all API schema values
    # 		'RDV.SchemaCommon
    # End Select
    
    # Mapping Types:
    # Checker
    # Gradient
    # Marble
    # Noise
    # Speckle
    # Tile
    # Wave
    # Wood
    # BumpMap
    # UnifiedBitmap

    # endregion

    # now we're ready to create our new material in the document, so we start a transaction
    this_material = None
    this_trans = None # Define trans here to check in except block
    
    try:
        with DB.Transaction(doc, "Create new material") as this_trans:
            this_trans.Start()

            # Create the material
            # error checking for existence of name
            name_str = _generate_name("_My Material", dict_mat.keys())
            print("Creating Material: {}".format(name_str))
            material_id = DB.Material.Create(doc, name_str)
            this_material = doc.GetElement(material_id)

            # properties and parameters often overlap, some can be used to set the other,
            # some will be overridden by the Appearance Asset Properties.
            # some will fail if you don't set them in the correct scope.
            # should always consider checking for read only and/or can be set,
            # but we're skipping some of that for now

            # region Set some properties for the Material
            # set a parameter on the material
            description_parameter = this_material.get_Parameter(DB.BuiltInParameter.ALL_MODEL_DESCRIPTION)
            description_parameter.Set("My First Material")
            
            # set a couple properties on the material
            this_material.MaterialClass = "My Classification"
            this_material.UseRenderAppearanceForShading = False
            # neither of the following apply if the above line is True
            this_material.Color = DB.Color(127, 127, 127)
            this_material.Transparency = 0

            # set some hatch patterns 
            # create a Model hatch pattern for the surface foreground
            # error checking for existence of name
            name_str = _generate_name("_My Model Pattern ", dict_pat.keys())
            model_pat_def = DB.FillPattern(name_str, DB.FillPatternTarget.Model,
                                         DB.FillPatternHostOrientation.ToHost, 0, 2.0, 2.0)
            model_pat = DB.FillPatternElement.Create(doc, model_pat_def)
            this_material.SurfaceForegroundPatternId = model_pat.Id
            
            # create a drafting hatch pattern for the cut foreground
            # error checking for existence of name
            name_str = _generate_name("_My Drafting Pattern", dict_pat.keys())
            draft_pat_def = DB.FillPattern(name_str, DB.FillPatternTarget.Drafting,
                                         DB.FillPatternHostOrientation.ToHost, 0, 1.0 / 12, 1.0 / 12)
            draft_pat = DB.FillPatternElement.Create(doc, draft_pat_def)
            this_material.CutForegroundPatternId = draft_pat.Id
            
            # endregion

            # region Create an Appearance Asset
            generic_asset = None

            # we should be able to search for any of the schema types by matching SchemaCommon.BaseSchema
            # Property to a specific schema type (this would require some casting). but we can't, see next attempt comment
            # genericAsset = listAsset.FirstOrDefault(Function(eachAsset) eachAsset.FindByName(RDV.SchemaCommon.BaseSchema) = GetType(RDV.Generic).Name)
            
            # or from the asset itself as the asset.name = the schema
            # we should be able to use this but there is no one-to-one mapping between the Property Values and the API Classes
            # genericAsset = listAsset.FirstOrDefault(Function(eachAsset) eachAsset.Name() = GetType(RDV.Generic).Name)
            
            # this one is for the Generic type by checking for a Generic Schema specific property,
            # but this would be tedious across multiple schemas
            
            # try existing doc assets first for one to duplicate since we can't just create one from scratch
            
            generic_asset = next((a for a in list_asset if a.FindByName(RDV.Generic.GenericDiffuse)), None)
            # generic_asset = next((a for a in list_asset if a.FindByName("generic_diffuse")), None) # Language-specific

            # if no suitable doc asset found then we'll get a Revit Library Asset
            if generic_asset is None:
                print("No suitable 'Generic' asset in document, searching Application library...")
                asset_list = doc.Application.GetAssets(RDV.AssetType.Appearance)
                generic_asset = next((a for a in asset_list if a.FindByName(RDV.Generic.GenericDiffuse)), None)

            if generic_asset is None:
                print("Error: Could not find any 'Generic' appearance asset in doc or library.")
                this_trans.RollBack()
                return

            print("Using asset '{}' as template.".format(generic_asset.Name))

            # create a new appearance Asset from the collected Asset
            # error checking for existence of name
            name_str = _generate_name("_My Appearance Asset", dict_asset_elem.keys())
            this_asset = DB.AppearanceAssetElement.Create(doc, name_str, generic_asset)

            # assign the new asset to the material
            this_material.AppearanceAssetId = this_asset.Id

            # enable editing of Appearance Assets within the document
            with RDV.AppearanceAssetEditScope(doc) as edit_scope:
                
                # add the newly created and assigned Appearance Asset
                # to the editing session and set it to a variable
                editable_asset = edit_scope.Start(this_asset.Id)

                # Now let's set some Properties for the Asset:
                # region Set some Properties on the Asset
                
                # ** create some reusable variables (not all property types are included in this example)
                str_property = None
                boolean_property = None
                double_property = None
                color_property = None
                
                # IsEditable and IsValidValue tests should be included as a rule, although we skip some here

                # ** set a couple common Schema Properties
                # language neutral call:
                str_property = editable_asset.FindByName(RDV.SchemaCommon.Description) # AssetPropertyString
                if str_property: str_property.Value = "My First Generic Appearance Asset"
                
                str_property = editable_asset.FindByName(RDV.SchemaCommon.Keyword) # AssetPropertyString
                if str_property: str_property.Value = "Generic,Custom,Concrete"
                
                str_property = editable_asset.FindByName(RDV.SchemaCommon.Category) # AssetPropertyString
                # IsReadOnly failed to catch this call
                # IsEditable caught it and correctly skipped it
                # if str_property and str_property.IsEditable:
                #    str_property.Value = ":Generic:Custom:Concrete"
                
                # ** set a few specific Generic Schema Properties (since we have no idea what we started with)
                boolean_property = editable_asset.FindByName(RDV.Generic.CommonTintToggle) # AssetPropertyBoolean
                if boolean_property: boolean_property.Value = True
                
                boolean_property = editable_asset.FindByName(RDV.Generic.GenericIsMetal) # AssetPropertyBoolean
                if boolean_property: boolean_property.Value = False

                double_property = editable_asset.FindByName(RDV.Generic.GenericDiffuseImageFade) # AssetPropertyDouble
                if double_property and double_property.IsEditable and double_property.IsValidValue(0.5):
                    double_property.Value = 0.5
                    
                double_property = editable_asset.FindByName(RDV.Generic.GenericTransparency) # AssetPropertyDouble
                if double_property and double_property.IsEditable and double_property.IsValidValue(0):
                    double_property.Value = 0
                    
                double_property = editable_asset.FindByName(RDV.Generic.GenericGlossiness) # AssetPropertyDouble
                if double_property and double_property.IsEditable and double_property.IsValidValue(0.1):
                    double_property.Value = 0.1

                double_property = editable_asset.FindByName(RDV.Generic.GenericReflectivityAt0deg) # AssetPropertyDouble
                if double_property and double_property.IsEditable and double_property.IsValidValue(0.1):
                    double_property.Value = 0.1
                    
                double_property = editable_asset.FindByName(RDV.Generic.GenericReflectivityAt90deg) # AssetPropertyDouble
                if double_property and double_property.IsEditable and double_property.IsValidValue(0):
                    double_property.Value = 0

                # let's try a more complex method for the more complicated Properties
                color_property = editable_asset.FindByName(RDV.Generic.CommonTintColor) # AssetPropertyDoubleArray4d
                # set the value as a color:
                if color_property: color_property.SetValueAsColor(DB.Color(127, 127, 127))
                
                color_property = editable_asset.FindByName(RDV.Generic.GenericDiffuse) # AssetPropertyDoubleArray4d
                # another method is set the value as a list of doubles
                if color_property: color_property.SetValueAsDoubles([0.5, 0.5, 0.5, 1.0])
                # endregion

                # let's attach some images
                # region Set some bitmaps to a couple of the Properties
                
                # ** add a generic Diffuse image to the Appearance Asset by
                # getting the correct asset property from the asset we just created
                diffuse_map_property = editable_asset.FindByName(RDV.Generic.GenericDiffuse) # AssetProperty
                
                if diffuse_map_property:
                    # then get or create the required connected Bitmap asset,
                    # although this might be a bad route if there is more than one connected asset (checker?)
                    connected_diff_asset = diffuse_map_property.GetSingleConnectedAsset()
                    # Add a new connected asset if it doesn't already have one
                    if connected_diff_asset is None:
                        # diffuseMapProperty.AddConnectedAsset("UnifiedBitmap")
                        diffuse_map_property.AddConnectedAsset(RDV.UnifiedBitmap.__name__)
                        connected_diff_asset = diffuse_map_property.GetSingleConnectedAsset()
                    
                    # test for success before trying to set a path
                    if connected_diff_asset:
                        # Find the target asset path property
                        diffuse_bitmap_property = connected_diff_asset.FindByName(RDV.UnifiedBitmap.UnifiedbitmapBitmap) # AssetPropertyString
                        # build a path to an image
                        image_path = os.path.join(WORKING_PATH, "Standing Seam-2@8_normal-24in.png")
                        if not os.path.exists(image_path):
                            print("Warning: Diffuse image not found at: {}".format(image_path))
                        elif diffuse_bitmap_property and diffuse_bitmap_property.IsValidValue(image_path):
                            diffuse_bitmap_property.Value = image_path
                        else:
                            print("Warning: Could not set diffuse image path.")
                
                # ** add a generic BumpMap Image  to the Appearance Asset
                bump_map_property = editable_asset.FindByName(RDV.Generic.GenericBumpMap) # AssetProperty
                
                if bump_map_property:
                    connected_bump_asset = bump_map_property.GetSingleConnectedAsset()
                    # Add a new connected asset if it doesn't already have one
                    if connected_bump_asset is None:
                        # bumpMapProperty.AddConnectedAsset("UnifiedBitmap")
                        bump_map_property.AddConnectedAsset(RDV.UnifiedBitmap.__name__)
                        connected_bump_asset = bump_map_property.GetSingleConnectedAsset()

                    if connected_bump_asset:
                        # Find the target asset path property
                        bumpmap_bitmap_property = connected_bump_asset.FindByName(RDV.UnifiedBitmap.UnifiedbitmapBitmap) # AssetPropertyString
                        # build a path to an image
                        image_path = os.path.join(WORKING_PATH, "Standing Seam-2@8_bump-24in.png")
                        if not os.path.exists(image_path):
                            print("Warning: Bump image not found at: {}".format(image_path))
                        elif bumpmap_bitmap_property and bumpmap_bitmap_property.IsValidValue(image_path):
                            bumpmap_bitmap_property.Value = image_path
                        else:
                            print("Warning: Could not set bump image path.")
                
                # endregion
                
                edit_scope.Commit(False)
            # endregion

            # region Add some Physical Property Sets

            # Create a new Structural property set that can be used by this material
            # error checking for existence of name
            name_str = _generate_name("_My Structural Asset", dict_struct.keys())
            # doublecheck name against unknown dictionary
            while name_str in dict_unknown:
                name_str += "_1"
            print("Creating Structural Asset: {}".format(name_str))
            
            # create a Concrete structural Asset
            struc_asset = DB.StructuralAsset(name_str, DB.StructuralAssetClass.Concrete)
            # Set a couple of generic values
            struc_asset.Behavior = DB.StructuralBehavior.Isotropic
            struc_asset.Density = 232.0
            # create a property set element from the structural asset.
            struc_pse = DB.PropertySetElement.Create(doc, struc_asset)
            # Assign the property set element to the material.
            this_material.SetMaterialAspectByPropertySet(DB.MaterialAspect.Structural, struc_pse.Id)
            # set a parameter value on the PSE
            struc_pse_param = struc_pse.get_Parameter(DB.BuiltInParameter.PROPERTY_SET_DESCRIPTION)
            if struc_pse_param: struc_pse_param.Set("My First Structural Asset")

            # Create a new Thermal property set that can be used by this material
            # error checking for existence of name
            name_str = _generate_name("_My Thermal Asset", dict_therm.keys())
            # doublecheck name against unknown dictionary
            while name_str in dict_unknown:
                name_str += "_1"
            print("Creating Thermal Asset: {}".format(name_str))
            
            # create a Solid thermal Asset
            therm_asset = DB.ThermalAsset(name_str, DB.ThermalMaterialType.Solid)
            # set a couple of gereric values
            therm_asset.Behavior = DB.StructuralBehavior.Isotropic # Yes, StructuralBehavior for ThermalAsset
            therm_asset.Density = 232.0
            # create a property set element from the thermal asset.
            therm_pse = DB.PropertySetElement.Create(doc, therm_asset)
            # Assign the property set to the material.
            this_material.SetMaterialAspectByPropertySet(DB.MaterialAspect.Thermal, therm_pse.Id)
            # set a parameter value on the PSE
            therm_pse_param = therm_pse.get_Parameter(DB.BuiltInParameter.PROPERTY_SET_DESCRIPTION)
            if therm_pse_param: therm_pse_param.Set("My First Thermal Asset")
            
            # endregion

            this_trans.Commit()
            print("Successfully created material: {}".format(this_material.Name))

    except Exception as e:
        print("Error during material creation transaction: {}".format(e))
        print(traceback.format_exc()) # Print detailed traceback
        if this_trans and this_trans.HasStarted() and this_trans.GetStatus() == DB.TransactionStatus.Started:
            this_trans.RollBack()
            print("Transaction rolled back.")
        return

    # region Log the resulting Material
    if create_report and this_material:
        print("Generating report for new material...")
        # start a log file:
        doc_name = this_material.Name if this_material.Name else "Material"
        log_file_path = os.path.join(WORKING_PATH, "{} Material Report.txt".format(doc_name))
        json_file_path = os.path.join(WORKING_PATH, "{} Material Report.json".format(doc_name))

        log_lines = [
            "\nDocument: \t{}\n".format(doc.Title),
            "\tMaterial: \t{}\n".format(this_material.Name)
        ]

        json_output = OrderedDict()
        json_output['Source'] = doc.Title
        
        # get the info here
        json_output['Material'] = _get_material_info(doc, this_material, log_lines, 2, True)

        # finalize the log files
        try:
            with io.open(log_file_path, 'w', encoding='utf-8') as f:
                f.writelines(log_lines)
            print("Text report written to: {}".format(log_file_path))

            with io.open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(json_output, f, indent=4)
            print("JSON report written to: {}".format(json_file_path))
                
        except Exception as e:
            print("Error writing report files: {}".format(e))

    # endregion
    print("Finished: Create Simple Material.")


# #############################################################################
# Helper Functions (Translated)
# #############################################################################


def to_unicode(value):
    """
    Safely converts a value to unicode, handling potential errors.
    This is for Python 2.7 (IronPython) compatibility.
    """
    try:
        if isinstance(value, unicode):
            return value
        if isinstance(value, (str, bytes)):
            return value.decode('utf-8')
        return unicode(value)
    except UnicodeError:
        # Fallback for strings with unknown encoding
        try:
            return value.decode('windows-1252')
        except Exception:
             return u"[Encoding Error]"
    except Exception as e:
        return u"[Conversion Error: {}]".format(e)


def _get_material_info(doc, this_mat, log_lines, indent=0, include_parameters=False):
    """
    Gathers detailed information about a specific material.
    Returns a dictionary of the info and appends to log_lines list.
    """
    prefix_str = "\t" * indent
    mat_node = OrderedDict()
    mat_node['Name'] = this_mat.Name
    mat_node['UniqueId'] = this_mat.UniqueId

    if this_mat.Parameters.Size > 0:
        log_lines.append("{} -- Parameters:  {}\n".format(prefix_str, this_mat.Parameters.Size))
        if include_parameters:
            mat_node['Parameters'] = _log_parameters(this_mat.Parameters, doc, log_lines, indent + 1)
            log_lines.append("{} -- End Parameters\n\n".format(prefix_str))

    # region Material Properties
    props_node = OrderedDict()
    log_lines.append("\n{} * Begin Material Properties\n".format(prefix_str))
    
    def add_prop(name, value):
        log_lines.append("{}\t - {}:  {}\n".format(prefix_str, name, value))
        props_node[name] = value

    add_prop("Category", this_mat.MaterialCategory)
    add_prop("Class", this_mat.MaterialClass)
    add_prop("Shininess", this_mat.Shininess)
    add_prop("Smoothness", this_mat.Smoothness)
    add_prop("Transparency", this_mat.Transparency)
    add_prop("Use Render Asset for Shading?", this_mat.UseRenderAppearanceForShading)
    
    c = this_mat.Color
    add_prop("Color", "{}, {}, {}".format(c.Red, c.Green, c.Blue))

    c = this_mat.CutBackgroundPatternColor
    add_prop("CutBackGroundPatternColor", "{}, {}, {}".format(c.Red, c.Green, c.Blue))
    
    cut_back_pat = doc.GetElement(this_mat.CutBackgroundPatternId)
    add_prop("CutBackGroundPattern", cut_back_pat.Name if cut_back_pat else "Not Assigned")

    c = this_mat.CutForegroundPatternColor
    add_prop("CutForeGroundPatternColor", "{}, {}, {}".format(c.Red, c.Green, c.Blue))
    
    cut_front_pat = doc.GetElement(this_mat.CutForegroundPatternId)
    add_prop("CutForeGroundPattern", cut_front_pat.Name if cut_front_pat else "Not Assigned")
    
    c = this_mat.SurfaceBackgroundPatternColor
    add_prop("SurfaceBackGroundPatternColor", "{}, {}, {}".format(c.Red, c.Green, c.Blue))
    
    sur_back_pat = doc.GetElement(this_mat.SurfaceBackgroundPatternId)
    add_prop("SurfaceBackGroundPattern", sur_back_pat.Name if sur_back_pat else "Not Assigned")

    c = this_mat.SurfaceForegroundPatternColor
    add_prop("SurfaceForeGroundPatternColor", "{}, {}, {}".format(c.Red, c.Green, c.Blue))

    sur_front_pat = doc.GetElement(this_mat.SurfaceForegroundPatternId)
    add_prop("SurfaceForeGroundPattern", sur_front_pat.Name if sur_front_pat else "Not Assigned")
    
    mat_node['MaterialProperties'] = props_node
    # endregion

    # region Begin Assets
    
    # --- Render Asset ---
    if this_mat.AppearanceAssetId != DB.ElementId.InvalidElementId:
        render_asset_elem = doc.GetElement(this_mat.AppearanceAssetId)
        
        if render_asset_elem:
            log_lines.append("\n{}Render Asset Element Name:  {}  Unique ID:  {}\n".format(prefix_str, render_asset_elem.Name, render_asset_elem.UniqueId))
            
            asset_xml_node = OrderedDict()
            asset_xml_node['Name'] = render_asset_elem.Name
            asset_xml_node['UniqueId'] = render_asset_elem.UniqueId
            
            if render_asset_elem.Parameters.Size > 0:
                log_lines.append("{}\t -- Asset Parameters:  {}\n".format(prefix_str, render_asset_elem.Parameters.Size))
                if include_parameters:
                    asset_xml_node['Parameters'] = _log_parameters(render_asset_elem.Parameters, doc, log_lines, indent + 2)
                    log_lines.append("{}\t -- End Parameters\n\n".format(prefix_str))
            
            this_asset = render_asset_elem.GetRenderingAsset()
            log_lines.append("\n{}\tName:  {}  |  Asset Type: {}\n".format(prefix_str, this_asset.Name, this_asset.AssetType.ToString()))
            
            this_json_node = OrderedDict()
            this_json_node['Name'] = this_asset.Name
            this_json_node['Size'] = this_asset.Size
            
            if this_asset.Size > 0:
                this_json_node['Properties'] = _get_asset_properties(this_asset, log_lines, indent + 2)
                
            asset_xml_node['Asset'] = this_json_node
            mat_node['RenderAsset'] = asset_xml_node
        else:
            log_lines.append("\n{}\t**Render Asset Element not found**\n".format(prefix_str))
            mat_node['RenderAsset'] = "Not Found"
    else:
        log_lines.append("\n{}\t**No Appearance Asset Element attached**\n".format(prefix_str))
        mat_node['RenderAsset'] = "None"

    # --- Structural Asset ---
    if this_mat.StructuralAssetId != DB.ElementId.InvalidElementId:
        stru_asset_elem = doc.GetElement(this_mat.StructuralAssetId)
        
        if stru_asset_elem:
            log_lines.append("\n{}\tStructural Asset Element Name:  {}  Unique ID:  {}\n".format(prefix_str, stru_asset_elem.Name, stru_asset_elem.UniqueId))
            asset_xml_node = OrderedDict()
            asset_xml_node['Name'] = stru_asset_elem.Name
            asset_xml_node['UniqueId'] = stru_asset_elem.UniqueId

            if stru_asset_elem.Parameters.Size > 0:
                log_lines.append("{}\t -- Asset Parameters:  {}\n".format(prefix_str, stru_asset_elem.Parameters.Size))
                if include_parameters:
                    asset_xml_node['Parameters'] = _log_parameters(stru_asset_elem.Parameters, doc, log_lines, indent + 2)
                    log_lines.append("{}\t -- End Parameters\n\n".format(prefix_str))
            
            stru_asset = stru_asset_elem.GetStructuralAsset()
            asset_xml_node['Asset'] = _get_structural_asset_info(stru_asset, log_lines, indent + 1)
            mat_node['StructuralAsset'] = asset_xml_node
        else:
            log_lines.append("\n{}\t\t**Structural Asset Element not found**\n".format(prefix_str))
            mat_node['StructuralAsset'] = "Not Found"
    else:
        log_lines.append("\n{}\t**No Structural Asset Element attached**\n".format(prefix_str))
        mat_node['StructuralAsset'] = "None"
        
    # --- Thermal Asset ---
    if this_mat.ThermalAssetId != DB.ElementId.InvalidElementId:
        therm_asset_elem = doc.GetElement(this_mat.ThermalAssetId)
        
        if therm_asset_elem:
            log_lines.append("\n{}\tThermal Asset Element Name:  {}  Unique ID:  {}\n".format(prefix_str, therm_asset_elem.Name, therm_asset_elem.UniqueId))
            asset_xml_node = OrderedDict()
            asset_xml_node['Name'] = therm_asset_elem.Name
            asset_xml_node['UniqueId'] = therm_asset_elem.UniqueId
            
            if therm_asset_elem.Parameters.Size > 0:
                log_lines.append("{}\t -- Pset Parameters:  {}\n".format(prefix_str, therm_asset_elem.Parameters.Size))
                if include_parameters:
                    asset_xml_node['Parameters'] = _log_parameters(therm_asset_elem.Parameters, doc, log_lines, indent + 2)
                    log_lines.append("{}\t -- End Parameters\n\n".format(prefix_str))
            
            therm_asset = therm_asset_elem.GetThermalAsset()
            asset_xml_node['Asset'] = _get_thermal_asset_info(therm_asset, log_lines, indent + 1)
            mat_node['ThermalAsset'] = asset_xml_node
        else:
            log_lines.append("\n{}\t\t**Thermal Asset Element not found**\n".format(prefix_str))
            mat_node['ThermalAsset'] = "Not Found"
    else:
        log_lines.append("\n{}\t**No Thermal Asset Element attached**\n".format(prefix_str))
        mat_node['ThermalAsset'] = "None"

    # endregion
    return mat_node


def _get_structural_asset_info(this_asset, log_lines, indent=0):
    """
    Gathers info from a StructuralAsset.
    Returns a dictionary of the info and appends to log_lines list.
    """
    prefix_str = "\t" * indent
    log_lines.append("{}  -  Structural Asset Name: {}  |  Class: {}  |  Sub-Class: {}\n".format(
        prefix_str, this_asset.Name, this_asset.StructuralAssetClass.ToString(), this_asset.SubClass
    ))
    
    indent += 1
    prefix_str = "\t" * indent
    log_lines.append("{}  : Structural Properties : \n".format(prefix_str))

    asset_node = OrderedDict()
    asset_node['Name'] = this_asset.Name
    asset_node['Class'] = this_asset.StructuralAssetClass.ToString()
    asset_node['SubClass'] = this_asset.SubClass
    asset_node['Properties'] = OrderedDict()
    
    def add_prop(name, value):
        log_lines.append("{}  -  {}: {}\n".format(prefix_str, name, value))
        asset_node['Properties'][name] = "{}".format(value) # Ensure value is string
        
    def add_xyz_prop(name, xyz):
        val_str = "{}, {}, {}".format(xyz.X, xyz.Y, xyz.Z)
        log_lines.append("{}  -  {}: {}\n".format(prefix_str, name, val_str))
        asset_node['Properties'][name] = val_str

    # 26 total possible?
    # it looks like all of these have (or return) values all of the time, regardless of type and what is shown in the UI
    # but we will break them down by AssetClass anyway to reduce the printed lines

    # let's start breaking it down:
    if this_asset.StructuralAssetClass != DB.StructuralAssetClass.Undefined:
        # common
        # under Basic Mechanical; everything except perhaps "Undefined"?
        add_prop("Density", this_asset.Density)

        if this_asset.StructuralAssetClass != DB.StructuralAssetClass.Basic:
            # everything except Basic
            # under Basic Thermal;
            # ThermalExpansionCoefficient As RDB.XYZ **Wood or isotrophic behavior elements, use setThermalExpansionCoefficient to set
            add_xyz_prop("Thermal Expansion Coefficient", this_asset.ThermalExpansionCoefficient)

            if this_asset.StructuralAssetClass != DB.StructuralAssetClass.Gas:
                # everything except Gas and Basic
                # under behavior;
                add_prop("Structural Behavior", this_asset.Behavior.ToString())

                if this_asset.StructuralAssetClass != DB.StructuralAssetClass.Liquid:
                    # everything except Gas, liquid, or basic
                    # Basic Mechanical;
                    # PoissonRatio As RDB.XYZ **Wood or isotrophic behavior elements, use setPoissonRatio to set
                    add_xyz_prop("Poisson Ratio", this_asset.PoissonRatio)
                    
                    # ShearModulus As RDB.XYZ **Wood or isotrophic behavior elements, use setShearModulus to set
                    add_xyz_prop("Shear Modulus", this_asset.ShearModulus)

                    # YoungModulus As RDB.XYZ **Wood or isotrophic behavior elements, use setYoungModulus to set
                    add_xyz_prop("Young Modulus", this_asset.YoungModulus)
                    
                    # location varies under strength or concrete;
                    add_prop("Minimum Tensile Strength", this_asset.MinimumTensileStrength)
                    add_prop("Minimum Yield Stress", this_asset.MinimumYieldStress) # VB used MinimumTensileStrength here, fixed.

                    # then get into specific cases
                    if this_asset.StructuralAssetClass == DB.StructuralAssetClass.Concrete:
                        # Concrete specific
                        log_lines.append("{}  * Concrete Specific Properties: \n".format(prefix_str))
                        add_prop("Concrete Bending Reinforcement", this_asset.ConcreteBendingReinforcement)
                        add_prop("Concrete Compression Strength", this_asset.ConcreteCompression)
                        add_prop("Concrete Shear Reinforcement", this_asset.ConcreteShearReinforcement)
                        add_prop("Concrete Shear Strength Reduction", this_asset.ConcreteShearStrengthReduction)
                        add_prop("Light Weight Concrete", this_asset.Lightweight)

                    elif this_asset.StructuralAssetClass == DB.StructuralAssetClass.Metal:
                        # Metal specific
                        log_lines.append("{}  * Metal Specific Properties: \n".format(prefix_str))
                        add_prop("Metal Reduction Factor", this_asset.MetalReductionFactor)
                        add_prop("Metal Resistance Calculation Strength", this_asset.MetalResistanceCalculationStrength)
                        add_prop("Metal Thermally Treated", this_asset.MetalThermallyTreated)

                    elif this_asset.StructuralAssetClass == DB.StructuralAssetClass.Wood:
                        # wood specific (all properties here shown under strength)
                        log_lines.append("{}  * Wood Specific Properties: \n".format(prefix_str))
                        add_prop("Wood Grade", this_asset.WoodGrade)
                        add_prop("Wood Species", this_asset.WoodSpecies)
                        add_prop("Wood Bending Strength", this_asset.WoodBendingStrength)
                        add_prop("Wood Parallel Compression Strength", this_asset.WoodParallelCompressionStrength)
                        add_prop("Wood Parallel Shear Strength", this_asset.WoodParallelShearStrength)
                        add_prop("Wood Perpendicular Compression Strength", this_asset.WoodPerpendicularCompressionStrength)
                        add_prop("Wood Perpendicular Shear Strength", this_asset.WoodPerpendicularShearStrength)
                        
                    # Other cases from VB:
                    # Case RDB.StructuralAssetClass.Basic
                    # Case RDB.StructuralAssetClass.Gas
                    # Case RDB.StructuralAssetClass.Generic
                    # Case RDB.StructuralAssetClass.Liquid
                    # Case RDB.StructuralAssetClass.Plastic
                    # Case RDB.StructuralAssetClass.Undefined
                    
                else:
                    log_lines.append("{}  * No additional Liquid Specific Properties\n".format(prefix_str))
            else:
                log_lines.append("{}  * No additional Gas Specific Properties\n".format(prefix_str))
        else:
            log_lines.append("{}  * No additional Basic Properties\n".format(prefix_str))
    else:
        log_lines.append("{}  * No Properties\n".format(prefix_str))

    log_lines.append("{}  : End Structural Properties : \n".format(prefix_str))
    return asset_node


def _get_thermal_asset_info(this_asset, log_lines, indent=0):
    """
    Gathers info from a ThermalAsset.
    Returns a dictionary of the info and appends to log_lines list.
    """
    prefix_str = "\t" * indent
    log_lines.append("{}  -  Thermal Asset Name: {}  |  Class: {}\n".format(
        prefix_str, this_asset.Name, this_asset.ThermalMaterialType.ToString()
    ))
    
    indent += 1
    prefix_str = "\t" * indent
    log_lines.append("{}  : Thermal Properties : \n".format(prefix_str))

    asset_node = OrderedDict()
    asset_node['Name'] = this_asset.Name
    asset_node['Class'] = this_asset.ThermalMaterialType.ToString()
    asset_node['SubClass'] = "" # Kept for schema consistency with Structural
    asset_node['Properties'] = OrderedDict()

    def add_prop(name, value):
        log_lines.append("{}  -  {}: {}\n".format(prefix_str, name, value))
        asset_node['Properties'][name] = "{}".format(value) # Ensure value is string

    # 16 total possible
    # Common
    # hope we don't need to filter out "Undefined"
    # ThermalConductivity As Double {must be non-negative}
    add_prop("Thermal Conductivity", this_asset.ThermalConductivity)
    # SpecificHeat As Double {must be non-negative}
    add_prop("Specific Heat", this_asset.SpecificHeat)
    # Density As Double {must be non-negative}
    add_prop("Density", this_asset.Density)
    # Emissivity As Double {0 to 1}
    add_prop("Emissivity", this_asset.Emissivity)

    if (this_asset.ThermalMaterialType == DB.ThermalMaterialType.Gas or
        this_asset.ThermalMaterialType == DB.ThermalMaterialType.Liquid):
        # only one that appears in two distinct Types but not the rest
        # Compressibility As Double {0 to 1}
        add_prop("Compressibility", this_asset.Compressibility)

    if this_asset.ThermalMaterialType == DB.ThermalMaterialType.Gas:
        # GasViscosity As Double {must be non-negative}
        add_prop("Gas Viscosity", this_asset.GasViscosity)
        
    elif this_asset.ThermalMaterialType == DB.ThermalMaterialType.Liquid:
        # LiquidViscosity As Double {must be non-negative}
        add_prop("Liquid Viscosity", this_asset.LiquidViscosity)
        # SpecificHeatOfVaporization As Double {must be non-negative}
        add_prop("Specific Heat Of Vaporization", this_asset.SpecificHeatOfVaporization)
        # VaporPressure As Double {must be non-negative}
        add_prop("Vapor Pressure", this_asset.VaporPressure)

    elif this_asset.ThermalMaterialType == DB.ThermalMaterialType.Solid:
        # TransmitsLight As Boolean
        add_prop("Transmits Light", this_asset.TransmitsLight)
        # Behavior As RDB.StructuralBehavior <- No, that isn't a mistake
        add_prop("Behavior", this_asset.Behavior.ToString())
        # Permeability As Double {must be non-negative}
        add_prop("Permeability", this_asset.Permeability)
        # Porosity As Double {0 to 1}
        add_prop("Porosity", this_asset.Porosity)
        # Reflectivity As Double {0 to 1}
        add_prop("Reflectivity", this_asset.Reflectivity)
        # ElectricalResistivity As Double {must be non-negative}
        add_prop("ElectricalResistivity", this_asset.ElectricalResistivity)

    elif this_asset.ThermalMaterialType == DB.ThermalMaterialType.Undefined:
        log_lines.append("{}  * Undefined Thermal Type: \n".format(prefix_str))
        asset_node['Properties']["Undefined Thermal Type"] = ""

    log_lines.append("{}  : End Thermal Properties : \n".format(prefix_str))
    return asset_node


def _get_asset_properties(this_asset, log_lines, indent=0):
    """
    Iterates all properties of an Asset.
    Returns a list of property dictionaries.
    """
    
    # Could consider trying to add a UnifiedBitmap and a BumpmapBitmap
    # to see if the property has the option available to it
    # since we can't find any property that will tell us if it's capable
    # would require starting a transaction,
    # Using thisTrans As New RDB.Transaction(thisDoc, "Temp Material")
    # 	thisTrans.Start()
    # create an editscope
    # Using editScope As New RDV.AppearanceAssetEditScope(thisDoc)
    # assign the incoming asset to it
    # 	Dim editableAsset As RDV.Asset = editScope.Start(thisAsset.Id)
    
    # enter property loop
    # test for connected Assets, if they're there then determine kind if not then
    # attempt to attach a connected asset of each type to each property in a Try... Catch...
    # we already have the property so we don't need to go get it like we did here
    # Dim diffuseMapProperty As RDV.AssetProperty = editableAsset.FindByName("generic_diffuse")
    # diffuseMapProperty.AddConnectedAsset("UnifiedBitmap")
    # diffuseMapProperty.AddConnectedAsset("BumpMap")
    # then report the success and/or failure of each
    # exit property loop
    
    properties_list = []
    
    for i in range(this_asset.Size):
        asset_prop = this_asset[i]
        prop_node = _get_asset_prop_values(asset_prop, log_lines, indent)
        if prop_node:
            properties_list.append(prop_node)
            
    # then rollback the editscope
    # EditScope.Cancel()
    # End Using
    # then rollback the transaction.
    # thisTrans.RollBack()
    
    return properties_list


def _get_asset_prop_values(asset_prop, log_lines, indent=0):
    """
    Gathers info from a single AssetProperty.
    Returns a dictionary of the info and appends to log_lines list.
    """
    print_str = ""
    json_value_str = ""
    prefix_str = "\t" * indent

    prop_node = OrderedDict()
    prop_node['Name'] = asset_prop.Name
    prop_node['Type'] = asset_prop.Type.ToString()
    prop_node['Class'] = asset_prop.GetType().Name
    
    prop_type = asset_prop.Type

    if prop_type == RDV.AssetPropertyType.Asset:
        # sub class is Asset As RDV.Asset (loop for embedded)
        this_prop = asset_prop # In Python, cast is not always needed
        if this_prop:
            log_lines.append("\n{}\t** Embedded Asset **\n".format(prefix_str))
            log_lines.append("{}\tName:  {}  |  Size: {}  |  Library Name: {}  |  Asset Type: {}  |  Asset Class: {}\n".format(
                prefix_str, this_prop.Name, this_prop.Size, this_prop.LibraryName, 
                this_prop.AssetType.ToString(), this_prop.Type.ToString()
            ))
            
            asset_json_node = OrderedDict()
            asset_json_node['Name'] = this_prop.Name
            asset_json_node['Size'] = this_prop.Size
            asset_json_node['Library'] = this_prop.LibraryName
            asset_json_node['Type'] = this_prop.AssetType.ToString()
            asset_json_node['Class'] = this_prop.Type.ToString()
            asset_json_node['Properties'] = _get_asset_properties(this_prop, log_lines, indent + 1)
            
            prop_node['Value'] = asset_json_node
            log_lines.append("{}\t** End Embedded Asset **\n\n".format(prefix_str))
            
            # exit the sub because we don't want the default writeline call at the end
            return prop_node
            
    elif prop_type == RDV.AssetPropertyType.Boolean:
        # sub class is AssetPropertyBoolean As Boolean
        if isinstance(asset_prop, RDV.AssetPropertyBoolean):
            val = asset_prop.Value
            print_str = "  |  Value: {}".format(val)
            json_value_str = val

    elif prop_type == RDV.AssetPropertyType.Distance:
        # sub class is AssetPropertyDistance As Double, with method (GetUnitTypeId As ForgeTypeID)
        if isinstance(asset_prop, RDV.AssetPropertyDistance):
            val = asset_prop.Value
            unit_id = asset_prop.GetUnitTypeId().TypeId
            print_str = "  |  Unit Type: {}  |  Value: {}".format(unit_id, val)
            json_value_str = "{}  |  Unit Type: {}".format(val, unit_id)

    elif prop_type == RDV.AssetPropertyType.Double1:
        # sub class is AssetPropertyDouble As Double
        if isinstance(asset_prop, RDV.AssetPropertyDouble):
            val = asset_prop.Value
            print_str = "  |  Value: {}".format(val)
            json_value_str = val

    elif prop_type == RDV.AssetPropertyType.Double2:
        # sub class is AssetPropertyDoubleArray2d As RDB.DoubleArray
        if isinstance(asset_prop, RDV.AssetPropertyDoubleArray2d):
            if asset_prop.Value.Size > 0:
                vals = [asset_prop.Value.Item[i] for i in range(asset_prop.Value.Size)]
                print_str = "  |  Value: " + ", ".join(map(str, vals))
                json_value_str = vals
                
    elif prop_type == RDV.AssetPropertyType.Double3:
        # sub class is AssetPropertyDoubleArray3d - no Value property
        # use methods (GetValueAsDoubles As IList(Of Double), GetValueAsXYZ As XYZ)
        if isinstance(asset_prop, RDV.AssetPropertyDoubleArray3d):
            vals = asset_prop.GetValueAsDoubles()
            val_xyz = asset_prop.GetValueAsXYZ()
            print_str = "  |  Value: {} | As XYZ: {}, {}, {}".format(
                ", ".join(map(str, vals)), val_xyz.X, val_xyz.Y, val_xyz.Z
            )
            json_value_str = {
                "Doubles": list(vals),
                "XYZ": "{}, {}, {}".format(val_xyz.X, val_xyz.Y, val_xyz.Z)
            }

    elif prop_type == RDV.AssetPropertyType.Double4:
        # sub class is AssetPropertyDoubleArray4d - no Value property
        # use methods (GetValueAsDoubles As IList(Of Double), GetValueAsColor As Color)
        if isinstance(asset_prop, RDV.AssetPropertyDoubleArray4d):
            vals = asset_prop.GetValueAsDoubles()
            val_color = asset_prop.GetValueAsColor()
            print_str = "  |  Value: {} | As RGB: {}, {}, {}".format(
                ", ".join(map(str, vals)), val_color.Red, val_color.Green, val_color.Blue
            )
            json_value_str = {
                "Doubles": list(vals),
                "RGB": "{}, {}, {}".format(val_color.Red, val_color.Green, val_color.Blue)
            }

    elif prop_type == RDV.AssetPropertyType.Double44:
        # sub class is AssetPropertyDoubleMatrix44 As RDB.DoubleArray
        if isinstance(asset_prop, RDV.AssetPropertyDoubleMatrix44):
            if asset_prop.Value.Size > 0:
                vals = [asset_prop.Value.Item[i] for i in range(asset_prop.Value.Size)]
                print_str = "  |  Value: " + ", ".join(map(str, vals))
                json_value_str = vals

    elif prop_type == RDV.AssetPropertyType.Enumeration:
        # sub class is AssetPropertyInteger As Integer
        # never returns anything (in original author's experience)
        if isinstance(asset_prop, RDV.AssetPropertyInteger):
            val = asset_prop.Value
            print_str = "  |  Value: {}".format(val)
            json_value_str = val
            
    elif prop_type == RDV.AssetPropertyType.Float:
        # sub class is AssetPropertyFloat As Single
        if isinstance(asset_prop, RDV.AssetPropertyFloat):
            val = asset_prop.Value
            print_str = "  |  Value: {}".format(val)
            json_value_str = val

    elif prop_type == RDV.AssetPropertyType.Float3:
        # sub class is AssetPropertyFloatArray - no Value property
        # use method (GetValue As IList(Of Single))
        if isinstance(asset_prop, RDV.AssetPropertyFloatArray):
            vals = asset_prop.GetValue()
            print_str = "  |  Value: " + ", ".join(map(str, vals))
            json_value_str = list(vals)

    elif prop_type == RDV.AssetPropertyType.Integer:
        # sub class is AssetPropertyInteger As Integer
        if isinstance(asset_prop, RDV.AssetPropertyInteger):
            val = asset_prop.Value
            print_str = "  |  Value: {}".format(val)
            json_value_str = val

    elif prop_type == RDV.AssetPropertyType.List:
        # sub class is AssetPropertyList - no Value property
        # use method (GetValue As IList(Of AssetProperty))
        if isinstance(asset_prop, RDV.AssetPropertyList):
            list_values = asset_prop.GetValue()
            log_lines.append("{}\tProperty Name:  {}  |  List Count: {}  |  Property Type:  {}  |  API Class Name: {}\n".format(
                prefix_str, asset_prop.Name, list_values.Count, asset_prop.Type.ToString(), asset_prop.GetType().Name
            ))
            
            list_json_node = []
            for val in list_values:
                list_json_node.append(_get_asset_prop_values(val, log_lines, indent + 1))
            
            prop_node['Value'] = list_json_node
            # exit the sub because we don't want the default writeline call at the end
            return prop_node
            
    elif prop_type == RDV.AssetPropertyType.Longlong:
        # sub class is AssetPropertyInt64 As Long
        if isinstance(asset_prop, RDV.AssetPropertyInt64):
            val = asset_prop.Value
            print_str = "  |  Value: {}".format(val)
            json_value_str = val

    elif prop_type == RDV.AssetPropertyType.Properties:
        # sub class is AssetProperties As Set of AssetProperty
        # ??Redundant or possibly never occurs?? See AssetPropertyList and connectedproperties
        print_str = "  |  **AssetPropertyType.Properties"
        json_value_str = "Asset Properties"
        
    elif prop_type == RDV.AssetPropertyType.Reference:
        # sub class is AssetPropertyReference - no Value property
        # will hold a "connected Property" which will be an embedded Asset
        print_str = "  |  No Value: Embedded Asset Element"
        json_value_str = "Embedded Asset Element"
        
    elif prop_type == RDV.AssetPropertyType.String:
        # sub class is AssetPropertyString As String
        if isinstance(asset_prop, RDV.AssetPropertyString):
            val = asset_prop.Value
            print_str = "  |  Value: {}".format(val)
            json_value_str = val

    elif prop_type == RDV.AssetPropertyType.Time:
        # sub class is AssetPropertyTime As DateTime
        if isinstance(asset_prop, RDV.AssetPropertyTime):
            val = asset_prop.Value
            print_str = "  |  Value: {}".format(val.ToString()) # Convert DateTime
            json_value_str = val.ToString()

    elif prop_type == RDV.AssetPropertyType.ULonglong:
        # sub class is AssetPropertyUInt64 As ULong
        if isinstance(asset_prop, RDV.AssetPropertyUInt64):
            val = asset_prop.Value
            print_str = "  |  Value: {}".format(val)
            json_value_str = val
            
    elif prop_type == RDV.AssetPropertyType.Unknown:
        # nothing? a catch all? no value to retrieve
        pass

    log_lines.append("{}\tProperty Name:  {} {}  |  Property Type:  {}  |  API Class Name: {}\n".format(
        prefix_str, asset_prop.Name, print_str, asset_prop.Type.ToString(), asset_prop.GetType().Name
    ))
    
    prop_node['Value'] = json_value_str

    # retrieve detachable assets of this property... 
    if asset_prop.NumberOfConnectedProperties > 0:
        prop_node['ConnectedProperties'] = []
        for connected_prop in asset_prop.GetAllConnectedProperties():
            prop_node['ConnectedProperties'].append(
                _get_asset_prop_values(connected_prop, log_lines, indent + 1)
            )
            
    return prop_node


def _log_parameters(parameters, doc, log_lines, indent=0):
    """
    Gathers info from a ParameterSet.
    Returns a list of parameter dictionaries and appends to log_lines list.
    """
    param_list = []
    for param in parameters:
        param_list.append(_log_param(param, doc, log_lines, indent))
    return param_list


def _log_param(param, doc, log_lines, indent=0):
    """
    Gathers info from a single Parameter.
    Returns a dictionary of the info and appends to log_lines list.
    """
    log_lines.append("\n")
    prefix_str = "\t" * indent
    
    param_node = OrderedDict()
    param_props = OrderedDict()
    param_node['Properties'] = param_props

    try:
        para_def = param.Definition
        if not para_def:
            log_lines.append("{}\t!! No Parameter Definition !!\n".format(prefix_str))
            param_node['Name'] = "Invalid Definition"
            return param_node
            
        param_node['Name'] = para_def.Name
        param_node['ElementId'] = para_def.Id.ToString()

        def add_prop(name, value):
            log_lines.append("{}\t{}: {}\n".format(prefix_str, name, value))
            param_props[name] = "{}".format(value)

        # at parameter Definition level
        if para_def.BuiltInParameter != DB.BuiltInParameter.INVALID:
            type_id = para_def.GetParameterTypeId().TypeId
            log_lines.append("{}\tDefinition IS Built-in: {} : {} : {}\n".format(
                prefix_str, para_def.Id.ToString(), para_def.Name, type_id
            ))
            param_node['TypeId'] = type_id
        else:
            type_id = para_def.GetTypeId().TypeId
            log_lines.append("{}\tDefinition Not Built-in: {} : {} : {}\n".format(
                prefix_str, para_def.Id.ToString(), para_def.Name, type_id
            ))
            param_node['TypeId'] = type_id

        ftID = para_def.GetDataType()
        if ftID.Empty:
            add_prop("Forge Data Type", "Empty")
        else:
            add_prop("Forge Data Type", ftID.TypeId)
            is_spec = DB.SpecUtils.IsSpec(ftID)
            add_prop("Is Spec?", is_spec)
            
            if is_spec:
                add_prop("Spec Display Name", DB.LabelUtils.GetLabelForSpec(ftID))
                is_measurable = DB.UnitUtils.IsMeasurableSpec(ftID)
                add_prop("Is Measurable Spec?", is_measurable)
                if is_measurable:
                    unit_type_id = param.GetUnitTypeId()
                    add_prop("Forge Unit Type ID", unit_type_id.TypeId)
                    add_prop("Unit Display Name", DB.LabelUtils.GetLabelForUnit(unit_type_id))
            else:
                # is Category (only applies to family types)? If so, what category
                is_cat = DB.Category.IsBuiltInCategory(ftID)
                add_prop("Is Category?", is_cat)
                if is_cat:
                    valBIC = DB.Category.GetBuiltInCategory(ftID)
                    add_prop("Built-in Category", "{} : {}".format(valBIC.ToString(), DB.LabelUtils.GetLabelFor(valBIC)))
                else:
                    add_prop("Built-in Category", "No")

        add_prop("Parameter Group", "{} : {}".format(para_def.ParameterGroup, para_def.ParameterGroup.ToString()))
        add_prop("Group Name", DB.LabelUtils.GetLabelFor(para_def.ParameterGroup))
        add_prop("Is User Visible", para_def.Visible)
        add_prop("Can Vary in Groups", para_def.VariesAcrossGroups)

        # at Parameter Instance Level
        # Tells us where it lives:
        # (Global, Family, Project, External, BuiltIn [by not indicating Parameter Def ID and having it's own description instead])
        if param.IsShared:
            add_prop("Shared Param", param.GUID.ToString())
        else:
            if param.Id.IntegerValue < 0:
                bip = param.Id.IntegerValue # This is not the enum, just the int
                add_prop("Built-in Param", "{} : {}".format(param.Id.ToString(), bip.ToString())) # Simplified
            else:
                add_prop("Local Param Id", param.Id.IntegerValue)

        add_prop("Is Read Only?", param.IsReadOnly)
        add_prop("Is User Modifiable?", param.UserModifiable)

        storage_type = param.StorageType
        if storage_type == DB.StorageType.String:
            add_prop("String Value", param.AsString())
        elif storage_type == DB.StorageType.ElementId:
            elem_id = param.AsElementId()
            add_prop("ElementID Value", elem_id.ToString())
            ref_elem = doc.GetElement(elem_id)
            if ref_elem:
                add_prop("Element Class Type", ref_elem.GetType().ToString())
                try:
                    add_prop("Element Category", ref_elem.Category.Name)
                except Exception:
                    add_prop("Element Category", "NULL")
                add_prop("Element Name", ref_elem.Name)
            else:
                add_prop("Element Reference", "NULL")
        elif storage_type == DB.StorageType.Double:
            add_prop("Double Value", param.AsDouble())
            add_prop("Value String", param.AsValueString())
        elif storage_type == DB.StorageType.Integer:
            add_prop("Integer Value", param.AsInteger())
            add_prop("Value String", param.AsValueString())
        else:
            add_prop("Value String", param.AsValueString())

        if param.CanBeAssociatedWithGlobalParameters:
            global_param_id = param.GetAssociatedGlobalParameter()
            if global_param_id != DB.ElementId.InvalidElementId:
                add_prop("Associated to Global Parameter", doc.GetElement(global_param_id).Name)

    except Exception as e:
        log_lines.append("{}\t !! Cannot retrieve Parameter: {} (Error: {})\n".format(
            prefix_str, param.Id.ToString() if param.Id else "N/A", e
        ))
        param_node['Name'] = "Error"
        param_node['Error'] = str(e)

    return param_node


def _generate_name(str_val, existing_names_list):
    """
    Generates a unique name by appending a number.
    """
    numb = 1
    test_str = "001{}".format(str_val)
    
    existing_set = set(existing_names_list) # Faster lookups

    while test_str in existing_set:
        numb += 1
        if numb < 100:
            test_str = "{:03d}{}".format(numb, str_val)
        else:
            test_str = "{}{}".format(numb, str_val)
            
    return test_str


# #############################################################################
# pyRevit Entry Point
# #############################################################################

if __name__ == "__main__":
    # This block runs when the script is executed by pyRevit.
    
    # Get the pyRevit managed "built-in" variables
    try:
        # __revit__ is available in pyRevit scripts
        uidoc = __revit__.ActiveUIDocument
        doc = __revit__.ActiveUIDocument.Document
        app = __revit__.Application
    except NameError:
        print("This script must be run within a pyRevit environment.")
        print("Faking Revit objects for testing purposes...")
        # Simple mock objects for testing outside of Revit
        class MockDoc:
            Title = "FakeRevitDoc"
        class MockApp:
            pass
        class MockUIDoc:
            Document = MockDoc()
        doc = MockDoc()
        app = MockApp()
        uidoc = MockUIDoc()
        
    print("--- Material Tools Script Started ---")
    print("Using working path: {}".format(WORKING_PATH))
    if not os.path.exists(WORKING_PATH):
        print("WARNING: Working path does not exist. Please create it or update the script.")
        print("Attempting to create it...")
        try:
            os.makedirs(WORKING_PATH)
            print("Successfully created directory: {}".format(WORKING_PATH))
        except Exception as e:
            print("Failed to create directory: {}".format(e))
            
    
    # --- Uncomment the function(s) you want to run ---
    
    # print("\nRunning Get Revit Appearance Assets...")
    # get_revit_appearance_assets(doc, app)
    
    # print("\nRunning Get Document Material Assets...")
    # get_doc_material_assets(doc, include_parameters=True)
    
    # print("\nRunning Get Document Materials...")
    # get_doc_materials(doc, include_parameters=True)
    
    print("\nRunning Create Simple Material...")
    try:
        create_simple_material(doc, create_report=True)
    except Exception as e:
        print("An error occurred running create_simple_material:")
        print(traceback.format_exc())

    print("\n--- Material Tools Script Finished ---")
