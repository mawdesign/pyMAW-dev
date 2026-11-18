# -*- coding: UTF-8 -*-
import os
from pyrevit import DB, UI, script
from System import Guid

location = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))

UPDATER_TEST = "create_updater"


class MyUpdater(DB.IUpdater):
    def __init__(self, addinId):
        """Type UpdaterId, mix of Addin ID and updater GUID choose a different GUID for each updater !!!"""
        self.updaterID = DB.UpdaterId(
            addinId, Guid("CBCBF6B2-4C06-42d4-97C1-D1B4EB593170")
        )

    def GetUpdaterId(self):
        return self.updaterID

    def GetUpdaterName(self):
        return "MyUpdater"

    def GetAdditionalInformation(self):
        return "MyUpdater (explanation, details, warnings)"

    def GetChangePriority(self):
        return DB.ChangePriority.Structure

    def Execute(self, updaterData):
        up_doc = updaterData.GetDocument()  # document
        elems = updaterData.GetAddedElementIds()
        # elems = updaterData.GetModifiedElementIds()
        # use a subtransaction in the current opened transaction
        if script.get_envvar(UPDATER_TEST):
            t = DB.SubTransaction(up_doc)
            t.Start()
            try:
                if elems:
                    for h in elems:
                        up_doc.GetElement(h)
                        UI.TaskDialog.Show("Element", "Wall Changed " + str(h) + h)
                t.Commit()
            except:
                t.RollBack()


app = __revit__.Application


def __selfinit__(script_cmp, ui_button_cmp, __rvt__):  # noqa: N807
    my_updater = MyUpdater(app.ActiveAddInId)
    if DB.UpdaterRegistry.IsUpdaterRegistered(my_updater.GetUpdaterId()):
        DB.UpdaterRegistry.UnregisterUpdater(my_updater.GetUpdaterId())
    DB.UpdaterRegistry.RegisterUpdater(my_updater)
    filter = DB.ElementCategoryFilter(DB.BuiltInCategory.OST_Walls)
    DB.UpdaterRegistry.AddTrigger(
        my_updater.GetUpdaterId(),
        filter,
        # Element.GetChangeTypeGeometry())
        DB.Element.GetChangeTypeElementAddition(),
    )


def togglestate():
    new_state = not script.get_envvar(UPDATER_TEST)
    script.set_envvar(UPDATER_TEST, new_state)
    script.toggle_icon(new_state)


if __name__ == "__main__":
    togglestate()
