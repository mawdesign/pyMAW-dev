# -*- coding: utf-8 -*-
"""
Export Wall Types to Excel
Exports multi-layer wall types and their properties to an Excel file.
"""
# # -------------- Standard Library Imports --------------
import sys
import os
import tempfile
import traceback

# # ----------------- 3rd Party Imports ------------------
try:
    import xlsxwriter
except ImportError:
    pass # Handled gracefully in script

# # ------------------ pyRevit Imports -------------------
from pyrevit import script, forms
from pyrevit import revit
from pyrevit import DB, UI


# --- Helper Functions ---

def feet_to_mm(feet_val):
    """Converts Revit internal units (feet) to millimeters."""
    try:
        return round(float(feet_val) * 304.8, 2)
    except (ValueError, TypeError):
        return 0.0

def get_param_value(element, bip=None, name=None):
    """Safely extracts a parameter value as a string."""
    param = None
    if bip:
        param = element.get_Parameter(bip)
    elif name:
        param = element.LookupParameter(name)
        
    if param and param.HasValue:
        if param.StorageType == DB.StorageType.String:
            return param.AsString()
        elif param.StorageType == DB.StorageType.Double:
            return param.AsValueString() or str(param.AsDouble())
        elif param.StorageType == DB.StorageType.Integer:
            return param.AsValueString() or str(param.AsInteger())
        elif param.StorageType == DB.StorageType.ElementId:
            return element.Document.GetElement(param.AsElementId()).Name
    return ""

def get_mapped_param(element, mapped_name, default_name, fallback_bip):
    """Gets parameter by user mapped name, falling back to BIP if it's left as default."""
    if mapped_name == default_name and fallback_bip:
        return get_param_value(element, bip=fallback_bip)
    else:
        return get_param_value(element, name=mapped_name)

def get_wall_function_string(wall_type):
    """Extracts the wall function parameter and maps it to a readable string."""
    func_param = wall_type.get_Parameter(DB.BuiltInParameter.FUNCTION_PARAM)
    func_val = func_param.AsInteger() if func_param else 0
    func_map = {
        0: "Interior", 1: "Exterior", 2: "Foundation", 
        3: "Retaining", 4: "Soffit", 5: "Core-shaft"
    }
    return func_map.get(func_val, "Interior")

def get_layer_function_ui_string(layer):
    """Maps Revit API MaterialFunctionAssignments to UI terminology, pulling 2026+ priority if it exists."""
    func_enum = layer.Function
    
    # Safely extract independent priority if using newer Revit API
    priority = None
    if hasattr(layer, 'Priority'):
        priority = layer.Priority
    elif hasattr(layer, 'LayerPriority'):
        priority = layer.LayerPriority
        
    func_map = {
        DB.MaterialFunctionAssignment.Structure: "Structure",
        DB.MaterialFunctionAssignment.Substrate: "Substrate",
        DB.MaterialFunctionAssignment.Insulation: "Thermal/Air Layer",
        DB.MaterialFunctionAssignment.Finish1: "Finish 1",
        DB.MaterialFunctionAssignment.Finish2: "Finish 2",
        DB.MaterialFunctionAssignment.Membrane: "Membrane Layer",
        DB.MaterialFunctionAssignment.StructuralDeck: "Structural Deck",
        DB.MaterialFunctionAssignment.None: ""
    }
    
    base_str = func_map.get(func_enum, str(func_enum).replace("MaterialFunctionAssignment.", ""))
    
    if func_enum == DB.MaterialFunctionAssignment.Membrane:
        return base_str
        
    # Append the true priority if we found it natively
    if priority is not None:
        return "{} [{}]".format(base_str, priority)
        
    # Fallback default priorities for older APIs
    pri_map = {
        DB.MaterialFunctionAssignment.Structure: 1,
        DB.MaterialFunctionAssignment.StructuralDeck: 1,
        DB.MaterialFunctionAssignment.Substrate: 2,
        DB.MaterialFunctionAssignment.Insulation: 3,
        DB.MaterialFunctionAssignment.Finish1: 4,
        DB.MaterialFunctionAssignment.Finish2: 5
    }
    return "{} [{}]".format(base_str, pri_map.get(func_enum, 5))

# --- Excel Reading Logic (For Update/Append) ---

def read_existing_excel(filepath):
    """Reads existing Excel data using xlrd or COM interop fallbacks."""
    data = []
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
                worksheet = workbook.Worksheets[1]
                used_range = worksheet.UsedRange
                rows = used_range.Rows.Count
                cols = used_range.Columns.Count
                value_array = used_range.Value2
                
                if value_array is not None:
                    if rows == 1 and cols == 1:
                        data.append([value_array])
                    else:
                        for r in range(1, rows + 1):
                            row_data = []
                            for c in range(1, cols + 1):
                                val = value_array[r, c]
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


