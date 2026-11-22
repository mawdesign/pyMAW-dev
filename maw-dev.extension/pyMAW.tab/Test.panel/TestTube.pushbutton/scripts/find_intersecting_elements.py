# -*- coding: utf-8 -*-
"""
Find  Intersecting Elements
"""
# -------------- Standard Library / .NET Imports --------------
import clr
clr.AddReference("PresentationCore")
from System.Windows import Clipboard

# ------------------ pyRevit Imports -------------------
from pyrevit import script, forms
from pyrevit import revit
from pyrevit import DB, UI


def get_solid_from_element(element):
    """Helper function to extract Solid geometry with >0 volume from an element."""
    solids = []
    geom_options = DB.Options()
    geom_options.ComputeReferences = False
    geom_options.DetailLevel = DB.ViewDetailLevel.Fine
    
    geom_elem = element.get_Geometry(geom_options)
    if not geom_elem:
        return solids

    for g_obj in geom_elem:
        if isinstance(g_obj, DB.Solid) and g_obj.Volume > 0:
            solids.append(g_obj)
        elif isinstance(g_obj, DB.GeometryInstance):
            inst_geom = g_obj.GetInstanceGeometry()
            for ig_obj in inst_geom:
                if isinstance(ig_obj, DB.Solid) and ig_obj.Volume > 0:
                    solids.append(ig_obj)
    return solids


def find_intersecting_elements():
    doc = revit.doc
    selection = revit.get_selection()
    
    # 1. Validate Selection
    target_types = (DB.Wall, DB.Floor, DB.Ceiling, DB.RoofBase)
    hosts = [el for el in selection.elements if isinstance(el, target_types)]
    if not hosts:
        forms.alert('Please select at least one wall, floor, ceiling, or roof before running this script.', 
                    title='No Host Element Selected', 
                    warn_icon=True)
        return

    all_intersecting_ids = set()

    for host in hosts:
        # --- Method 1: Hosted Inserts ---
        try:
            # Arguments: addRectOpenings, addShadows, addWallSweepsAndReveals, includeEmbeddedWalls
            # The last two are wall-specific, so we dynamically assign them based on element type
            is_wall = isinstance(host, DB.Wall)
            inserts = host.FindInserts(True, False, is_wall, is_wall)
            
            for insert_id in inserts:
                all_intersecting_ids.add(insert_id)
        except Exception as e:
            print("Error retrieving inserts for Element {}: {}".format(host.Id, e))

        # --- Method 2: Joined Elements ---
        try:
            joined_ids = DB.JoinGeometryUtils.GetJoinedElements(doc, host)
            for joined_id in joined_ids:
                all_intersecting_ids.add(joined_id)
        except Exception as e:
            print("Error retrieving joined elements for Element {}: {}".format(host.Id, e))

        # --- Method 3: Intersecting / Cutting Elements ---
        solids = get_solid_from_element(host)
        for solid in solids:
            try:
                solid_filter = DB.ElementIntersectsSolidFilter(solid)
                collector = DB.FilteredElementCollector(doc).WherePasses(solid_filter)
                
                for elem in collector:
                    # Filter out the host itself to avoid self-selection
                    if elem.Id != host.Id:
                        all_intersecting_ids.add(elem.Id)
            except Exception as e:
                print("Error processing solid intersection: {}".format(e))

    # 2. Handle Results
    if not all_intersecting_ids:
        forms.alert('No intersecting or shape-altering elements found for the selected element(s).', 
                    title='Find Intersecting Elements', 
                    warn_icon=False)
        return

    # Format the IDs into a semicolon-separated string for easy pasting
    id_list_str = ";".join([str(eid.IntegerValue) for eid in all_intersecting_ids])
    
    # Generate a small preview string so the user knows what they're copying
    preview_str = id_list_str[:60] + "..." if len(id_list_str) > 60 else id_list_str

    # Prompt user to copy to clipboard (Yes/No dialog)
    copy_to_clipboard = forms.alert(
        "Found {} intersecting/affecting element(s).\n\n"
        "Copy ID list to clipboard (semicolon-separated)?\n\n"
        "Preview:\n{}".format(len(all_intersecting_ids), preview_str),
        title='Find Intersecting Elements',
        yes=True, 
        no=True,
        warn_icon=False
    )

    # 3. Copy to clipboard if user selected 'Yes'
    if copy_to_clipboard:
        try:
            Clipboard.SetText(id_list_str)
        except Exception as e:
            print("Failed to copy to clipboard. Error: {}".format(e))

    # 4. Exit with all elements selected
    # Convert the set of IDs to a list, which pyRevit's set_to() consumes
    selection.set_to(list(all_intersecting_ids))


if __name__ == '__main__':
    find_intersecting_elements()