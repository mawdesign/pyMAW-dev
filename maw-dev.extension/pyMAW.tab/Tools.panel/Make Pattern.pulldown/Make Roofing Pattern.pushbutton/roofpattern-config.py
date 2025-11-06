# -*- coding: utf-8 -*-
"""
This script launches the shared configuration editor
for the 'Roofing Patterns' section.
"""

from pyrevit import script
import pattern_config  # Imports from the 'lib' folder
import os

# Get the path of THIS script
PATH_SCRIPT = script.get_script_path()

# Call the edit function from the library
pattern_config.edit_config(PATH_SCRIPT, "Roofing Patterns")