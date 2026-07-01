# -*- coding: utf-8 -*-
"""
Legend Components
Places Legend Components for all types of a selected category in a grid.

Check that the current view is a legend view, asks for the category, and
uses an existing legend component in the view as the base/origin to duplicate.
Includes advanced features for forcing floor plan representation and 
tracing layered compound structures (Walls/Floors/Roofs/Ceilings) with Detail Components.
"""
# # -------------- Standard Library Imports --------------
import sys
import math

# # ------------------ pyRevit Imports -------------------
from pyrevit import script, forms
from pyrevit import revit
from pyrevit import DB

# Grid Configuration (Variables for future UI form)
MAX_ITEMS_PER_ROW = 10
SPACING_X_M = 3.0
SPACING_Y_M = 3.0
TEXT_OFFSET_Y_M = 1.0
HOST_LENGTH_M = 1.0

# Feature Toggles
FORCE_SELECTED_VIEW_VALUE = -8 # Value used to force Floor Plan representation (e.g. for Walls)

# Get current document and pyRevit script engine
doc = revit.doc
logger = script.get_logger()

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

def legend_tag(pairs):
    """
    Dummy function for future integration with the tagging library module.
    Expected to populate annotation parameters based on the associated legend component.
    :param pairs: List of tuples -> [(legend_component_instance, generic_annotation_instance), ...]
    """
    pass

