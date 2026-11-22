# -*- coding: utf-8 -*-
"""
Curved Insulation
Translates C# logic to pyRevit Python.
Credit: mikaeldeity/CurvedInsulation (Mikael Santrolli) - MIT License
"""
# # -------------- Standard Library Imports --------------
import math

# # ------------------ pyRevit Imports -------------------
from pyrevit import forms
from pyrevit import revit
from pyrevit import DB, UI

# # ----------------- Autodesk Imports -------------------
from Autodesk.Revit.Exceptions import OperationCanceledException


class SelectionFilterCurve(UI.Selection.ISelectionFilter):
    def AllowElement(self, elem):
        if isinstance(elem, DB.DetailCurve):
            if elem.CurveElementType == DB.CurveElementType.DetailCurve:
                return True
        return False

    def AllowReference(self, reference, position):
        return False


class SelectionFilterAnnotation(UI.Selection.ISelectionFilter):
    def AllowElement(self, elem):
        if isinstance(elem, DB.DetailCurve):
            if elem.CurveElementType == DB.CurveElementType.Insulation:
                return True
        return False

    def AllowReference(self, reference, position):
        return False


def split_arc(curve, width, ratio):
    lines = []
    
    # Create offset arc
    offset_arc = curve.CreateOffset(width / 2.0, curve.Normal)
    
    radius = offset_arc.Radius
    chord = 1.1 * (width / ratio)
    
    angle = 2.0 * math.asin(chord / (2.0 * radius))
    arc_angle = offset_arc.Length / offset_arc.Radius
    
    divisions = int(math.ceil(arc_angle / angle))
    
    points = []
    
    # Calculate points along the offset arc
    for i in range(divisions + 1):
        param = i * (1.0 / divisions)
        point = offset_arc.Evaluate(param, True)
        points.append(point)
        
    # Generate the split lines and offset them back
    for i in range(len(points) - 1):
        line = DB.Line.CreateBound(points[i], points[i + 1])
        new_line = line.CreateOffset(width / 2.0, curve.Normal.Negate())
        lines.append(new_line)
        
    return lines


def curved_insulation():
    doc = revit.doc
    uidoc = revit.uidoc

    # Verify we are in a Project Environment
    if doc.IsFamilyDocument:
        forms.alert('This tool only works in Project environment.', title='Error')
        return

    # Attempt user selection
    try:
        ref_insulation = uidoc.Selection.PickObject(
            UI.Selection.ObjectType.Element, 
            SelectionFilterAnnotation(), 
            "Select Insulation Batting"
        )
        
        ref_curve = uidoc.Selection.PickObject(
            UI.Selection.ObjectType.Element, 
            SelectionFilterCurve(), 
            "Select Curve"
        )
    except OperationCanceledException:
        # User pressed escape during selection
        return

    # Fetch elements from selection
    insulation_detail_curve = doc.GetElement(ref_insulation)
    detail_curve = doc.GetElement(ref_curve)

    # Extract BuiltIn parameters for width and ratio
    width = insulation_detail_curve.get_Parameter(DB.BuiltInParameter.INSULATION_WIDTH).AsDouble()
    ratio = insulation_detail_curve.get_Parameter(DB.BuiltInParameter.INSULATION_SCALE).AsDouble()

    curve = detail_curve.GeometryCurve                

    # Start Transaction
    with revit.Transaction("Draw Curved Insulation"):
        if isinstance(curve, DB.Arc) and curve.IsBound:
            lines = split_arc(curve, width, ratio)
            
            for line in lines:
                # Copy the reference insulation line and apply the new geometry
                copied_element_ids = DB.ElementTransformUtils.CopyElement(doc, insulation_detail_curve.Id, DB.XYZ())
                new_curve = doc.GetElement(copied_element_ids[0])
                new_curve.GeometryCurve = line
                
        elif isinstance(curve, DB.Line) and curve.IsBound:
            # Direct copy for lines
            copied_element_ids = DB.ElementTransformUtils.CopyElement(doc, insulation_detail_curve.Id, DB.XYZ())
            new_curve = doc.GetElement(copied_element_ids[0])
            new_curve.GeometryCurve = curve


if __name__ == '__main__':
    curved_insulation()