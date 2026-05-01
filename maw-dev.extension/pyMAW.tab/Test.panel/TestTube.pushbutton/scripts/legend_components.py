# -*- coding: utf-8 -*-
"""
Legend Components
Places Legend Components for all types of a selected category in a grid.

Check that the current view is a legend view, asks for the category, and
uses an existing legend component in the view as the base/origin to duplicate.
"""
# # -------------- Standard Library Imports --------------
# import os
import sys
# import clr
# import wpf

# # -------------------- .NET Imports --------------------
# clr.AddReference("System.Drawing")
# clr.AddReference("PresentationFramework")
# clr.AddReference("PresentationCore")
# clr.AddReference("WindowsBase")

# # ------------------ pyRevit Imports -------------------
from pyrevit import script, forms
from pyrevit import revit
from pyrevit import DB #, UI

# Get current document and pyRevit script engine
doc = revit.doc
logger = script.get_logger()

def legend_components():
    # 1. Check if Active View is a Legend View
    if doc.ActiveView.ViewType != DB.ViewType.Legend:
        forms.alert("The active view must be a Legend view.", exitscript=True)
        
    # 2. Prompt user for Category using pyRevit's built-in SelectFromList
    # We do this before picking a point so the UI dialog doesn't interrupt the click action
    categories = [c for c in doc.Settings.Categories if c.CategoryType == DB.CategoryType.Model and c.Name]
    cat_names = sorted([c.Name for c in categories])
    
    selected_cat_name = forms.SelectFromList.show(
        cat_names,
        title='Select a Category',
        button_name='Select',
        multiselect=False
    )
    
    if not selected_cat_name:
        sys.exit()
        
    selected_category = next((c for c in categories if c.Name == selected_cat_name), None)
    
    # 3. Find a base Legend Component to duplicate
    # Revit API does not allow creating new Legend Components from scratch.
    selection = revit.get_selection()
    selected_comps = [el for el in selection.elements if el.Category and el.Category.Id.IntegerValue == int(DB.BuiltInCategory.OST_LegendComponents)]
    
    if selected_comps:
        base_component = selected_comps[0]
    else:
        # Fallback: find any legend component in the active view
        view_legend_components = DB.FilteredElementCollector(doc, doc.ActiveView.Id) \
            .OfCategory(DB.BuiltInCategory.OST_LegendComponents) \
            .WhereElementIsNotElementType() \
            .ToElements()
            
        if not view_legend_components:
            forms.alert(
                "No Legend Components found in this view.\n\n"
                "The Revit API requires an existing Legend Component to duplicate. "
                "Please place at least ONE manually anywhere in the view, and run the script again.",
                exitscript=True
            )
        base_component = view_legend_components[0]
        
    # Robustly determine the base location (Fix for missing LocationPoint)
    base_loc = None
    if hasattr(base_component, "Location") and isinstance(base_component.Location, DB.LocationPoint):
        base_loc = base_component.Location.Point
    else:
        # Fallback: use the center of the bounding box
        bbox = base_component.get_BoundingBox(doc.ActiveView)
        if bbox:
            base_loc = (bbox.Min + bbox.Max) / 2.0
            
    if not base_loc:
        forms.alert("The base Legend Component does not have a valid location point or bounding box.", exitscript=True)
        
    # 4. Prompt user to pick the starting point for the grid
    try:
        origin = revit.uidoc.Selection.PickPoint("Click to set the top-left starting point for the Legend Grid")
    except Exception:
        # User canceled the point picking operation (e.g. pressed ESC)
        sys.exit()
    
    # 5. Get all Types for the selected Category
    element_types = DB.FilteredElementCollector(doc) \
        .OfCategoryId(selected_category.Id) \
        .WhereElementIsElementType() \
        .ToElements()
        
    if not element_types:
        forms.alert("No types found for the category '{}'.".format(selected_cat_name), exitscript=True)
        
    # Get all placed instances to count them securely by Integer Value
    all_instances = DB.FilteredElementCollector(doc) \
        .OfCategoryId(selected_category.Id) \
        .WhereElementIsNotElementType() \
        .ToElements()
        
    instance_counts = {}
    for inst in all_instances:
        type_id = inst.GetTypeId()
        if type_id != DB.ElementId.InvalidElementId:
            tid_val = type_id.IntegerValue
            if tid_val not in instance_counts:
                instance_counts[tid_val] = 0
            instance_counts[tid_val] += 1
            
    # Get a default Text Note Type to use for the labels
    default_text_type = DB.FilteredElementCollector(doc) \
        .OfClass(DB.TextNoteType) \
        .FirstElement()
        
    if not default_text_type:
        forms.alert("No Text Note Types found in the model. Please create one to use this tool.", exitscript=True)

    # Helper functions to safely get names avoiding IronPython AttributeErrors
    def safe_get_name(elem):
        try:
            return elem.Name
        except AttributeError:
            param = elem.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
            return param.AsString() if param else "Unknown Type"

    def safe_get_fam_name(elem):
        try:
            return elem.FamilyName
        except AttributeError:
            param = elem.get_Parameter(DB.BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)
            return param.AsString() if param else "System Family"

    # 6. Group Types by Family Name
    families_dict = {}
    for elem_type in element_types:
        fam_name = safe_get_fam_name(elem_type)
        if not fam_name:
            fam_name = "System Family"
            
        if fam_name not in families_dict:
            families_dict[fam_name] = []
        families_dict[fam_name].append(elem_type)
        
    # 7. Place the Legend Components in a 3m x 3m grid
    # Convert 3 meter to Revit internal units (decimal feet)
    grid_size = 3.0 / 0.3048 
    
    sorted_families = sorted(families_dict.keys())
    
    placed_count = 0
    errors = 0
    
    with revit.Transaction("Place Legend Components - {}".format(selected_cat_name)):
        for row_idx, fam_name in enumerate(sorted_families):
            types = families_dict[fam_name]
            # Sort types alphabetically by Name along the X-axis
            types = sorted(types, key=lambda x: safe_get_name(x))
            
            for col_idx, elem_type in enumerate(types):
                # Calculate translation vector from the base component
                # X moves positive (right) per type
                # Y moves negative (down) per family row
                target_pt = origin + DB.XYZ(col_idx * grid_size, -row_idx * grid_size, 0)
                translation = target_pt - base_loc
                
                try:
                    # Duplicate the base component using the calculated translation
                    new_ids = DB.ElementTransformUtils.CopyElement(doc, base_component.Id, translation)
                    new_comp = doc.GetElement(new_ids[0])
                    
                    # Set the new type parameter
                    param = new_comp.get_Parameter(DB.BuiltInParameter.LEGEND_COMPONENT)
                    if param and not param.IsReadOnly:
                        param.Set(elem_type.Id)
                        
                        # Add text note under the component
                        count = instance_counts.get(elem_type.Id.IntegerValue, 0)
                        text_str = "Family: {}\nType: {}\nInstances: {}".format(fam_name, safe_get_name(elem_type), count)
                        
                        # Place text 1 meter below the legend component's origin
                        text_offset = 1.0 / 0.3048
                        text_pt = target_pt - DB.XYZ(0, text_offset, 0)
                        
                        DB.TextNote.Create(doc, doc.ActiveView.Id, text_pt, text_str, default_text_type.Id)
                        
                        placed_count += 1
                except Exception as e:
                    # Logs silently to the backend in case a specific system type isn't allowed to be a legend
                    logger.debug("Failed to place {}: {}".format(safe_get_name(elem_type), e))
                    errors += 1
                    
    # 8. Finish and notify
    if errors > 0:
        forms.alert("Placed {} components. {} could not be placed (some system types may not be supported natively as Legend Components).".format(placed_count, errors))
    else:
        forms.alert("Successfully placed {} legend components in a 3m grid!".format(placed_count))

if __name__ == '__main__':
    legend_components()
