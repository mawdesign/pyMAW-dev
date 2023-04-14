from pyrevit import forms, UI
from pyrevit import EXEC_PARAMS
from System import EventHandler, Uri
from Autodesk.Revit.UI.Events import DialogBoxShowingEventArgs

forms.alert("Loaded"+str(__revit__.DialogBoxShowing))

def maw_dialog_open(sender, event):
    forms.alert(str(event.DialogId))
    # try:
        # if event.DialogId == 'TaskDialog_Really_Print_Or_Export_Temp_View_Modes':
            # event.OverrideResult(1002) 
            # # 1001 call TaskDialogResult.CommandLink1
            # # 1002 call TaskDialogResult.CommandLink2
            # # int(TaskDialogResult.CommandLink2) to check the result
    # except Exception as e:
        # pass #print(e) # uncomment this to debug 
        
# __uiControlledApplication__.DialogBoxShowing += on_dialog_open
# __revit__.DialogBoxShowing += maw_dialog_open
__revit__.DialogBoxShowing += EventHandler[DialogBoxShowingEventArgs](maw_dialog_open)

# from System import EventHandler, Uri
# from Autodesk.Revit.UI.Events import ViewActivatedEventArgs, ViewActivatingEventArgs

# def event_handler_function(sender, args):
   # do the even stuff here

# I'm using ViewActivating event here as example.
# The handler function will be executed every time a Revit view is activated:
# __revit__.ViewActivating += EventHandler[ViewActivatingEventArgs](event_handler_function)

# def on_opened(sender, args):
    # if doc.IsWorkshared:
        # pass

# uiapp.Application.DocumentOpened += EventHandler[Events.DocumentOpenedEventArgs](on_opened)