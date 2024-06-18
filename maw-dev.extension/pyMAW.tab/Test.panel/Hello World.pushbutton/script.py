# -*- coding: UTF-8 -*-

# from pyrevit import HOST_APP
from pyrevit import revit
from pyrevit import DB, UI
from pyrevit import forms
# from pyrevit.revit import query
# from pyrevit.framework import List
from pyrevit.revit import Transaction
# from pyrevit.revit.db.transaction import Transaction
# from pyrevit.revit import create
from pyrevit import script
from pyrevit import EXEC_PARAMS
# from rpws import RevitServer
import os
# import json
import xlrd
import re
import sys


# func = forms.SelectFromList.show(
    # DB.FormulaManager.GetFunctions(), button_name="select function"
# )
# oper = forms.SelectFromList.show(
    # DB.FormulaManager.GetOperators(), button_name="select function"
# )
# paras = DB.GlobalParametersManager.GetGlobalParametersOrdered(revit.doc)
# para = paras[0]

# formula = "{}(30) * 1 {} 10".format(func, oper)
# fx_value = DB.FormulaManager.Evaluate(para, revit.doc, formula)

# forms.alert("{}\n= {}".format(formula, fx_value), "Valid formula")
# # Evaluate()
# test = xl.load("C:\\Users\\Warwickm\\OneDrive - Warren and Mahoney\\Documents\\BIM Content Development\\Doors\\DoorFamilyParameters.xslx")
# forms.alert("test",str(test))
# https://github.com/pyrevitlabs/pyRevit/blob/b7704eacfe1e5ab4840c1759f5ee3830af38a328/pyrevitlib/pyrevit/interop/xl.py




# Test if family already contains the parameter
def familyHasParameter(currentParams, parameterName):
    for k in range(len(currentParams)):
        if currentParams[k].Definition.Name == parameterName:
            return currentParams[k]
    return False


def setParam(param, value, f = revit.doc.FamilyManager):
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
        forms.alert("{} [{}] | {} [{}]".format(param.Definition.Name, param.StorageType, value, type(value)), "Error setting "+param.Definition.Name)


def pathShortener(path, length = 40):
    pattern = r"^(\w+:\\)?([^\\]*\\).*(\\[^\\]*\\[^.]*[.].*)$"
    replacement = r"\1\2...\3"
    if path and len(path) > length and re.match(pattern, path):
        return re.sub(pattern, replacement, path)
    else:
        return path

def main():
    doc = revit.doc
    app = __revit__.Application
    fam = doc.FamilyManager

    # pick excel file and read new parameters
    inParams = []
    cfg = script.get_config("MAWdev")
    path = cfg.get_option("famparamxl", "not set")
    sheet_name = cfg.get_option("famparamxlsheet", "")
    exists = os.path.exists(path)
    if not exists:
        path = forms.pick_file(file_ext='xlsx')
        exists = False if not path else os.path.exists(path)
    if exists:
        book = xlrd.open_workbook(path)
        sheet_name = sheet_name if sheet_name else forms.SelectFromList.show(book.sheet_names(), button_name="Select sheet", title="Select Excel Sheet")
        worksheet = book.sheet_by_name(sheet_name)

        # create ordered list to preserve order
        for r in worksheet.get_rows():
            inParams.append([c.value for c in r])

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
    instanceParams = []
    errorItems = []

    # get shared parameters
    sharedParams = {}
    sharedParamFile = app.OpenSharedParameterFile()
    for sg in sharedParamFile.Groups:
        sgName = sg.Name
        for sp in sg.Definitions:
            sharedParams[sp.Name] = sp

    # wrap in a Transaction
    with Transaction('Update {} parameters'.format(categoryName)) as rvtxn:
    # TransactionManager.Instance.EnsureInTransaction(doc)

        for p in inParams:
            if categoryName == "Doors" and "CurtainWallDoors" in headers:
                if isCurtain and not p[headers.index("CurtainWallDoors")]:
                    continue
            parameterName = p[headers.index("Parameter")]
            paraType = (
                p[headers.index("Type")]
                if p[headers.index("Type")] in ["SHARED", "SORT"]
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

            isNew = False
            param = False
            if parameterName in currentParamNames:
                param = familyHasParameter(currentParams, parameterName)
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
                            "ERROR: Shared parameter '{}' not found".format(parameterName)
                        )
                elif paraType != "SORT":
                    # public FamilyParameter AddParameter(
                    # 	string parameterName,
                    # 	BuiltInParameterGroup parameterGroup,
                    # 	ParameterType parameterType,
                    # 	bool isInstance
                    # )
                    param = fam.AddParameter(parameterName, paraGroup, paraType, isInstance)

            if param:
                if param.Definition.ParameterGroup != paraGroup:
                    # errorItems.append("ERROR: Parameter {} is in Group '{}', should be '{}'".format(parameterName, paraGroup, param.Definition.ParameterGroup))
                    param.Definition.ParameterGroup = paraGroup
                if formula and (formulaOverride or not param.Formula):
                    formulaParams.append(
                        {
                            "parameter": param,
                            "formula": formula,
                            "dependents": depends,
                            "formulaOverride": formulaOverride,
                        }
                    )

                # Set Value
                # immediately for type based, deferred for instance based
                if (valueOverride and not newValue == "") and not param.IsDeterminedByFormula:
                    if param.IsInstance:
                        instanceParams.append([parameterName, param, newValue, valueOverride])
                    elif valueOverride or not fam.CurrentType.HasValue(param):
                        setParam(param, newValue)

                newParams.append(param)

        # Set Type values for instance parameters
        familyTypesItor = fam.Types.ForwardIterator()
        familyTypesItor.Reset()
        while familyTypesItor.MoveNext():
            familyType = familyTypesItor.Current
            fam.CurrentType = familyType
            for i in instanceParams:
                parameterName, param, newValue, valueOverride = i[0], i[1], i[2], i[3]
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
                fam.SetFormula(fx["parameter"], str(fx["formula"]))

        # Sort parameters according to excel order
        fam.ReorderParameters([x for x in currentParams if x not in newParams] + newParams)

    # TransactionManager.Instance.TransactionTaskDone()
    # Report errors
    if len(errorItems) > 0:
        forms.alert("\n".join(errorItems), "errors")



if EXEC_PARAMS.config_mode:
    # Settings (shift-click)
    cfg = script.get_config("MAWdev")
    curxlpath = cfg.get_option("famparamxl", "not set")
    curxlsheet = cfg.get_option("famparamxlsheet", "")
    if curxlpath is None:
        curxlpath = "not set"
    exists = os.path.exists(curxlpath)

    # present option to change
    options = ["Change Excel file and sheet", "Clear Excel file setting (pick each time)", "Close"]
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
            newxlsheet = forms.SelectFromList.show(book.sheet_names(), button_name="Select sheet", title="Select Excel Sheet")
    cfg.famparamxl = newxlpath
    cfg.famparamxlsheet = newxlsheet
    script.save_config()
    forms.alert("Configuration updated\nExcel file: {}\nSheet: {}".format(pathShortener(newxlpath), newxlsheet), title="Settings", warn_icon=False)
else:
    main()
