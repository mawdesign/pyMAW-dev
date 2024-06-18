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
viewtypes = (DB.ViewDrafting,)
familytypes = ("Generic Annotations", "Detail Items", "Detail Item Tags", "Keynote Tags")


# Select document to import from
open_docs = [d for d in revit.docs if not (d.IsLinked or d.IsFamilyDocument)]
open_docs.remove(currdoc)
if len(open_docs) > 1:
    sourcedoc = forms.select_open_docs(title='Select Document to import from', multiple=False, check_more_than_one=True, filterfunc=lambda d: not d.IsFamilyDocument)
else:
    sourcedoc = open_docs[0]
forms.alert_ifnot(sourcedoc, "No document selected", exitscript = True)


# Select sheets or views to import
choice = forms.ask_for_one_item(['Sheets', 'Views'], default = 'Sheets', title = sourcedoc.Title, prompt='Import whole sheets or specific views?')
if choice == 'Sheets':
    sheets = forms.select_sheets(doc = sourcedoc, multiple = True)#, use_selection = True)
    views = []
    for s in sheets:
        views = list(set(views + [sourcedoc.GetElement(x) for x in s.GetAllPlacedViews()]))
if choice == 'Views':
    views = forms.select_views(doc = sourcedoc, multiple = True, filterfunc=lambda x: isinstance(x, viewtypes))
forms.alert_ifnot(len(views) > 0, "No views selected (perhaps empty sheets?)", exitscript = True)
    

# Get all families in current document
currdoc_families = []
currdoc_families_names = []
for f in DB.FilteredElementCollector(currdoc).OfClass(DB.Family).ToElements():
    if f.FamilyCategory.Name in familytypes:
        currdoc_families.append(f)
        currdoc_families_names.append(f.Name)


# Get all families in selected views
view_elements = []
view_element_ids = []
for v in views:
    for e in DB.FilteredElementCollector(sourcedoc, v.Id).WhereElementIsNotElementType().ToElements():
        if e.Category and e.Category.Name in familytypes:
            try:
                f = e.Symbol.Family
                if f.Id not in view_element_ids \
                        and f.Name in currdoc_families_names: # filter out new families
                    view_element_ids.append(f.Id)
                    view_elements.append(f)
            except Exception as err:
                continue


# Open each family and load into current, override parameters
for f in view_elements:
    source_family = sourcedoc.EditFamily(f)
    reloaded_family = source_family.LoadFamily(currdoc, FamilyLoadOptions())
    source_family.Close(False)


# Import sheets/views
# cp_options = DB.CopyPasteOptions()
# cp_options.SetDuplicateTypeNamesHandler(CopyUseDestination())

# if choice == 'Sheets':
    # with revit.Transaction("Copy Sheet", doc = currdoc):
        # # for s in sheets:
            # try:
                # # revit.create.copy_elements([s.Id], sourcedoc, currdoc)
                # # DB.ElementTransformUtils.CopyElements(sourcedoc, List[DB.ElementId]([s.Id]), currdoc, None, cp_options)
                # revit.UI.UIDocument(sourcedoc)
                # revit.uidoc.Selection.SetElementIds(List[DB.ElementId]([s.Id for s in sheets]))
                # revit.uidoc.RefreshActiveView()
                # # text += "Sheet {} worked\r\n".format(sheet[0].Name)
            # except Exception as create_err:
                # text += "Sheet {} {} failed with error {}\r\n".format(s.Name, s.Id, create_err)

text = "Now copy and paste these sheets:\r\n"
for e in sheets:
    text += "{} - {}\r\n".format(e.SheetNumber, e.Name)
    # try:
        # text += "[{}] {} ({})\r\n".format(e.Id, e.Name, e.Category.Name)
    # except Exception as err:
        # text += "[{}] {} ({})\r\n".format(e.Id, e.Name, e.FamilyCategory.Name)
forms.alert(text)


# from pyrevit.revit import create
# from pyrevit.revit import Transaction

# with Transaction("transaction name", doc):
    # create.copy_elements(element_ids, src_doc, dest_doc)




# https://sites.google.com/site/revitapi123/postablecommand-example

# CopyToClipboard
# CutToClipboard
# PasteFromClipboard
# from Autodesk.Revit.UI import RevitCommandId
# CmndID = RevitCommandId.LookupCommandId('ID_SPLIT_SURFACE')
# CmId = CmndID.Id
# uiapp.PostCommand(CmndID)

# import clr
# import System
# from System.Threading import Thread, ThreadStart
# clr.AddReference("System.Windows.Forms")

# def SetText(text):
    # def thread_proc():
        # System.Windows.Forms.Clipboard.SetText(text)
    # t = Thread(ThreadStart(thread_proc))
    # t.ApartmentState = System.Threading.ApartmentState.STA
    # t.Start()

# try:
	# if IN[0] != "" and IN[0] != None:
		# SetText(IN[0])
		# OUT = IN[0]
	# else:
		# OUT = "Invalid input: Empty string or Null value!"
# except:
	# OUT = 'Data could not be copied to clipboard!'