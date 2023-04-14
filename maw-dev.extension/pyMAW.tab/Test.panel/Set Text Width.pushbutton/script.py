from pyrevit import revit
from pyrevit import forms, script

forms.check_selection(exitscript=True, message='At least one element must be selected.')

selection = revit.get_selection()

default_width = selection[0].Width * 304.8
current_height = selection[0].Height * 304.8
width = forms.ask_for_number_slider(default = default_width, min = 1.0, max = 400.0, prompt = "Current size = " + str(default_width) + u" \u00d7 " + str(current_height) + " mm\nText Width (mm):", title = "Set Text Width")

if width:
    with script.revit.Transaction("Text width"):
        for s in selection:
            s.Width = width / 304.8
