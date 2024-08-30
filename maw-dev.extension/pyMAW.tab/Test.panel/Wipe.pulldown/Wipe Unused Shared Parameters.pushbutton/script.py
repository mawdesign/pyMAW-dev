from pyrevit import forms
from pyrevit import revit, DB


forms.alert('Ka - boom\n(doesn\'t actually do anything yet)')

    # # ask user for wipe actions
    # return_options = \
        # forms.SelectFromList.show(
            # [ViewTemplateToPurge(revit.doc.GetElement(DB.ElementId(x)))
             # for x in unusedvtemp],
            # title='Select View Templates to Purge',
            # width=500,
            # button_name='Purge View Templates',
            # multiselect=True
            # )

