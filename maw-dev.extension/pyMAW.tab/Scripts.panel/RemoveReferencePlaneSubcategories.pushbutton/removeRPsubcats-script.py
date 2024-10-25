from pyrevit import revit, DB
from pyrevit import forms
from pyrevit.revit import query
from pyrevit.framework import List
# from pyrevit.revit import Transaction
# from pyrevit.revit import create
# from pyrevit import script
# from rpws import RevitServer
# import os


## Implementation of family load options - always override existing family
class FamilyLoadOptions(DB.IFamilyLoadOptions):
    def     OnFamilyFound(self, familyInUse, overwriteParameterValues):
            overwriteParameterValues = True
            return True

    def     OnSharedFamilyFound(self, sharedFamily, familyInUse, source, overwriteParameterValues):
            source = FamilySource.Family
            overwriteParameterValues = True
            return True

class CopyUseDestination(DB.IDuplicateTypeNamesHandler):
    # Handle copy and paste errors.

    def OnDuplicateTypeNamesFound(self, args):
        # Use destination model types if duplicate.
        return DB.DuplicateTypeAction.UseDestinationTypes

currdoc = revit.doc
familytypes = ("Doors")
ignorelist = ["<None>", "Secondary Planes"]
text = ""

# Get all families in current document
currdoc_families = []
currdoc_families_names = []
for f in DB.FilteredElementCollector(currdoc).OfClass(DB.Family).ToElements():
    if f.FamilyCategory.Name in familytypes:
        subcats = {}
        currdoc_families.append(f)
        currdoc_families_names.append(f.Name)
        text += f.Name + "\r\n"
        familydoc = currdoc.EditFamily(f)
        # Transaction
        for rp in DB.FilteredElementCollector(familydoc).OfClass(DB.ReferencePlane).ToElements():
            subcatname = rp.LookupParameter("Subcategory").AsValueString()
            if subcatname in ignorelist:
                continue
            elif subcatname in subcats:
                subcats[subcatname] += 1
            else:
                subcats[subcatname] = 1
            subcatcount = subcats[subcatname]
            # rpname = rp.LookupParameter("Name")
            rpname = rp.get_Parameter(DB.BuiltInParameter.DATUM_TEXT)
            if rpname.AsString():
                rpnewname = "{} {} {}".format(rpname.AsString(), subcatname, subcatcount)
            else:
                rpnewname = "{} {}".format(subcatname, subcatcount)
            if rpname.Set(rpnewname):
                text += "- {}\r\n".format(rpnewname)
            else:
                text += "X {} failed\r\n".format(rpnewname)
        # Transaction Close
        reloaded_family = familydoc.LoadFamily(currdoc, FamilyLoadOptions())
        familydoc.Close(False)



# Open each family and load into current, override parameters
# for f in view_elements:
    # reloaded_family = source_family.LoadFamily(currdoc, FamilyLoadOptions())
    # source_family.Close(False)



# text = str(subcats)
# for e in sheets:
    # text += "{} - {}\r\n".format(e.SheetNumber, e.Name)
    # try:
        # text += "[{}] {} ({})\r\n".format(e.Id, e.Name, e.Category.Name)
    # except Exception as err:
        # text += "[{}] {} ({})\r\n".format(e.Id, e.Name, e.FamilyCategory.Name)
forms.alert(text)

