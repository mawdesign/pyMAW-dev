# -*- coding: utf-8 -*-
"""
Parameter Tools
"""
# # -------------- Standard Library Imports --------------
# import os
# import sys
# import clr
# import wpf

# # -------------------- .NET Imports --------------------
# clr.AddReference("System.Drawing")
# clr.AddReference("PresentationFramework")
# clr.AddReference("PresentationCore")
# clr.AddReference("WindowsBase")

# # ------------------ pyRevit Imports -------------------
from pyrevit import script, forms
from pyrevit import revit
from pyrevit import DB, UI


def parameter_tools_script():
    forms.alert('This is the parameter_tools_script script', title='Parameter Tools', warn_icon=False)


if __name__ == '__main__':
    parameter_tools_script()
