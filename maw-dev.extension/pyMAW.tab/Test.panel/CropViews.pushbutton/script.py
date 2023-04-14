# Based on a node by Modelical
# www.modelical.com

import clr

#Load Revit API
from pyrevit import revit, DB
from pyrevit import forms
from pyrevit import script

logger = script.get_logger()

doc = __revit__.ActiveUIDocument.Document


def duplicableview(view):
    return view.CanViewBeDuplicated(DB.ViewDuplicateOption.Duplicate)


def dependant_views(vw, scopeboxlist):
    with revit.Transaction('Duplicate selected views'):
        dupop = DB.ViewDuplicateOption.AsDependent
        count = 0
        #for vw in viewlist:
        crop = vw.GetCropRegionShapeManager()
        if crop.ShapeSet:
            crop.RemoveCropRegionShape()
        if crop.Split:
            crop.RemoveSplit()
        for sb in scopeboxlist:
            count += 1
            print(str(count) + " " + vw.Name + " " + sb.Name)
            try:
                newView = revit.doc.GetElement(vw.Duplicate(dupop))
                newView.Name = vw.Name + " " + sb.Name
                sbParam = newView.LookupParameter("Scope Box")
                sbParam.Set(sb.Id)
                #newView.CropBoxActive = True
            except Exception as duplerr:
                logger.error('Error duplicating view "{}_{}" | {}'
                             .format(revit.query.get_name(vw),revit.query.get_name(sb), duplerr))


view = doc.ActiveView
#selected_views = forms.select_views(filterfunc=duplicableview)

selection = revit.get_selection()
##selection_filter = \
##            [x for x in revit.query.get_types_by_class(DB.GraphicsStyle,
##                                                       doc=revit.doc)
##             if x.GraphicsStyleCategory
##             and x.GraphicsStyleCategory.CategoryType != DB.CategoryType.Internal
##             and x.GraphicsStyleCategory.Name == "Scope Boxes"]
##selection.set_to(list(selection_filter))

dependant_views(view, selection)