# --- User Interface Logic ---

def get_parameter_mapping():
    """Builds and displays a WPF Window to ask the user for parameter mappings."""
    xaml_str = """
    <Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
            xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
            Title="Parameter Mapping" Height="410" Width="420" WindowStartupLocation="CenterScreen">
        <Grid Margin="15">
            <Grid.RowDefinitions>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="*"/>
                <RowDefinition Height="Auto"/>
            </Grid.RowDefinitions>
            
            <TextBlock Grid.Row="0" Text="Map Project Parameters:" FontWeight="Bold" FontSize="14" Margin="0,0,0,10"/>
            <TextBlock Grid.Row="1" Text="Update the names below to match your project parameters. Leave the defaults if utilizing standard Built-In Revit parameters." TextWrapping="Wrap" Margin="0,0,0,15"/>
            
            <StackPanel Grid.Row="2" Margin="0,0,0,10">
                <TextBlock Text="Description:" />
                <TextBox Name="txtDesc" Text="Description" />
            </StackPanel>
            
            <StackPanel Grid.Row="3" Margin="0,0,0,10">
                <TextBlock Text="Fire Rating:" />
                <TextBox Name="txtFire" Text="Fire Rating" />
            </StackPanel>
            
            <StackPanel Grid.Row="4" Margin="0,0,0,10">
                <TextBlock Text="Acoustic Rating:" />
                <TextBox Name="txtAcoustic" Text="Acoustic Rating" />
            </StackPanel>
            
            <StackPanel Grid.Row="5" Margin="0,0,0,10">
                <TextBlock Text="Thermal Rating:" />
                <TextBox Name="txtThermal" Text="Thermal Rating" />
            </StackPanel>
            
            <StackPanel Grid.Row="6" Margin="0,0,0,10">
                <TextBlock Text="Manufacturer System Code:" />
                <TextBox Name="txtModel" Text="Model" />
            </StackPanel>
            
            <StackPanel Grid.Row="8" Orientation="Horizontal" HorizontalAlignment="Right">
                <Button Name="btnOk" Content="OK" Width="80" Height="25" Click="submit_click" Margin="0,0,10,0"/>
                <Button Name="btnCancel" Content="Cancel" Width="80" Height="25" Click="cancel_click"/>
            </StackPanel>
        </Grid>
    </Window>
    """
    
    fd, path = tempfile.mkstemp(suffix='.xaml')
    with open(path, 'w') as f:
        f.write(xaml_str)
    os.close(fd)

    class ParamWindow(forms.WPFWindow):
        def __init__(self, xaml_path):
            forms.WPFWindow.__init__(self, xaml_path)
            self.success = False
            self.mapping = {}
            
        def submit_click(self, sender, args):
            self.mapping = {
                'Description': self.txtDesc.Text,
                'FireRating': self.txtFire.Text,
                'AcousticRating': self.txtAcoustic.Text,
                'ThermalRating': self.txtThermal.Text,
                'Model': self.txtModel.Text
            }
            self.success = True
            self.Close()
            
        def cancel_click(self, sender, args):
            self.Close()

    win = ParamWindow(path)
    win.show_dialog()
    os.remove(path) 
    
    if win.success:
        return win.mapping
    return None

# --- Main Script Logic ---

