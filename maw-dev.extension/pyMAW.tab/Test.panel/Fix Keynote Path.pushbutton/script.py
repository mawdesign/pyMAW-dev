# from pyrevit import forms
from pyrevit import DB, revit
from pyrevit import forms, script
import os
import sys

# get keynote file path
kfile_old = revit.query.get_local_keynote_file(doc=revit.doc)
usrname = os.environ.get('USERNAME')

kfile = u"..\\..\\..\\..\\..\\..\\NZL\\CAD + GRAPHICS\\BIM-Revit-Resources\\Standard Plans\\K\u0101inga Ora\\KO Keynotes.txt"


# pyrevit.script.exit()

# if usrname in kfile:
    # pyrevit.script.exit()



# try:
    # with revit.Transaction("Set Keynote File"):
        # revit.update.set_keynote_file(kfile, doc=revit.doc)
# except Exception as skex:
    # forms.alert(str(skex),
                # expanded="{}::_change_kfile() [transaction]".format(
                                # self.__class__.__name__))

# forms.alert("{0} : {1}\n{2}".format(usrname, kfile_old, kfile), "Check")

doc = revit.doc
view_refs = DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_ReferenceViewer)
for view_ref in view_refs:
    print("\n{1}: {0}".format(view_ref.Name, view_ref.Id))
    # print(str(view_ref.GetOrderedParameters()))
    view = doc.GetElement(view_ref.OwnerViewId)
    print("{1}: {0}".format(view.Name, view.Id))
    for s in view.GetOrderedParameters():
        print("\t{0}: {1}".format(s.Definition.Name, s.AsString()))
    for p in view_ref.GetOrderedParameters():
        print("\t{0}: {1}".format(p.Definition.Name, p.AsString()))

# 1180301: Detail Section - Top Right
# 1180275: Bathroom FF 2BD (IE-39)
	# View Template: None
	# View Name: Bathroom FF 2BD (IE-39)
	# Dependency: Independent
	# Title on Sheet: Bathroom FF 2BD
	# View Scale: None
	# Scale Value 1:: None
	# Detail Level: None
	# Detail Number: IE-39
	# Sheet Number: A5222
	# Sheet Name: Bathroom FF - Lots 6 & 7
	# Rotation on Sheet: None
	# Referencing Sheet: 
	# Referencing Detail: 
	# Visibility/Graphics Overrides: None
	# Discipline: None
	# Kāinga Ora Default Sheet Number: A5223
	# Kāinga Ora Detail Number: IE-39
	# None: None
	# Visual Style: None
	# Target view: None
	# Detail Number: D705
	# Sheet Number: A5402

# # -*- coding: utf-8 -*-
# __title__ = "Get sheet from View"
# __author__ = "Erik Frits"

# #>>>>>>>>>>>>>>>>>>>> IMPORTS
# import clr, os
# from Autodesk.Revit.DB import *

# #>>>>>>>>>>>>>>>>>>>> VARIABLES
# doc = __revit__.ActiveUIDocument.Document
# uidoc = __revit__.ActiveUIDocument
# app = __revit__.Application


# #>>>>>>>>>>>>>>>>>>>> FUNCTIONS
# def create_string_equals_filter(key_parameter, element_value, caseSensitive = True):
  # """Function to create ElementParameterFilter based on FilterStringRule."""
  # f_parameter         = ParameterValueProvider(ElementId(key_parameter))
  # f_parameter_value   = element_value
  # caseSensitive       = True
  # f_rule              = FilterStringRule(f_parameter, FilterStringEquals(),
                        # f_parameter_value, caseSensitive)
  # return ElementParameterFilter(f_rule)

# def get_sheet_from_view(view):
  # #type:(View) -> ViewPlan
  # """Function to get ViewSheet associated with the given ViewPlan"""

  # #>>>>>>>>>> CREATE FILTER 
  # my_filter = create_string_equals_filter(key_parameter=BuiltInParameter.SHEET_NUMBER,
    # element_value=view.get_Parameter(BuiltInParameter.VIEWER_SHEET_NUMBER).AsString() )

  # #>>>>>>>>>> GET SHEET
  # return FilteredElementCollector(doc)
    # .OfCategory(BuiltInCategory.OST_Sheets)
    # .WhereElementIsNotElementType()
    # .WherePasses(my_filter).FirstElement()

# #>>>>>>>>>>>>>>>>>>>> MAIN
# if __name__ == '__main__':

  # #>>>>>>>>>> ACTIVE VIEW
  # active_view = doc.ActiveView
  # sheet     = get_sheet_from_view(active_view)

  # #>>>>>>>>>> PRINT RESULTS
  # if sheet:   print('Sheet Found: {} - {}'.format(sheet.SheetNumber, sheet.Name))
  # else:     print('No sheet associated with the given view: {}'.format(active_view.Name))