def legend_components():
    # 1. Check if Active View is a Legend View
    if doc.ActiveView.ViewType != DB.ViewType.Legend:
        forms.alert("The active view must be a Legend view.", exitscript=True)
        
    # 2. Find a base Legend Component to duplicate (Moved to start)
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
        
    # 3. Prompt user for Category
    # Filter categories to ONLY those that have at least one ElementType in the project
    categories = []
    for c in doc.Settings.Categories:
        if c.CategoryType == DB.CategoryType.Model and c.Name:
            if DB.FilteredElementCollector(doc).OfCategoryId(c.Id).WhereElementIsElementType().FirstElement():
                categories.append(c)
                
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
    
    # 3.5 Layer Drawing Options (Triggered only if Category is a layered type)
    layered_category_ids = [
        int(DB.BuiltInCategory.OST_Walls),
        int(DB.BuiltInCategory.OST_Floors),
        int(DB.BuiltInCategory.OST_Roofs),
        int(DB.BuiltInCategory.OST_Ceilings)
    ]
    
    draw_layers_mode = "None"
    detail_comp_type = None
    
    if selected_category.Id.IntegerValue in layered_category_ids:
        mode_opts = ["None", "Outer faces", "Core faces", "All layer faces"]
        draw_layers_mode = forms.SelectFromList.show(
            mode_opts,
            title='Draw detail lines on layer faces?',
            button_name='Select'
        )
        if draw_layers_mode and draw_layers_mode != "None":
            # Collect Line-based Detail Components
            det_comps = DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_DetailComponents).WhereElementIsElementType().ToElements()
            
            line_based_types = []
            for dc in det_comps:
                if dc.Family and dc.Family.FamilyPlacementType == DB.FamilyPlacementType.CurveBasedDetail:
                    line_based_types.append(dc)
                    
            if not line_based_types:
                forms.alert("No Line-Based Detail Components found in the project. Layer lines will be skipped.")
                draw_layers_mode = "None"
            else:
                type_names = ["{} : {}".format(dc.FamilyName, safe_get_name(dc)) for dc in line_based_types]
                type_names.sort()
                
                selected_dc_name = forms.SelectFromList.show(
                    type_names,
                    title='Select Line-Based Detail Component',
                    button_name='Select',
                    multiselect=False
                )
                
                if selected_dc_name:
                    for dc in line_based_types:
                        if "{} : {}".format(dc.FamilyName, safe_get_name(dc)) == selected_dc_name:
                            detail_comp_type = dc
                            break
                else:
                    draw_layers_mode = "None"
    
    # 4. Prompt user to pick the starting point for the grid
    try:
        origin = revit.uidoc.Selection.PickPoint("Click to set the top-left starting point for the Legend Grid")
    except Exception:
        # User canceled the point picking operation (e.g. pressed ESC)
        sys.exit()
        
    # 4.5 Prompt user for the Generic Annotation type to use as a tag
    anno_types = DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_GenericAnnotation).WhereElementIsElementType().ToElements()
    if not anno_types:
        forms.alert("No Generic Annotation types found. Please load one to use as a tag.", exitscript=True)

    anno_type_names = ["{} : {}".format(safe_get_fam_name(at), safe_get_name(at)) for at in anno_types]
    anno_type_names.sort()

    selected_anno_name = forms.SelectFromList.show(
        anno_type_names,
        title='Select Generic Annotation for Tagging',
        button_name='Select',
        multiselect=False
    )
    if not selected_anno_name:
        sys.exit()

    selected_anno_type = next((at for at in anno_types if "{} : {}".format(safe_get_fam_name(at), safe_get_name(at)) == selected_anno_name), None)
    
    # 5. Get all Types for the selected Category
    element_types = DB.FilteredElementCollector(doc) \
        .OfCategoryId(selected_category.Id) \
        .WhereElementIsElementType() \
        .ToElements()
        
    if not element_types:
        forms.alert("No types found for the category '{}'.".format(selected_cat_name), exitscript=True)

    # 6. Group Types by Family Name
    families_dict = {}
    for elem_type in element_types:
        fam_name = safe_get_fam_name(elem_type)
        if not fam_name:
            fam_name = "System Family"
            
        if fam_name not in families_dict:
            families_dict[fam_name] = []
        families_dict[fam_name].append(elem_type)
        
    # 7. Place the Legend Components using defined variables
    # Convert meters to Revit internal units (decimal feet)
    M_TO_FT = 1.0 / 0.3048
    spacing_x = SPACING_X_M * M_TO_FT
    spacing_y = SPACING_Y_M * M_TO_FT
    text_offset = TEXT_OFFSET_Y_M * M_TO_FT
    host_length = HOST_LENGTH_M * M_TO_FT
    
    sorted_families = sorted(families_dict.keys())
    
    placed_count = 0
    errors = 0
    error_logs = []
    legend_anno_pairs = []
    
    with revit.Transaction("Place Legend Components - {}".format(selected_cat_name)):
        row_idx = 0
        for fam_name in sorted_families:
            types = families_dict[fam_name]
            # Sort types alphabetically by Name along the X-axis
            types = sorted(types, key=lambda x: safe_get_name(x))
            
            # Split into chunks of MAX_ITEMS_PER_ROW to wrap long families onto multiple rows
            for i in range(0, len(types), MAX_ITEMS_PER_ROW):
                chunk = types[i:i + MAX_ITEMS_PER_ROW]
                
                for col_idx, elem_type in enumerate(chunk):
                    # Calculate translation vector from the base component
                    # X moves positive (right) per type
                    # Y moves negative (down) per family row
                    target_pt = origin + DB.XYZ(col_idx * spacing_x, -row_idx * spacing_y, 0)
                    translation = target_pt - base_loc
                    
                    try:
                        # Duplicate the base component using the calculated translation
                        new_ids = DB.ElementTransformUtils.CopyElement(doc, base_component.Id, translation)
                        new_comp = doc.GetElement(new_ids[0])
                        
                        try:
                            # Set the new type parameter
                            param = new_comp.get_Parameter(DB.BuiltInParameter.LEGEND_COMPONENT)
                            if param and not param.IsReadOnly:
                                param.Set(elem_type.Id)
                                
                                # Force view representation to Plan View
                                view_param = new_comp.get_Parameter(DB.BuiltInParameter.LEGEND_COMPONENT_VIEW)
                                if view_param and not view_param.IsReadOnly:
                                    try:
                                        view_param.Set(FORCE_SELECTED_VIEW_VALUE)
                                    except Exception:
                                        pass
                                
                                # Safely set Host Length or Component Length avoiding BuiltInParameter AttributeErrors
                                # 1. Try by string lookup (most common for 'Host Length' and 'Component Length')
                                for p_name in ["Host Length", "Component Length"]:
                                    length_param = new_comp.LookupParameter(p_name)
                                    if length_param and not length_param.IsReadOnly:
                                        length_param.Set(host_length)
                                        
                                # 2. Try by BuiltInParameter safely if they exist in this Revit API version
                                for bip_name in ["LEGEND_COMPONENT_HOST_LENGTH", "LEGEND_COMPONENT_LENGTH"]:
                                    if hasattr(DB.BuiltInParameter, bip_name):
                                        bip_param = new_comp.get_Parameter(getattr(DB.BuiltInParameter, bip_name))
                                        if bip_param and not bip_param.IsReadOnly:
                                            bip_param.Set(host_length)
                                
                                placed_count += 1
                                
                                # Place Generic Annotation under the component
                                text_pt = target_pt - DB.XYZ(0, text_offset, 0)
                                
                                try:
                                    # Ensure the family symbol is active in the project before placement
                                    if not selected_anno_type.IsActive:
                                        selected_anno_type.Activate()
                                        doc.Regenerate()
                                        
                                    new_anno = doc.Create.NewFamilyInstance(text_pt, selected_anno_type, doc.ActiveView)
                                    legend_anno_pairs.append((new_comp, new_anno))
                                except Exception as anno_e:
                                    import traceback
                                    err_msg = "Failed to place annotation for {}:\n{}".format(safe_get_name(elem_type), traceback.format_exc())
                                    logger.debug(err_msg)
                                    error_logs.append(err_msg)
                                    
                                # Draw Layer Lines if configured
                                if draw_layers_mode and draw_layers_mode != "None" and detail_comp_type:
                                    struct = elem_type.GetCompoundStructure() if hasattr(elem_type, "GetCompoundStructure") else None
                                    if struct:
                                        layers = struct.GetLayers()
                                        if layers:
                                            total_width = sum([l.Width for l in layers])
                                            y_offsets = []
                                            
                                            if draw_layers_mode == "Outer faces":
                                                y_offsets.extend([total_width / 2.0, -total_width / 2.0])
                                            elif draw_layers_mode == "Core faces":
                                                cb1 = struct.GetFirstCoreLayerIndex()
                                                cb2 = struct.GetLastCoreLayerIndex()
                                                y = total_width / 2.0
                                                for idx, layer in enumerate(layers):
                                                    if idx == cb1: y_offsets.append(y)
                                                    y -= layer.Width
                                                    if idx == cb2: y_offsets.append(y)
                                            elif draw_layers_mode == "All layer faces":
                                                y = total_width / 2.0
                                                y_offsets.append(y)
                                                for layer in layers:
                                                    y -= layer.Width
                                                    y_offsets.append(y)
                                                    
                                            # Remove duplicates while preserving drawing order
                                            unique_y_offsets = []
                                            for y_off in y_offsets:
                                                if y_off not in unique_y_offsets:
                                                    unique_y_offsets.append(y_off)
                                                    
                                            # Draw lines natively into the active view
                                            for y_off in unique_y_offsets:
                                                p1 = target_pt + DB.XYZ(-host_length / 2.0, y_off, 0)
                                                p2 = target_pt + DB.XYZ(host_length / 2.0, y_off, 0)
                                                try:
                                                    line = DB.Line.CreateBound(p1, p2)
                                                    doc.Create.NewFamilyInstance(line, detail_comp_type, doc.ActiveView)
                                                except Exception as draw_e:
                                                    logger.debug("Failed to draw layer line: {}".format(draw_e))
                                                    
                            else:
                                err_msg = "LEGEND_COMPONENT parameter missing or read-only for {}.".format(safe_get_name(elem_type))
                                logger.debug(err_msg)
                                error_logs.append(err_msg)
                                errors += 1
                                doc.Delete(new_comp.Id)
                                
                        except Exception as type_e:
                            # Revert the copied component if it's an unsupported system type that fails the type swap
                            doc.Delete(new_comp.Id)
                            import traceback
                            err_msg = "Failed to set type for {}:\n{}".format(safe_get_name(elem_type), traceback.format_exc())
                            logger.debug(err_msg)
                            error_logs.append(err_msg)
                            errors += 1
                            
                    except Exception as e:
                        # Catch copy failures
                        import traceback
                        err_msg = "Failed to duplicate component for {}:\n{}".format(safe_get_name(elem_type), traceback.format_exc())
                        logger.debug(err_msg)
                        error_logs.append(err_msg)
                        errors += 1
                
                # Increment row index after a chunk so the next chunk (or next family) drops down a row
                row_idx += 1
                
        # Call the tagging function inside the transaction to allow it to update parameters
        if legend_anno_pairs:
            legend_tag(legend_anno_pairs)
                    
    # 8. Finish and notify
    if error_logs:
        print("⚠️ LEGEND GRID ERRORS")
        print("=========================================")
        for log in error_logs:
            print(log)
            print("-----------------------------------------")
            
    if errors > 0:
        forms.alert("Placed {} components. {} could not be placed. Check the pyRevit output window for details.".format(placed_count, errors))
    else:
        forms.alert("Successfully placed {} legend components!".format(placed_count))

if __name__ == '__main__':
    legend_components()
