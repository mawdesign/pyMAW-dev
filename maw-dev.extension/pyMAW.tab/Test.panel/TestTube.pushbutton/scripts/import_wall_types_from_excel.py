# -*- coding: utf-8 -*-
"""
Import Wall Types from Excel
Reads an Excel file to create multi-layer wall types and their materials.
"""
# # -------------- Standard Library Imports --------------
import sys
import re
import traceback

# # -------------------- .NET Imports --------------------
from System.Collections.Generic import List

# # ------------------ pyRevit Imports -------------------
from pyrevit import script, forms
from pyrevit import revit
from pyrevit import DB, UI

# Initialize pyRevit logger
logger = script.get_logger()

# --- Helper Functions ---

def mm_to_feet(mm_val):
    """Converts millimeters to Revit internal units (feet)."""
    try:
        return float(mm_val) / 304.8
    except (ValueError, TypeError):
        return 0.0

def get_or_create_material(doc, mat_name):
    """Finds a material by name, or creates a new one if it doesn't exist."""
    if not mat_name or str(mat_name).strip() == "":
        return DB.ElementId.InvalidElementId
        
    mat_name = str(mat_name).strip()
    
    # Check if material already exists
    materials = DB.FilteredElementCollector(doc).OfClass(DB.Material)
    for mat in materials:
        if mat.Name.lower() == mat_name.lower():
            return mat.Id
            
    # Create new material
    new_mat_id = DB.Material.Create(doc, mat_name)
    return new_mat_id

def parse_layer_function(func_str):
    """Maps a string value to a Revit MaterialFunctionAssignment and extracts priority."""
    func_str = str(func_str).lower().strip()
    priority = None
    
    # Extract priority from brackets like "[3]"
    match = re.search(r'\[(\d+)\]', func_str)
    if match:
        priority = int(match.group(1))
        
    func_enum = DB.MaterialFunctionAssignment.Finish2 # Default fallback
    
    if "finish" in func_str:
        if "2" in func_str:
            func_enum = DB.MaterialFunctionAssignment.Finish2
        else:
            func_enum = DB.MaterialFunctionAssignment.Finish1
    elif "structure" in func_str or (not match and "1" in func_str):
        func_enum = DB.MaterialFunctionAssignment.Structure
    elif "substrate" in func_str or (not match and "2" in func_str):
        func_enum = DB.MaterialFunctionAssignment.Substrate
    elif "thermal" in func_str or "air" in func_str or "insulation" in func_str or (not match and "3" in func_str):
        func_enum = DB.MaterialFunctionAssignment.Insulation
    elif "membrane" in func_str:
        func_enum = DB.MaterialFunctionAssignment.Membrane
    elif "deck" in func_str:
        func_enum = DB.MaterialFunctionAssignment.StructuralDeck
        
    return func_enum, priority

def sanitize_shell_priorities(layers, ext_shell_count, core_layer_end_idx):
    """Ensures layer functions strictly ascend in priority number from the core outwards to satisfy older Revit validation."""
    pri_val = {
        DB.MaterialFunctionAssignment.Structure: 1,
        DB.MaterialFunctionAssignment.StructuralDeck: 1,
        DB.MaterialFunctionAssignment.Substrate: 2,
        DB.MaterialFunctionAssignment.Insulation: 3,
        DB.MaterialFunctionAssignment.Finish1: 4,
        DB.MaterialFunctionAssignment.Finish2: 5,
        DB.MaterialFunctionAssignment.Membrane: 0
    }
    
    def set_func(layer, target_pri):
        if target_pri <= 1: layer.Function = DB.MaterialFunctionAssignment.Structure
        elif target_pri == 2: layer.Function = DB.MaterialFunctionAssignment.Substrate
        elif target_pri == 3: layer.Function = DB.MaterialFunctionAssignment.Insulation
        elif target_pri == 4: layer.Function = DB.MaterialFunctionAssignment.Finish1
        else: layer.Function = DB.MaterialFunctionAssignment.Finish2

    # Auto-correct Exterior Shell
    if ext_shell_count > 0 and ext_shell_count < layers.Count:
        prev_pri = pri_val.get(layers[ext_shell_count].Function, 1)
        if prev_pri == 0: prev_pri = 1
        
        for i in range(ext_shell_count - 1, -1, -1):
            pri = pri_val.get(layers[i].Function, 5)
            if pri == 0: continue
            if pri < prev_pri:
                logger.warning("    -> Priority Auto-Correct: Exterior shell layer [{}] downgraded to priority {} to prevent Revit error.".format(i, prev_pri))
                set_func(layers[i], prev_pri)
                pri = prev_pri
            prev_pri = pri
            
    # Auto-correct Interior Shell
    if core_layer_end_idx < layers.Count and core_layer_end_idx > 0:
        prev_pri = pri_val.get(layers[core_layer_end_idx - 1].Function, 1)
        if prev_pri == 0: prev_pri = 1
        
        for i in range(core_layer_end_idx, layers.Count):
            pri = pri_val.get(layers[i].Function, 5)
            if pri == 0: continue
            if pri < prev_pri:
                logger.warning("    -> Priority Auto-Correct: Interior shell layer [{}] downgraded to priority {} to prevent Revit error.".format(i, prev_pri))
                set_func(layers[i], prev_pri)
                pri = prev_pri
            prev_pri = pri

