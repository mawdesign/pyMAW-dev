from pyrevit import revit
from pyrevit import forms, script

forms.check_selection(exitscript=True, message='At least one element must be selected.')

selection = revit.get_selection()

default_width = selection[0].Width * 304.8
current_height = selection[0].Height * 304.8
position = selection[0].Coord
position_X = position.X * 304.8
position_Y = position.Y * 304.8
prompt_text = u"Current position = ({x:g}, {y:g})\nCurrent size = {w:g} \u00d7 {h:g} mm\nText Width (mm):".format(
    x=position_X, y=position_Y, w=default_width, h=current_height
)
width = forms.ask_for_number_slider(
    default=default_width,
    min=5.0,
    max=400.0,
    interval=5.0,
    prompt=prompt_text,
    title="Set Text Width",
)

if width:
    with script.revit.Transaction("Text width"):
        for s in selection:
            s.Width = width / 304.8
