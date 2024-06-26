# -*- coding: UTF-8 -*-
import os
from pyrevit import framework
from pyrevit import script
from pyrevit.framework import AppDomain
import Autodesk
from Autodesk.Revit.UI import *
from Autodesk.Revit.DB import *
import System
from System import Guid

location = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))

UPDATER_TEST = 'create_updater'
class MyUpdater(IUpdater):

    def __init__(self, addinId):
        '''type UpdaterId, mix of Addin ID and updater GUID
           choose a different GUID for each updater !!! '''
        self.updaterID = UpdaterId(addinId,
            Guid("CBCBF6B2-4C06-42d4-97C1-D1B4EB593170"))

    def GetUpdaterId(self):
        return self.updaterID

    def GetUpdaterName(self):
        return 'MyUpdater'

    def GetAdditionalInformation(self):
        return 'MyUpdater (explanation, details, warnings)'

    def GetChangePriority(self):
        return ChangePriority.Structure

    def Execute(self, updaterData):
        up_doc = updaterData.GetDocument()   #document
        uidoc = __revit__.ActiveUIDocument
        elems = updaterData.GetAddedElementIds()
        #elems = updaterData.GetModifiedElementIds()
        # use a subtransaction in the current opened transaction
        if script.get_envvar(UPDATER_TEST):

            t = SubTransaction(up_doc)
            t.Start()
            try:
                if elems:
                    for h in elems:
                        id = up_doc.GetElement(h)
                        TaskDialog.Show('Element', 'Wall Changed '+str(h)+h)
                t.Commit()
            except:
                t.RollBack()

app = __revit__.Application
def __selfinit__(script_cmp, ui_button_cmp, __rvt__):
    my_updater = MyUpdater(app.ActiveAddInId)
    if UpdaterRegistry.IsUpdaterRegistered(my_updater.GetUpdaterId()):
        UpdaterRegistry.UnregisterUpdater(my_updater.GetUpdaterId())
    UpdaterRegistry.RegisterUpdater(my_updater)
    filter = ElementCategoryFilter(BuiltInCategory.OST_Walls)
    UpdaterRegistry.AddTrigger(my_updater.GetUpdaterId(), filter,
        #Element.GetChangeTypeGeometry())
        Element.GetChangeTypeElementAddition())

def togglestate():
	new_state = not script.get_envvar(UPDATER_TEST)
	script.set_envvar(UPDATER_TEST, new_state)
	script.toggle_icon(new_state)

if __name__ == '__main__':
    togglestate()