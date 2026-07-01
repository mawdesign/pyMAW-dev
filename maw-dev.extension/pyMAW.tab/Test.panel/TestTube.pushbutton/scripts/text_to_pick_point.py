# -*- coding: utf-8 -*-
"""
Text To Pick Point
Moves selected text notes to a user-picked location.
"""
# # -------------- Standard Library Imports --------------
# import os
# import sys
# import clr
# import wpf

# # -------------------- .NET Imports --------------------
from System.Collections.Generic import List
from Autodesk.Revit.Exceptions import OperationCanceledException

# # ------------------ pyRevit Imports -------------------
from pyrevit import script, forms
from pyrevit import revit
from pyrevit import DB, UI


def text_to_pick_point():
    doc = revit.doc
    uidoc = revit.uidoc
    
    # 1. Get the current user selection
    selection = revit.get_selection()
    
    # 2. Filter the selection to only include Text Notes
    text_notes = [el for el in selection if isinstance(el, DB.TextNote)]
    
    # 3. Check if any text notes were selected
    if not text_notes:
        forms.alert(
            'Please select at least one Text Note before running this tool.', 
            title='Text To Pick Point', 
            warn_icon=True
        )
        return

    # 4. Prompt the user to pick a destination point
    try:
        dest_point = uidoc.Selection.PickPoint("Pick a destination point for the selected text")
    except OperationCanceledException:
        # Handles the scenario where the user presses 'Esc' to cancel
        return
    except Exception as e:
        print("Error picking point: {}".format(e))
        return

    # 5. Calculate the movement translation vector
    # We use the position (Coord) of the first selected text note as our base point
    base_point = text_notes[0].Coord
    
    # Calculate vector from base point to destination point. 
    # Z difference is forced to 0 to keep text strictly on its current view plane.
    translation_vector = DB.XYZ(
        dest_point.X - base_point.X,
        dest_point.Y - base_point.Y,
        0 
    )
    
    # 6. Collect Element IDs into a .NET List for the MoveElements method
    ids_to_move = List[DB.ElementId]()
    for tn in text_notes:
        ids_to_move.Add(tn.Id)
        
    # 7. Execute the move within a Revit Transaction
    with revit.Transaction("Move Text To Pick Point"):
        DB.ElementTransformUtils.MoveElements(doc, ids_to_move, translation_vector)


if __name__ == '__main__':
    text_to_pick_point()