def set_parameter_value(element, param_name, value):
    """Attempts to set a parameter by BuiltIn or Name."""
    if not value or str(value).strip() == "": return
    value_str = str(value).strip()
    
    # Map common strings to BuiltInParameters
    bip_map = {
        "Type Mark": DB.BuiltInParameter.WINDOW_TYPE_ID,
        "Description": DB.BuiltInParameter.ALL_MODEL_DESCRIPTION,
        "Fire Rating": DB.BuiltInParameter.DOOR_FIRE_RATING,
        "Manufacturer System Code": DB.BuiltInParameter.ALL_MODEL_MANUFACTURER,
        "Model": DB.BuiltInParameter.ALL_MODEL_MODEL
    }
    
    param = None
    if param_name in bip_map:
        param = element.get_Parameter(bip_map[param_name])
    if not param:
        param = element.LookupParameter(param_name)
        
    if param and not param.IsReadOnly:
        param.Set(value_str)

def read_excel_data(filepath):
    """Reads Excel data using xlrd or COM interop fallbacks."""
    data = []
    
    # 1. Try Pure Python xlrd
    try:
        import xlrd
        wb = xlrd.open_workbook(filepath)
        sheet = wb.sheet_by_index(0)
        for r in range(sheet.nrows):
            row = []
            for c in range(sheet.ncols):
                val = sheet.cell_value(r, c)
                if isinstance(val, float) and val.is_integer():
                    row.append(int(val))
                else:
                    row.append(val)
            data.append(row)
        return data
    except Exception as e1:
        logger.debug("xlrd failed, trying COM interop fallback: {}".format(e1))
        # 2. Try COM Interop Fallback
        try:
            import clr
            clr.AddReference("Microsoft.Office.Interop.Excel")
            import Microsoft.Office.Interop.Excel as Excel
            excel = Excel.ApplicationClass()
            excel.Visible = False
            excel.DisplayAlerts = False
            workbook = None
            try:
                workbook = excel.Workbooks.Open(filepath)
                worksheet = workbook.Worksheets[1] # 1-indexed in COM
                used_range = worksheet.UsedRange
                rows = used_range.Rows.Count
                cols = used_range.Columns.Count
                
                value_array = used_range.Value2
                
                if value_array is not None:
                    if rows == 1 and cols == 1:
                        data.append([value_array])
                    else:
                        try:
                            for r in range(1, rows + 1):
                                row_data = []
                                for c in range(1, cols + 1):
                                    val = value_array[r, c]
                                    row_data.append(val if val is not None else "")
                                data.append(row_data)
                        except Exception:
                            data = [] 
                            start_row = used_range.Row
                            start_col = used_range.Column
                            for r in range(start_row, start_row + rows):
                                row_data = []
                                for c in range(start_col, start_col + cols):
                                    val = worksheet.Cells[r, c].Value2
                                    row_data.append(val if val is not None else "")
                                data.append(row_data)
            finally:
                if workbook: workbook.Close(False)
                excel.Quit()
                import System
                System.Runtime.InteropServices.Marshal.ReleaseComObject(excel)
            return data
        except Exception as e2:
            forms.alert("Could not read existing Excel file for append/update.\n\nxlrd Error: {}\nCOM Error: {}".format(e1, e2), title="Read Error", warn_icon=True)
            return None


# --- Main Script Logic ---

