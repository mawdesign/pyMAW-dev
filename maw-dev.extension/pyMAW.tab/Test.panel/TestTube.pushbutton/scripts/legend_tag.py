# -*- coding: utf-8 -*-
"""Tags Generic Annotations with data from nearby Legend Components.

Select Generic Annotations and Legend Components. The script matches each 
annotation to the nearest Legend Component, finds the referenced family type 
in the model, and populates the annotation's parameters based on prefixes:
'TYPE <param>', 'ITEM <param>', 'COUNT', and 'HOST <param>'.
It also supports layered element parsing using 'STRUCTURE' and 'STRUCTURE TEMPLATE'.
"""
# # -------------- Standard Library Imports --------------
import sys
import re

# # ------------------ pyRevit Imports -------------------
from pyrevit import revit, DB, script, forms

# # ----------------- Autodesk Imports -------------------
from Autodesk.Revit.UI.Selection import ISelectionFilter

# Get current document and pyRevit script engine
doc = revit.doc
logger = script.get_logger()

def get_location(elem):
    """Safely gets the center location of an element."""
    if hasattr(elem, "Location") and isinstance(elem.Location, DB.LocationPoint):
        return elem.Location.Point
    # Fallback to bounding box center
    bbox = elem.get_BoundingBox(doc.ActiveView)
    if bbox:
        return (bbox.Min + bbox.Max) / 2.0
    return None

def get_source_values(elements, param_name, storage_type, target_is_type=False):
    """Extracts unique parameter values from elements, matching the target storage type."""
    values = []
    for el in elements:
        p = None
        if target_is_type:
            if hasattr(el, "GetTypeId"):
                type_id = el.GetTypeId()
                if type_id != DB.ElementId.InvalidElementId:
                    elem_type = doc.GetElement(type_id)
                    if elem_type: p = elem_type.LookupParameter(param_name)
            if not p: p = el.LookupParameter(param_name)
        else:
            p = el.LookupParameter(param_name)
            if not p and hasattr(el, "GetTypeId"):
                type_id = el.GetTypeId()
                if type_id != DB.ElementId.InvalidElementId:
                    elem_type = doc.GetElement(type_id)
                    if elem_type: p = elem_type.LookupParameter(param_name)
                    
        if not p: continue
            
        val = None
        if storage_type == DB.StorageType.String:
            val = p.AsString() if p.StorageType == DB.StorageType.String else p.AsValueString()
            if val and val not in values: values.append(val)
        elif storage_type == DB.StorageType.Double:
            val = p.AsDouble()
            if val is not None and val not in values: values.append(val)
        elif storage_type == DB.StorageType.Integer:
            val = p.AsInteger()
            if val is not None and val not in values: values.append(val)
        elif storage_type == DB.StorageType.ElementId:
            val = p.AsElementId()
            if val is not None and val not in values: values.append(val)
                
    return values

def get_param_val_as_string(elem, param_name):
    """Simple helper to strictly pull a parameter as a string (mostly for materials)."""
    if not elem: return ""
    p = elem.LookupParameter(param_name)
    if not p: return ""
    val = p.AsString() if p.StorageType == DB.StorageType.String else p.AsValueString()
    return val if val else ""

def get_host(inst):
    """Attempts to find the host element of a given instance."""
    if hasattr(inst, "Host") and inst.Host: return inst.Host
    if hasattr(inst, "HostId") and inst.HostId != DB.ElementId.InvalidElementId:
        return doc.GetElement(inst.HostId)
    return None

def format_width(width, doc):
    """Safely format Revit internal units (decimal feet) into the project's default length format."""
    units = doc.GetUnits()
    try: # Revit 2022+
        return DB.UnitFormatUtils.Format(units, DB.SpecTypeId.Length, width, False)
    except AttributeError:
        try: # Revit 2021
            return DB.UnitFormatUtils.Format(units, DB.UnitType.UT_Length, width, False, False)
        except Exception: # Hard Fallback
            return str(round(width * 304.8, 1)) + " mm"