def export_wall_types_to_excel():
    doc = revit.doc
    
    # 1. Verify xlsxwriter availability
    try:
        xlsxwriter
    except NameError:
        forms.alert('The xlsxwriter module is missing from your pyRevit environment.', title='Missing Dependency', warn_icon=True)
        return
        
    # 2. Get User Parameter Mapping
    param_mapping = get_parameter_mapping()
    if not param_mapping:
        return

    # 3. Pick save location
    filepath = forms.save_file(file_ext='xlsx', default_name='WallTypesExport.xlsx', title='Save Wall Types to Excel')
    if not filepath:
        return

    # 4. Handle Existing File Append/Update Scenario
    existing_data = []
    update_mode = 'Overwrite Entire File'
    
    if os.path.exists(filepath):
        update_mode = forms.CommandSwitchWindow.show(
            ['Overwrite Entire File', 'Add New (Keep Existing)', 'Update Existing & Add New'],
            message='The selected Excel file already exists. How would you like to proceed?'
        )
        if not update_mode:
            return 
            
        if update_mode != 'Overwrite Entire File':
            existing_data = read_existing_excel(filepath)
            if existing_data is None:
                return 

    # 5. Collect all Wall Types
    wall_types = DB.FilteredElementCollector(doc).OfClass(DB.WallType).WhereElementIsElementType().ToElements()
    
    base_headers = [
        "Type Mark", "Description", "Type Name", "Fire Rating", 
        "Acoustic Rating", "Thermal Rating", "Manufacturer System Code", "Function"
    ]
    
    new_raw_data = []
    
    # 6. Extract data from Wall Types
    for wt in wall_types:
        if wt.Kind != DB.WallKind.Basic:
            continue
            
        type_mark = get_param_value(wt, bip=DB.BuiltInParameter.WINDOW_TYPE_ID)
        description = get_mapped_param(wt, param_mapping['Description'], "Description", DB.BuiltInParameter.ALL_MODEL_DESCRIPTION)
        fire_rating = get_mapped_param(wt, param_mapping['FireRating'], "Fire Rating", DB.BuiltInParameter.DOOR_FIRE_RATING)
        acoustic = get_mapped_param(wt, param_mapping['AcousticRating'], "Acoustic Rating", None)
        thermal = get_mapped_param(wt, param_mapping['ThermalRating'], "Thermal Rating", None)
        model = get_mapped_param(wt, param_mapping['Model'], "Model", DB.BuiltInParameter.ALL_MODEL_MODEL)
        
        type_name = get_param_value(wt, bip=DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        if not type_name: 
            type_name = wt.Name
            
        wall_function = get_wall_function_string(wt)
        
        row = [type_mark, description, type_name, fire_rating, acoustic, thermal, model, wall_function]
        
        cs = wt.GetCompoundStructure()
        if cs:
            first_core = cs.GetFirstCoreLayerIndex()
            last_core = cs.GetLastCoreLayerIndex()
            struct_idx = cs.StructuralMaterialIndex
            
            for i, layer in enumerate(cs.GetLayers()):
                if i == first_core:
                    row.append("Core Boundary")
                    
                thick_mm = feet_to_mm(layer.Width)
                mat = doc.GetElement(layer.MaterialId)
                mat_name = mat.Name if mat else ""
                is_struct = "Yes" if i == struct_idx else ""
                
                # Fetch explicit UI string instead of raw API Enum
                func_str = get_layer_function_ui_string(layer)
                
                row.extend([thick_mm, mat_name, is_struct, func_str])
                
                if i == last_core:
                    row.append("Core Boundary")
                    
        new_raw_data.append(row)
        
    if not new_raw_data:
        forms.alert("No basic wall types found to export.", title='Export Cancelled', warn_icon=True)
        return

    # 7. Merge logic based on User Selection
    final_data = []
    
    if update_mode == 'Overwrite Entire File' or not existing_data:
        final_data = [base_headers] + new_raw_data
    else:
        final_data = existing_data 
        try:
            type_name_idx = final_data[0].index("Type Name")
        except ValueError:
            type_name_idx = 2 
            
        existing_types = {str(row[type_name_idx]).strip(): r_idx for r_idx, row in enumerate(final_data) if r_idx > 0 and len(row) > type_name_idx}
        
        for new_row in new_raw_data:
            new_type_name = str(new_row[2]).strip()
            
            if new_type_name in existing_types:
                if update_mode == 'Update Existing & Add New':
                    row_idx = existing_types[new_type_name]
                    final_data[row_idx] = new_row
            else:
                final_data.append(new_row)

    # 8. Format Data for Excel Write
    max_cols = max([len(r) for r in final_data])
    header_row = final_data[0]
    while len(header_row) < max_cols:
        header_row.append("Layer Data")
    final_data[0] = header_row
    
    # 9. Write to Excel
    try:
        workbook = xlsxwriter.Workbook(filepath)
        worksheet = workbook.add_worksheet("Wall Types")
        bold_format = workbook.add_format({'bold': True})
        
        for r_idx, row in enumerate(final_data):
            for c_idx, val in enumerate(row):
                if r_idx == 0:
                    worksheet.write(r_idx, c_idx, val, bold_format)
                else:
                    worksheet.write(r_idx, c_idx, val)
                    
        for c_idx in range(max_cols):
            max_len = max([len(str(r[c_idx])) if c_idx < len(r) else 0 for r in final_data])
            col_width = min(max_len + 3, 50) 
            worksheet.set_column(c_idx, c_idx, col_width)
            
        workbook.close()
        forms.alert("Successfully exported/updated {} Wall Types to Excel.".format(len(final_data) - 1), title="Export Complete")
        
    except Exception as e:
        forms.alert("Failed to save the Excel file. Please ensure the file is not currently open.\n\nError: {}".format(e), title="Export Failed", warn_icon=True)

if __name__ == '__main__':
    export_wall_types_to_excel()