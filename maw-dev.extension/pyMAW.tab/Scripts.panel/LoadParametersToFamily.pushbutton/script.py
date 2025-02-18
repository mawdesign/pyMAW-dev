# -*- coding: UTF-8 -*-
from pyrevit import revit
from pyrevit import DB, UI
from pyrevit import forms
from pyrevit.revit import Transaction
from pyrevit import script
from pyrevit import EXEC_PARAMS
import os, sys
import xlrd
import re


# Test if family already contains the parameter
def familyHasParameter(currentParams, parameterName):
    for k in range(len(currentParams)):
        try:
            if currentParams[k].Definition.Name == parameterName:
                return currentParams[k]
        except:
            continue
    return False


# Set parameter according to type
def setParam(param, value, f=revit.doc.FamilyManager):
    # Use Revit in-built unit conversion if data looks to be entered as number with units
    if type(value) is str and re.match(r"^[-.0-9]+[^-.0-9]+", value):
        try:
            f.SetValueString(param, value)
        except:
            forms.alert(
                "{} [{}]\n {} (value string) [{}]".format(
                    param.Definition.Name, param.StorageType, value, type(value)
                ),
                "Error setting " + param.Definition.Name,
            )
    else:
        try:
            if param.StorageType == "Double":
                value = float(value)
            elif param.StorageType == "Integer":
                value = int(value)
            elif param.StorageType == "ElementID":
                value = None
            if not value is None:
                f.Set(param, value)
        except:
            forms.alert(
                "{} [{}]\n {} (value [{}]".format(
                    param.Definition.Name, param.StorageType, value, type(value)
                ),
                "Error setting " + param.Definition.Name,
            )

def replaceParam(oldName, newName, param, sharedParams, paraGroup, isInstance, fam):
    errorState = False
    if param.IsShared and newName in sharedParams:
        # Cannot direct replace shared with shared so have to first replace with a family parameter
        #
        # Replace a shared family parameter with a new non-shared family parameter.
        # public FamilyParameter ReplaceParameter(
        # 	FamilyParameter currentParameter,
        # 	string parameterName,
        # 	BuiltInParameterGroup parameterGroup,
        # 	bool isInstance
        # )
        familyParameter = fam.ReplaceParameter(param, "x"+oldName, paraGroup, isInstance)
    else:
        familyParameter = param
    # Replace a family parameter with a shared parameter.
    # public FamilyParameter ReplaceParameter(
    #   FamilyParameter currentParameter,
    #   ExternalDefinition familyDefinition,
    #   BuiltInParameterGroup parameterGroup,
    #   bool isInstance
    # )
    try:
        param = fam.ReplaceParameter(familyParameter, sharedParams[newName], paraGroup, isInstance)
    except:
        errorState = True
        param = False
    return param, errorState

def pathShortener(path, length=40):
    pattern = r"^(\w+:\\)?([^\\]*\\).*(\\[^\\]*\\[^.]*[.].*)$"
    replacement = r"\1\2...\3"
    if path and len(path) > length and re.match(pattern, path):
        return re.sub(pattern, replacement, path)
    else:
        return path


def xlFixUnicode(value, ctype):
    return value #.decode("utf-8") if ctype == 1 else value


