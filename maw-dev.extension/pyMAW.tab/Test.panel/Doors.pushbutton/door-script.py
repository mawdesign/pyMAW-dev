# # -*- coding: utf-8 -*-
# from pyrevit import revit, DB
# from pyrevit import script


# # DB.Family
# document.EditFamily(family)
     # for fam in families:
         # revit.doc.EditFamily(fam)


# collector = FilteredElementCollector( doc ) 
# collector.OfClass( targetType ).ToElements()



# for f in collector: 

        # if f.Name.Equals( targetName ):

                # result = f




# with script.revit.Transaction("Change Door Swing"):
    # parameter = [a for a in doc.FamilyManager.Parameters if a.Definition.Name=="Elev Swing Points to Hinge" ][0]
    # doc.FamilyManager.SetFormula(parameter, "1 = 1")

from pyrevit import script, forms
from pyrevit import revit, DB

class FamilyOption(DB.IFamilyLoadOptions):
    def OnFamilyFound(self, familyInUse, overwriteParameterValues):
        familyInUse.Value = True
        overwriteParameterValues.Value = False
        return True

    def OnSharedFamilyFound(self, sharedFamily, familyInUse, source, overwriteParameterValues):
        familyInUse.Value = True
        source.Value = DB.FamilySource.Family
        overwriteParameterValues.Value = False
        return True

doc = revit.doc

text = ""
count = 0
checklist = []
# famOption = DB.IFamilyLoadOptions([False])

Families = DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol).ToElements()
for fam in Families:
    if fam.FamilyName[:5] == 'Door_':
        fam_typename = DB.Element.Name.__get__(fam)
        elev_param = fam.LookupParameter("Elev Swing Points to Hinge").AsInteger()
        checklist.append((fam.FamilyName, fam_typename, elev_param))
checklist.sort(key=lambda a: a[2])
currfam = ""
currhinge = -1
for i in checklist:
    if i[2] != currhinge:
        text += '\n{}\n'.format(list(["Australia","New Zealand"])[i[2]])
        currhinge = i[2]
    if i[0] != currfam:
        text += '{}\n'.format(i[0])
        currfam = i[0]
    text += '- {}\n'.format(i[1])


# Families = DB.FilteredElementCollector(doc).OfClass(DB.Family)
# for fam in Families:
    # if fam.Name[:5] == 'Door_':
        # famlist.append(fam.Name)
        # for fam_typeid in fam.GetFamilySymbolIds():
            # fam_type = doc.GetElement(fam_typeid)
            # try:
                # # fam_typename = fam_type.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
                # fam_typename = Element.Name.__get__(fam_type)
                # elev_param = "" #fam_type.LookupParameter("Elev Swing Points to Hinge").AsValueString()
            # except:
                # fam_typename = fam_type.Id
                # elev_param = "N/A"
            # text += '{0} swing points to hinge? {1}\n'.format(fam_typename, elev_param) 

# with forms.ProgressBar(title='Door {value} of {max_value}') as pb:
    # for findfam in famlist:
        # Families = DB.FilteredElementCollector(doc).OfClass(DB.Family)
        # for fam in Families:
            # if fam.Name[:5] == 'Door_':
                # # fam is the Family object called 'Door_...', do your worst!
                # try:
                    # elev_param = fam.LookupParameter("Elev Swing Points to Hinge").AsValueString()
                # except:
                    # elev_param = "N/A"
                # text += '{0} swing points to hinge? {2}\n'.format(fam.Name,fam.FamilyCategory.Name, elev_param)
                # #forms.alert(str(fam.Name))
                # # famdoc = doc.EditFamily(fam)
                # # with script.revit.Transaction(name="Change Door Swing", doc=famdoc):
                    # # #Set Door Swing
                    # # parameter = [a for a in famdoc.FamilyManager.Parameters if a.Definition.Name=="Elev Swing Points to Hinge" ]
                    # # if len(parameter):
                        # # famdoc.FamilyManager.SetFormula(parameter[0], "1 = 0")
                # # # load in Project
                # # famdoc.LoadFamily(doc, FamilyOption())
                # # # close Family
                # # famdoc.Close(False)
                # # famdoc.Dispose()
                # count += 1
                # pb._title = fam.Name
                # pb.update_progress(count, len(famlist))
                # break
forms.alert(text)