def format_structure_template(struct, template, doc):
    """Parses the STRUCTURE TEMPLATE parameter against the layer data of a compound structure."""
    if not struct: return ""
    layers = struct.GetLayers()
    if not layers: return ""
        
    cb1 = struct.GetFirstCoreLayerIndex()
    cb2 = struct.GetLastCoreLayerIndex()
    
    template = template.replace("\\n", "\n").replace("\\t", "\t")
    result_lines = []
    
    for i, layer in enumerate(layers):
        layer_text = template
        
        # Handle conditional brackets [ ] for end of sequence
        if i == len(layers) - 1:
            layer_text = re.sub(r'\[(.*?)\]', "", layer_text)
        else:
            layer_text = re.sub(r'\[(.*?)\]', r"\1", layer_text)
            
        def replace_brace(match):
            inner = match.group(1)
            # Split by colons that are not escaped
            parts = re.split(r'(?<!\\):', inner)
            keyword = parts[0].strip()
            
            def unescape(s): return s.replace("\\:", ":")
            
            if keyword == "Thickness":
                return format_width(layer.Width, doc)
                
            elif keyword == "Material":
                mat = doc.GetElement(layer.MaterialId)
                if len(parts) > 1:
                    param_name = unescape(parts[1]).strip()
                    return get_param_val_as_string(mat, param_name)
                return mat.Name if mat else ""
                
            elif keyword == "Core Boundary":
                is_boundary = (i == cb1 - 1) or (i == cb2)
                t_val = unescape(parts[1]) if len(parts) > 1 else ""
                f_val = unescape(parts[2]) if len(parts) > 2 else ""
                return t_val if is_boundary else f_val
                
            elif keyword == "Wraps":
                is_wraps = layer.LayerCapFlag
                t_val = unescape(parts[1]) if len(parts) > 1 else "Wraps"
                f_val = unescape(parts[2]) if len(parts) > 2 else ""
                return t_val if is_wraps else f_val
                
            elif keyword == "Structural Material":
                is_struct = (struct.StructuralMaterialIndex == i)
                t_val = unescape(parts[1]) if len(parts) > 1 else "Structural Material"
                f_val = unescape(parts[2]) if len(parts) > 2 else ""
                return t_val if is_struct else f_val
                
            elif keyword == "Variable":
                is_var = (struct.VariableLayerIndex == i)
                t_val = unescape(parts[1]) if len(parts) > 1 else "Variable"
                f_val = unescape(parts[2]) if len(parts) > 2 else ""
                return t_val if is_var else f_val
                
            return match.group(0) # Unrecognized

        layer_text = re.sub(r'\{(.+?)\}', replace_brace, layer_text)
        result_lines.append(layer_text)
        
    return "".join(result_lines)

class LegendAndAnnoFilter(ISelectionFilter):
    """Selection filter to restrict picks to Legends and Annotations only."""
    def AllowElement(self, el):
        if not el.Category: return False
        cat_id = el.Category.Id.IntegerValue
        return cat_id in [int(DB.BuiltInCategory.OST_LegendComponents), int(DB.BuiltInCategory.OST_GenericAnnotation)]
    def AllowReference(self, ref, pt):
        return False