def main():
    doc = revit.doc
    app = __revit__.Application
    fam = doc.FamilyManager

    # pick excel file and read new parameters
    # https://github.com/pyrevitlabs/pyRevit/tree/master/site-packages/xlrd
    inParams = []
    cfg = script.get_config("MAWdev")
    path = cfg.get_option("famparamxl", "not set")
    sheet_name = cfg.get_option("famparamxlsheet", "")
    exists = os.path.exists(path)
    if not exists:
        path = forms.pick_file(file_ext="xlsx")
        exists = False if not path else os.path.exists(path)
    if exists:
        book = xlrd.open_workbook(path)
        sheet_name = (
            sheet_name
            if sheet_name
            else forms.SelectFromList.show(
                book.sheet_names(),
                button_name="Select sheet",
                title="Select Excel Sheet",
            )
        )
        worksheet = book.sheet_by_name(sheet_name)

        # create ordered list to preserve order
        for r in worksheet.get_rows():
            inParams.append([xlFixUnicode(c.value, c.ctype) for c in r])

    if not len(inParams):
        forms.alert("Error opening {}".format(pathShortener(path)), "Error")
        sys.exit()

    # get family parameters
    currentParams = fam.GetParameters()
    currentParamNames = [x.Definition.Name for x in currentParams]
    categoryName = doc.OwnerFamily.FamilyCategory.Name
    if categoryName == "Doors":
        for p in doc.OwnerFamily.Parameters:
            if p.Definition.Name == "Host":
                isCurtain = False if p.AsValueString() == "Wall" else True
                break

    headers = inParams.pop(0)  # get headers from first row
    newParams = []
    formulaParams = []
    valueParams = []
    errorItems = []

    # get shared parameters
    sharedParams = {}
    sharedParamFile = app.OpenSharedParameterFile()
    for sg in sharedParamFile.Groups:
        sgName = sg.Name
        for sp in sg.Definitions:
            sharedParams[sp.Name] = sp

    # wrap in a Transaction
    with Transaction("Update {} parameters".format(categoryName)) as rvtxn:

        for p in inParams:
            if categoryName == "Doors" and "CurtainWallDoors" in headers:
                if isCurtain and not p[headers.index("CurtainWallDoors")]:
                    continue
            parameterName = p[headers.index("Parameter")]
            paraType = (
                p[headers.index("Type")]
                if p[headers.index("Type")] in ["SHARED", "SORT", "RENAME", "REPLACE"]
                else DB.ParameterType.Parse(DB.ParameterType, p[headers.index("Type")])
            )
            paraGroup = DB.BuiltInParameterGroup.Parse(
                DB.BuiltInParameterGroup, p[headers.index("Group")]
            )
            isInstance = p[headers.index("Instance")]
            formula = p[headers.index("Formula")] or ""
            depends = p[headers.index("Dependents")] or ""
            depends = [x.strip() for x in depends.split(",")]
            depends = [] if depends == [""] else depends
            formulaOverride = p[headers.index("FormulaOverride")]
            newValue = p[headers.index("Value")]
            valueOverride = p[headers.index("ValueOverride")]
            oldName = p[headers.index("OldName")]

            isNew = False
            param = False
            if parameterName in currentParamNames:
                param = familyHasParameter(currentParams, parameterName)
            elif oldName and oldName in currentParamNames:
                param = familyHasParameter(currentParams, oldName)
                if param and paraType == "REPLACE":
                    param, errorState = replaceParam(oldName, parameterName, param, sharedParams, paraGroup, isInstance, fam)
                    if param.Definition.Name == oldName or errorState:
                        errorItems.append("ERROR: couldn't replace '{}' with '{}'".format(oldName, parameterName))
                        errorItems.append("Parameter is instance: " + str(param.IsInstance))
                        errorItems.append("Excel is instance: " + str(isInstance))
                        param = False
                elif param and paraType == "RENAME":
                    # Rename a family parameter.
                    # public void RenameParameter(
                    # 	FamilyParameter familyParameter,
                    # 	string name
                    # )
                    fam.RenameParameter(param, parameterName)
                    if param.Definition.Name == oldName:
                        errorItems.append("ERROR: couldn't rename '{}' to '{}'".format(oldName, parameterName))
                        param = False
            if not param:
                isNew = True
                formulaOverride = True
                valueOverride = True

                if paraType == "SHARED":
                    if parameterName in sharedParams:
                        # public FamilyParameter AddParameter(
                        # 	ExternalDefinition familyDefinition,
                        # 	BuiltInParameterGroup parameterGroup,
                        # 	bool isInstance
                        # )
                        param = fam.AddParameter(
                            sharedParams[parameterName], paraGroup, isInstance
                        )
                    else:
                        errorItems.append(
                            "ERROR: Shared parameter '{}' not found".format(
                                parameterName
                            )
                        )
                elif paraType not in ["SORT", "REPLACE", "RENAME"]:
                    # public FamilyParameter AddParameter(
                    # 	string parameterName,
                    # 	BuiltInParameterGroup parameterGroup,
                    # 	ParameterType parameterType,
                    # 	bool isInstance
                    # )
                    param = fam.AddParameter(
                        parameterName, paraGroup, paraType, isInstance
                    )

            if param:
                if param.Definition.ParameterGroup != paraGroup:
                    param.Definition.ParameterGroup = paraGroup
                if formula:
                    formulaParams.append(
                        {
                            "parameter": param,
                            "name": parameterName,
                            "formula": formula,
                            "dependents": depends,
                            "formulaOverride": formulaOverride,
                        }
                    )

                # Store Value to set for each type
                if not newValue == "" and not param.IsDeterminedByFormula:
                    valueParams.append([param, newValue, valueOverride])

                newParams.append(param)

        # Set values for parameters
        familyTypesItor = fam.Types.ForwardIterator()
        familyTypesItor.Reset()
        while familyTypesItor.MoveNext():
            familyType = familyTypesItor.Current
            fam.CurrentType = familyType
            for i in valueParams:
                param, newValue, valueOverride = i[0], i[1], i[2]
                if valueOverride or not familyType.HasValue(param):
                    setParam(param, newValue)

        # Add formulas
        updatedParams = fam.GetParameters()
        for fx in formulaParams:
            # public void SetFormula(
            # 	FamilyParameter familyParameter,
            # 	string formula
            # )
            hasDepends = (
                False if fx["parameter"].Formula and not fx["formulaOverride"] else True
            )
            for d in fx["dependents"]:
                if not familyHasParameter(updatedParams, d):
                    hasDepends = False
            if hasDepends:
                try:
                    fam.SetFormula(fx["parameter"], str(fx["formula"]))
                except:
                    errorItems.append("ERROR: couldn't set formula for '{}'".format(fx["name"]))

    # Report errors
    if len(errorItems) > 0:
        forms.alert("\n".join(errorItems), "errors")

    # Sort Parameters
    with Transaction("Sort {} parameters".format(categoryName)) as rvtxn:
        # Sort parameters according to excel order
        updatedParams = fam.GetParameters()
        orderedParams = []
        for p in inParams:
            parameterName = p[headers.index("Parameter")]
            param = familyHasParameter(updatedParams, parameterName)
            if param:
                orderedParams.append(param)
        try:
            fam.ReorderParameters(
                orderedParams + [x for x in updatedParams if x not in orderedParams]
            )
        except:
            forms.alert("{}".format("\n- ".join([x.Definition.Name for x in updatedParams if x not in orderedParams])))


