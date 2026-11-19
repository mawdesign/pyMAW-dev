# -*- coding: utf-8 -*-
"""Add Material Library.

Adds material libraries (.adsklib) to the material and asset browsers. Libraries
configured by an admin in lib/material_settings.json are offered as a list;
any other library can be added by name and browsing for the file.
"""

# # -------------- Standard Library Imports --------------
import os

# # ------------------ pyRevit Imports -------------------
from pyrevit import forms
from pyrevit import script

# # ------------------ module imports --------------------
import revitmaterialconfig

OTHER_LIBRARY = {"name": "Other library (browse for file)...", "file": ""}


class LibraryOption(forms.TemplateListItem):
    """Library list item showing its name and file."""

    @property
    def name(self):
        if self.item is OTHER_LIBRARY:
            return self.item["name"]
        return "{}  [{}]".format(self.item["name"], self.item["file"])


def pick_other_library():
    """Ask for a library file and name. Returns {"name", "file"} or None."""
    file_path = forms.pick_file(file_ext="adsklib", title="Select Material Library")
    if not file_path:
        return None

    default_name = os.path.splitext(os.path.basename(file_path))[0]
    name = forms.ask_for_string(
        default=default_name,
        prompt="Display name for the library:",
        title="Add Material Library",
    )
    if not name:
        return None

    return {"name": name.strip(), "file": os.path.normpath(file_path)}


def select_libraries():
    """Returns the list of libraries the user wants to add, or [] if cancelled."""
    options = [LibraryOption(lib) for lib in revitmaterialconfig.get_company_libraries()]
    options.append(LibraryOption(OTHER_LIBRARY))

    selected = forms.SelectFromList.show(
        options,
        multiselect=True,
        title="Add Material Libraries",
        button_name="Add",
    )
    if not selected:
        return []

    libraries = []
    for item in selected:
        if item is OTHER_LIBRARY:
            other = pick_other_library()
            if other:
                libraries.append(other)
        else:
            libraries.append(item)
    return libraries


def add_material_library():
    libraries = select_libraries()
    if not libraries:
        script.exit()

    # Add in reverse so the first selected ends up first in the browser
    errors = []
    for lib in reversed(libraries):
        error = revitmaterialconfig.config_add_material_library(
            lib["name"], lib["file"], source="both", destination="both"
        )
        if error:
            errors.append("{}: {}".format(lib["name"], error))

    if not errors:
        forms.alert(
            "Added {} librar{}".format(len(libraries), "y" if len(libraries) == 1 else "ies"),
            title="Add Material Library",
        )
    else:
        forms.alert(
            "Errors adding library:\n" + "\n".join(errors),
            title="Add Material Library",
            warn_icon=True,
        )


if __name__ == "__main__":
    add_material_library()
