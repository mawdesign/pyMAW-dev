# -*- coding: utf-8 -*-
"""
Test Formatter
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


def test_formatter_script():
    forms.alert('This is the test_formatter_script script', title='Test Formatter', warn_icon=False)


if __name__ == '__main__':
    test_formatter_script()