if EXEC_PARAMS.config_mode:
    # Settings (shift-click)
    cfg = script.get_config("MAWdev")
    curxlpath = cfg.get_option("famparamxl", "not set")
    curxlsheet = cfg.get_option("famparamxlsheet", "")
    if curxlpath is None:
        curxlpath = "not set"
    exists = os.path.exists(curxlpath)

    # present option to change
    options = [
        "Change Excel file and sheet",
        "Clear Excel file setting (pick each time)",
        "Close",
    ]
    msg = "Current Excel file is:\n  {}\n".format(pathShortener(curxlpath))
    if curxlsheet:
        msg += "Sheet: {}\n".format(curxlsheet)
    if not exists:
        msg = msg + "\n(File not found)\nDo you want to set it now?"
        options[0] = "Select Excel file and sheet"
    else:
        msg = msg + "\nDo you want to change this?"
    update = forms.alert(
        msg,
        options=options,
        title="Configure Family Parameter Load Options",
        warn_icon=not exists,
    )
    newxlpath = ""
    newxlsheet = ""
    if update == options[2]:
        sys.exit()
    elif update == options[0]:
        if exists:
            suggestpath = os.path.dirname(curxlpath)
        else:
            suggestpath = ""
        newxlpath = forms.pick_file(
            file_ext="xlsx", init_dir=suggestpath, title="Select Excel File"
        )
        if os.path.exists(newxlpath):
            book = xlrd.open_workbook(newxlpath)
            newxlsheet = forms.SelectFromList.show(
                book.sheet_names(),
                button_name="Select sheet",
                title="Select Excel Sheet",
            )
    cfg.famparamxl = newxlpath
    cfg.famparamxlsheet = newxlsheet
    script.save_config()
    forms.alert(
        "Configuration updated\nExcel file: {}\nSheet: {}".format(
            pathShortener(newxlpath), newxlsheet
        ),
        title="Settings",
        warn_icon=False,
    )
else:
    main()
