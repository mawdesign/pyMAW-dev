# -*- coding: utf-8 -*-
"""Add Material Library."""
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
from pyrevit import forms

# # ------------------ module imports --------------------
import revitmaterials

WAM_NAME = "** WAM Materials **"
WAM_FILE = (
    "//wam/data/Revit/Staff_Library/Wellington/MAW/Materials/WAM Materials.adsklib"
)


def add_material_library():
    errors = revitmaterials.config_add_material_library(
        WAM_NAME, WAM_FILE, source="both", destination="both"
    )
    if not errors:
        forms.alert("Added library", title="Add Material Library", warn_icon=False)
    else:
        forms.alert(
            "Errors adding library:\n" + errors,
            title="Add Material Library",
            warn_icon=True,
        )


if __name__ == "__main__":
    add_material_library()