def import_wall_types_from_excel():
    doc = revit.doc
    
    # 1. Pick the Excel File
    filepath = forms.pick_file(file_ext='xlsx', title='Select Wall Types Excel File')
    if not filepath:
        return

    # 2. Read data from Excel
    raw_data = read_excel_data(filepath)
    if not raw_data:
        return 

    if len(raw_data) < 2:
        forms.alert('Excel file appears to be empty or missing data rows.', title='Error', warn_icon=True)
        return

    # Remove headers
    headers = raw_data[0]
    wall_rows = raw_data[1:]

    # 3. Get a base wall type to duplicate
    base_wall_type = DB.FilteredElementCollector(doc).OfClass(DB.WallType).WhereElementIsElementType().FirstElement()
    if not base_wall_type:
        forms.alert('No existing Wall Types found in the document to act as a template.', title='Error', warn_icon=True)
        return

    walls_created = 0

    # 4. Execute creation within a Transaction
    with revit.Transaction("Create Wall Types from Excel"):
        for row in wall_rows:
            try:
                # Ensure row has enough base columns
                if len(row) < 8:
                    continue
                    
                # Base Attributes
                type_mark = row[0]
                description = row[1]
                type_name = str(row[2]).strip()
                fire_rating = row[3]
                acoustic_rating = row[4] 
                thermal_rating = row[5] 
                manufacturer = row[6]
                wall_function_str = str(row[7]).lower().strip()
                
                if not type_name:
                    continue 
                    
                # Check if wall type already exists
                existing_type = DB.FilteredElementCollector(doc).OfClass(DB.WallType).WhereElementIsElementType().ToElements()
                type_exists = False
                for wt in existing_type:
                    wt_name_param = wt.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
                    if wt_name_param and wt_name_param.AsString() == type_name:
                        type_exists = True
                        break
                        
                if type_exists:
                    logger.info("Skipping '{}': Wall Type already exists.".format(type_name))
                    continue
                    
                logger.debug("Processing Wall Type: {}".format(type_name))
                
                # Duplicate the base wall type
                new_wall_type = base_wall_type.Duplicate(type_name)
                
                # Set Base Parameters
                set_parameter_value(new_wall_type, "Type Mark", type_mark)
                set_parameter_value(new_wall_type, "Description", description)
                set_parameter_value(new_wall_type, "Fire Rating", fire_rating)
                set_parameter_value(new_wall_type, "Model", manufacturer)
                set_parameter_value(new_wall_type, "Acoustic Rating", acoustic_rating)
                set_parameter_value(new_wall_type, "Thermal Rating", thermal_rating)
                
                # Set Wall Function
                wall_func_param = new_wall_type.get_Parameter(DB.BuiltInParameter.FUNCTION_PARAM)
                if "exterior" in wall_function_str:
                    wall_func_param.Set(1) 
                elif "foundation" in wall_function_str:
                    wall_func_param.Set(2) 
                elif "retaining" in wall_function_str:
                    wall_func_param.Set(3) 
                elif "soffit" in wall_function_str:
                    wall_func_param.Set(4) 
                elif "core" in wall_function_str or "shaft" in wall_function_str:
                    wall_func_param.Set(5) 
                else:
                    wall_func_param.Set(0) 
                    
                # Parse Layers
                layers = List[DB.CompoundStructureLayer]()
                ext_shell_count = 0
                int_shell_count = 0
                core_boundaries_found = 0
                structural_layer_index = -1
                
                idx = 8
                while idx < len(row):
                    cell_val = str(row[idx]).strip()
                    
                    if "core" in cell_val.lower() and "boundary" in cell_val.lower():
                        logger.debug("  Found 'Core Boundary' at column index {}".format(idx))
                        if core_boundaries_found == 0:
                            ext_shell_count = layers.Count
                        elif core_boundaries_found == 1:
                            core_layer_end_idx = layers.Count
                        core_boundaries_found += 1
                        idx += 1 
                        continue
                    
                    if idx + 3 < len(row):
                        thick_val = row[idx]
                        mat_val = row[idx+1]
                        struct_val = str(row[idx+2]).lower()
                        func_val = row[idx+3]
                        
                        logger.debug("  Reading Layer at cols {}-{}: Thick='{}', Mat='{}', Struct='{}', Func='{}'".format(
                            idx, idx+3, thick_val, mat_val, struct_val, func_val))
                        
                        if str(func_val).strip() != "":
                            thickness = mm_to_feet(thick_val)
                            mat_id = get_or_create_material(doc, mat_val)
                            
                            # Parse function and priority
                            layer_func, layer_priority = parse_layer_function(func_val)
                            
                            # --- LAYER VALIDITY RULES ---
                            if layer_func == DB.MaterialFunctionAssignment.Membrane:
                                thickness = 0.0 # Membranes must strictly be 0 thickness
                            elif thickness <= 0.0:
                                logger.warning("    -> Layer '{}' has 0 thickness but is mapped to non-membrane function '{}'for {}. Forcing to Membrane to prevent Revit API error.".format(mat_val, func_val, type_name))
                                layer_func = DB.MaterialFunctionAssignment.Membrane
                                
                            logger.debug("    -> Adding Layer: Thickness={} ft, Material ID={}, Function={}, Priority={}".format(
                                thickness, mat_id, layer_func, layer_priority))
                                
                            # Create Layer
                            new_layer = DB.CompoundStructureLayer(thickness, layer_func, mat_id)
                            
                            # Apply independent priority if running on newer Revit (2026+) API
                            if layer_priority is not None:
                                if hasattr(new_layer, 'Priority'):
                                    new_layer.Priority = layer_priority
                                elif hasattr(new_layer, 'LayerPriority'):
                                    new_layer.LayerPriority = layer_priority
                            
                            # Is Structural?
                            if "yes" in struct_val or "y" in struct_val or "true" in struct_val or "1" in struct_val:
                                structural_layer_index = layers.Count
                                
                            layers.Add(new_layer)
                        else:
                            logger.debug("    -> Skipping Layer: Function column is empty.")
                    
                    idx += 4 # Advance to next layer block
                    
                logger.debug("  Total Layers Parsed: {}, Core Boundaries Found: {}".format(layers.Count, core_boundaries_found))
                
                # Apply Compound Structure if we successfully read layers
                if layers.Count > 0:
                    
                    # Ensure core boundaries are logical
                    if core_boundaries_found == 0:
                        ext_shell_count = 0
                        core_layer_end_idx = layers.Count
                    elif core_boundaries_found == 1:
                        core_layer_end_idx = layers.Count
                        
                    if ext_shell_count >= layers.Count or core_layer_end_idx <= ext_shell_count:
                        logger.warning("    -> Invalid core boundaries detected for {}. Forcing all layers into the Core to ensure wall creation.".format(type_name))
                        ext_shell_count = 0
                        core_layer_end_idx = layers.Count
                        
                    is_valid_struct = True
                    # Fix Structural Layer function before creation
                    if structural_layer_index != -1:
                        if ext_shell_count <= structural_layer_index < core_layer_end_idx:
                            func = layers[structural_layer_index].Function
                            if func != DB.MaterialFunctionAssignment.Structure and func != DB.MaterialFunctionAssignment.StructuralDeck:
                                logger.warning("    -> Layer {} marked as Structural must have 'Structure' function for {}. Auto-correcting.".format(structural_layer_index, type_name))
                                layers[structural_layer_index].Function = DB.MaterialFunctionAssignment.Structure
                        else:
                            is_valid_struct = False
                            
                    try:
                        # Attempt 1: Faithful creation using Excel's function + priority
                        cs = DB.CompoundStructure.CreateSimpleCompoundStructure(layers)
                        
                        cs.SetNumberOfShellLayers(DB.ShellLayerType.Exterior, ext_shell_count)
                        int_shell_count = layers.Count - core_layer_end_idx
                        cs.SetNumberOfShellLayers(DB.ShellLayerType.Interior, int_shell_count)
                        
                        if structural_layer_index != -1 and is_valid_struct:
                            cs.StructuralMaterialIndex = structural_layer_index
                            
                        new_wall_type.SetCompoundStructure(cs)
                        logger.info("Successfully applied compound structure to '{}'".format(type_name))
                        walls_created += 1
                        
                    except Exception as e:
                        logger.warning("    -> Initial structure application failed for '{}': {}. Attempting priority auto-correction fallback.".format(type_name, e))
                        
                        # Attempt 2: Sanitize Priorities to satisfy older Revit validation
                        sanitize_shell_priorities(layers, ext_shell_count, core_layer_end_idx)
                        
                        try:
                            cs_fallback = DB.CompoundStructure.CreateSimpleCompoundStructure(layers)
                            cs_fallback.SetNumberOfShellLayers(DB.ShellLayerType.Exterior, ext_shell_count)
                            cs_fallback.SetNumberOfShellLayers(DB.ShellLayerType.Interior, int_shell_count)
                            
                            if structural_layer_index != -1 and is_valid_struct:
                                cs_fallback.StructuralMaterialIndex = structural_layer_index
                                
                            new_wall_type.SetCompoundStructure(cs_fallback)
                            logger.info("Successfully applied compound structure to '{}' after priority auto-correction.".format(type_name))
                            walls_created += 1
                        except Exception as fallback_e:
                            logger.error("Failed to apply structure to '{}' even after fallback: {}".format(type_name, fallback_e))
                else:
                    logger.warning("WARNING: No layers were found or parsed for '{}'".format(type_name))

            except Exception as e:
                # Catch row-specific errors and log the traceback
                type_name_safe = str(row[2]).strip() if len(row) > 2 else "Unknown"
                logger.error("--- Error processing wall type: {} ---".format(type_name_safe))
                logger.error(traceback.format_exc())

    # 5. Completion Message
    forms.alert("Successfully created {} new Wall Type(s).".format(walls_created), title="Complete")

if __name__ == '__main__':
    import_wall_types_from_excel()