# -*- coding: utf-8 -*-
"""
Layout Walls In Plan
Draws all basic wall types into the active floor plan in a 1m x 1m grid.
"""
# # -------------- Standard Library Imports --------------
# import os
# import sys
# import clr
import math

# # ------------------ pyRevit Imports -------------------
from pyrevit import script, forms
from pyrevit import revit
from pyrevit import DB


logger = script.get_logger()

def mm_to_ft(mm):
    return mm / 304.8

def layout_walls_in_plan():
    doc = revit.doc
    view = doc.ActiveView
    
    # 1. Validate active view is a Floor Plan
    if view.ViewType != DB.ViewType.FloorPlan:
        forms.alert("Please run this script from a Floor Plan view.", title="Invalid View", warn_icon=True)
        return
        
    level = view.GenLevel
    if not level:
        forms.alert("Active view does not have an associated Level.", title="Error", warn_icon=True)
        return

    # 2. Collect all Basic Wall Types
    wall_types = DB.FilteredElementCollector(doc).OfClass(DB.WallType).WhereElementIsElementType().ToElements()
    basic_wall_types = [wt for wt in wall_types if wt.Kind == DB.WallKind.Basic]
    
    if not basic_wall_types:
        forms.alert("No basic wall types found in the project.", title="Error", warn_icon=True)
        return

    # Sort wall types alphabetically for a neat layout
    basic_wall_types.sort(key=lambda x: DB.Element.Name.__get__(x))

    # 3. Calculate Grid Dimensions
    total_walls = len(basic_wall_types)
    cols = int(math.ceil(math.sqrt(total_walls)))
    
    spacing_ft = mm_to_ft(1000.0) # 1m spacing
    wall_len_ft = mm_to_ft(900.0) # 900mm length
    offset_x_ft = (spacing_ft - wall_len_ft) / 2.0 # Center the 900mm wall in the 1000mm grid column
    wall_height_ft = mm_to_ft(2500.0) # 2m default height for representation

    walls_created = 0

    with revit.Transaction("Layout Wall Types Grid"):
        for i, wt in enumerate(basic_wall_types):
            col = i % cols
            row = i // cols
            
            # 4. Calculate coordinates
            # Grid origin is (0,0). Rows step down (-Y) to match reading order.
            cell_y = -row * spacing_ft
            
            # Start and End points (Drawing Left to Right)
            pt1 = DB.XYZ(col * spacing_ft + offset_x_ft, cell_y - wt.Width/2.0, 0)
            pt2 = DB.XYZ(pt1.X + wall_len_ft, cell_y - wt.Width/2.0, 0)
            
            # Placed right to left to make exterior side down
            line = DB.Line.CreateBound(pt2, pt1)
            
            try:
                # 5. Create Wall
                wall = DB.Wall.Create(doc, line, wt.Id, level.Id, wall_height_ft, 0.0, False, False)
                
                # 6. Align Internal Face & Set Exterior Direction
                # Change location line to Finish Face: Interior (BuiltIn Enum 5)
                loc_param = wall.get_Parameter(DB.BuiltInParameter.WALL_KEY_REF_PARAM)
                if loc_param:
                    loc_param.Set(5)
                    
                # Disallow joins
                DB.WallUtils.DisallowWallJoinAtEnd(wall, 0)
                DB.WallUtils.DisallowWallJoinAtEnd(wall, 1)
                
                # Re-apply the curve so the wall shifts to put the Internal face exactly on the line
                wall.Location.Curve = line
                    
                # 7. Place Tag in the center of the 1m grid cell
                center_pt = DB.XYZ(col * spacing_ft + (spacing_ft / 2.0), cell_y - (spacing_ft / 2.0), 0)
                
                # Revit requires a reference to tag
                wall_ref = DB.Reference(wall)
                DB.IndependentTag.Create(
                    doc, 
                    view.Id, 
                    wall_ref, 
                    False, # addLeader
                    DB.TagMode.TM_ADDBY_CATEGORY, 
                    DB.TagOrientation.Horizontal, 
                    center_pt
                )
                
                walls_created += 1
                
            except Exception as e:
                logger.error("Failed to layout wall type {}: {}".format(DB.Element.Name.__get__(wt), e))

    forms.alert("Successfully laid out {} wall types.".format(walls_created), title="Complete")

if __name__ == '__main__':
    layout_walls_in_plan()
