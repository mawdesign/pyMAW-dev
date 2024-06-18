# -*- coding: utf-8 -*-
__context__ = 'zerodoc'
__doc__ = 'This test script is currently trialling options for removing or preventing duplicates of families when inserting views'

# import os.path as op
from pyrevit import revit, DB
from pyrevit import forms
from pyrevit import script

dump = ""

## get from and to documents
pyrevit.forms.select_dest_docs()

## get list of views

## get all families used in selected views

## copy families from source to destination documents
# by opening families and then load into project and close



output = script.get_output()

output.set_height(600)
output.set_title('Current script dump:')