def main():
    selection = revit.get_selection().elements
    
    legend_comps = []
    annos = []
    
    def parse_selection(elements):
        l_comps, a_comps = [], []
        for el in elements:
            if not el.Category: continue
            cat_id = el.Category.Id.IntegerValue
            if cat_id == int(DB.BuiltInCategory.OST_LegendComponents): l_comps.append(el)
            elif cat_id == int(DB.BuiltInCategory.OST_GenericAnnotation): a_comps.append(el)
        return l_comps, a_comps

    legend_comps, annos = parse_selection(selection)
            
    if not legend_comps or not annos:
        try:
            sel_refs = revit.pick_rectangle(
                message="Drag a box to select Legend Components and Generic Annotations", 
                pick_filter=LegendAndAnnoFilter(),
            )
            legend_comps, annos = parse_selection(sel_refs)
        except Exception:
            sys.exit() # User canceled pick operation
            
    if not legend_comps or not annos:
        forms.alert("You must select at least one Legend Component AND at least one Generic Annotation.", exitscript=True)
        
    instances_cache = {}
    
    def get_instances(type_elem):
        t_id = type_elem.Id.IntegerValue
        if t_id in instances_cache: return instances_cache[t_id]
        cat_id = type_elem.Category.Id
        all_cat_instances = DB.FilteredElementCollector(doc) \
            .OfCategoryId(cat_id) \
            .WhereElementIsNotElementType() \
            .ToElements()
        matched = [i for i in all_cat_instances if i.GetTypeId().IntegerValue == t_id]
        instances_cache[t_id] = matched
        return matched

    tagged_count = 0
    warnings = []

    with revit.Transaction("Tag Legend Components"):
        for anno in annos:
            anno_loc = get_location(anno)
            if not anno_loc: continue
                
            nearest_lc = None
            min_dist = float('inf')
            for lc in legend_comps:
                lc_loc = get_location(lc)
                if not lc_loc: continue
                dist = anno_loc.DistanceTo(lc_loc)
                if dist < min_dist:
                    min_dist = dist
                    nearest_lc = lc
                    
            if not nearest_lc: continue
                
            lc_param = nearest_lc.get_Parameter(DB.BuiltInParameter.LEGEND_COMPONENT)
            if not lc_param: continue
                
            target_type_id = lc_param.AsElementId()
            if target_type_id == DB.ElementId.InvalidElementId: continue
                
            target_type = doc.GetElement(target_type_id)
            if not target_type: continue
                
            instances = get_instances(target_type)
            
            for param in anno.Parameters:
                if param.IsReadOnly: continue
                p_name = param.Definition.Name
                
                # Rule: STRUCTURE Template Parsing
                if p_name == "STRUCTURE":
                    anno_type = doc.GetElement(anno.GetTypeId())
                    if anno_type:
                        template_param = anno_type.LookupParameter("STRUCTURE TEMPLATE")
                        if template_param and template_param.AsString():
                            struct = target_type.GetCompoundStructure() if hasattr(target_type, "GetCompoundStructure") else None
                            if struct:
                                param.Set(format_structure_template(struct, template_param.AsString(), doc))
                            else:
                                if param.StorageType == DB.StorageType.String: param.Set("")
                    continue
                
                # Rule: COUNT
                if p_name == "COUNT":
                    if param.StorageType == DB.StorageType.Integer: param.Set(len(instances))
                    elif param.StorageType == DB.StorageType.Double: param.Set(float(len(instances)))
                    else: param.Set(str(len(instances)))
                    continue
                    
                target_param = ""
                sources = []
                source_type_label = ""
                target_is_type = False
                is_handled = False
                
                # Prefix Rules Check
                if p_name.startswith("TYPE "):
                    target_param, sources, source_type_label, target_is_type, is_handled = p_name[5:], [target_type], "TYPE", True, True
                elif p_name.startswith("ITEM TYPE "):
                    target_param, sources, source_type_label, target_is_type, is_handled = p_name[10:], instances, "ITEM TYPE", True, True
                elif p_name.startswith("ITEM "):
                    target_param, sources, source_type_label, target_is_type, is_handled = p_name[5:], instances, "ITEM", False, True
                elif p_name.startswith("HOST TYPE "):
                    sources = [h for h in (get_host(i) for i in instances) if h]
                    target_param, source_type_label, target_is_type, is_handled = p_name[10:], "HOST TYPE", True, True
                elif p_name.startswith("HOST "):
                    sources = [h for h in (get_host(i) for i in instances) if h]
                    target_param, source_type_label, target_is_type, is_handled = p_name[5:], "HOST", False, True
                    
                # Extract, Convert, and Set
                if is_handled and target_param:
                    vals = get_source_values(sources, target_param, param.StorageType, target_is_type) if sources else []
                    if vals:
                        if param.StorageType == DB.StorageType.String:
                            param.Set(", ".join(sorted([str(v) for v in vals])))
                        else:
                            if len(vals) > 1:
                                t_name = target_type.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
                                t_name_str = t_name.AsString() if t_name else getattr(target_type, "Name", "Unknown")
                                warnings.append("- [{}] {}: '{}' found {} numeric variations. First value applied.".format(
                                    t_name_str, source_type_label, target_param, len(vals)
                                ))
                            param.Set(vals[0])
                    else:
                        # Blank out the value cleanly if the requested parameter is empty/doesn't exist
                        if param.StorageType == DB.StorageType.String:
                            param.Set("")

            tagged_count += 1
            
    if warnings:
        unique_warns = []
        for w in warnings:
            if w not in unique_warns: unique_warns.append(w)
        forms.alert("Processed {} annotations.\n\nWARNINGS (Mismatched Numeric Values):\n{}".format(tagged_count, "\n".join(unique_warns)))
    else:
        forms.toast("Successfully processed {} Generic Annotations!".format(tagged_count), title="Legend Tagger")

if __name__ == '__main__':
    main()