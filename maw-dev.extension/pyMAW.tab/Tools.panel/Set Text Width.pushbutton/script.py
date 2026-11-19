# IronPython 2.7 needs this for \uXXXX escapes; ruff format strips u"" prefixes.
from __future__ import unicode_literals

from pyrevit import revit
from pyrevit import forms, script

forms.check_selection(exitscript=True, message="At least one element must be selected.")

selection = revit.get_selection()

default_width = selection[0].Width * 304.8
current_height = selection[0].Height * 304.8
position = selection[0].Coord
position_x = position.X * 304.8
position_y = position.Y * 304.8
position_z = position.Z * 304.8
prompt_text = "Current position = ({x:g}, {y:g}, {z:g})\nCurrent size = {w:g} \u00d7 {h:g} mm\nText Width (mm):".format(
    x=position_x, y=position_y, z=position_z, w=default_width, h=current_height
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
