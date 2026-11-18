# -*- coding: UTF-8 -*-
from pyrevit import revit
from pyrevit import DB
from pyrevit import forms
from pyrevit.revit import Transaction
from pyrevit import script
from pyrevit import EXEC_PARAMS
import os
import sys
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
            if value is not None:
                f.Set(param, value)
        except:
            forms.alert(
                "{} [{}]\n {} (value [{}]".format(
                    param.Definition.Name, param.StorageType, value, type(value)
                ),
                "Error setting " + param.Definition.Name,
            )


def replaceParam(oldName, newName, param, sharedParams, paraGroup, isInstance, fam):
    error_state = False
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
        family_parameter = fam.ReplaceParameter(
            param, "x" + oldName, paraGroup, isInstance
        )
    else:
        family_parameter = param
    # Replace a family parameter with a shared parameter.
    # public FamilyParameter ReplaceParameter(
    #   FamilyParameter currentParameter,
    #   ExternalDefinition familyDefinition,
    #   BuiltInParameterGroup parameterGroup,
    #   bool isInstance
    # )
    try:
        param = fam.ReplaceParameter(
            family_parameter, sharedParams[newName], paraGroup, isInstance
        )
    except:
        error_state = True
        param = False
    return param, error_state


def pathShortener(path, length=40):
    pattern = r"^(\w+:\\)?([^\\]*\\).*(\\[^\\]*\\[^.]*[.].*)$"
    replacement = r"\1\2...\3"
    if path and len(path) > length and re.match(pattern, path):
        return re.sub(pattern, replacement, path)
    else:
        return path


def xlFixUnicode(value, ctype):
    return value  # .decode("utf-8") if ctype == 1 else value


def main():
    doc = revit.doc
    app = __revit__.Application
    fam = doc.FamilyManager

    # pick excel file and read new parameters
    # https://github.com/pyrevitlabs/pyRevit/tree/master/site-packages/xlrd
    in_params = []
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
            if sheet_name in book.sheet_names()
            else forms.SelectFromList.show(
                book.sheet_names(),
                button_name="Select sheet",
                title="Select Excel Sheet",
            )
        )
        worksheet = book.sheet_by_name(sheet_name)

        # create ordered list to preserve order
        for r in worksheet.get_rows():
            in_params.append([xlFixUnicode(c.value, c.ctype) for c in r])

    if not len(in_params):
        forms.alert("Error opening {}".format(pathShortener(path)), "Error")
        sys.exit()

    # get family parameters
    current_params = fam.GetParameters()
    current_param_names = [x.Definition.Name for x in current_params]
    category_name = doc.OwnerFamily.FamilyCategory.Name
    if category_name == "Doors":
        for p in doc.OwnerFamily.Parameters:
            if p.Definition.Name == "Host":
                is_curtain = False if p.AsValueString() == "Wall" else True
                break

    headers = in_params.pop(0)  # get headers from first row
    new_params = []
    formula_params = []
    value_params = []
    error_items = []

    # get shared parameters
    shared_params = {}
    shared_param_file = app.OpenSharedParameterFile()
    for sg in shared_param_file.Groups:
        for sp in sg.Definitions:
            shared_params[sp.Name] = sp

    # wrap in a Transaction
    with Transaction("Update {} parameters".format(category_name)):
        for p in in_params:
            if not p[headers.index("Parameter")]:
                continue
            if category_name == "Doors" and "CurtainWallDoors" in headers:
                if is_curtain and not p[headers.index("CurtainWallDoors")]:
                    continue
            parameter_name = p[headers.index("Parameter")]
            para_type = (
                p[headers.index("Type")]
                if p[headers.index("Type")] in ["SHARED", "SORT", "RENAME", "REPLACE"]
                else DB.ParameterType.Parse(DB.ParameterType, p[headers.index("Type")])
            )
            para_group = DB.BuiltInParameterGroup.Parse(
                DB.BuiltInParameterGroup, p[headers.index("Group")]
            )
            is_instance = p[headers.index("Instance")]
            formula = p[headers.index("Formula")] or ""
            depends = p[headers.index("Dependents")] or ""
            depends = [x.strip() for x in depends.split(",")]
            depends = [] if depends == [""] else depends
            formula_override = p[headers.index("FormulaOverride")]
            new_value = p[headers.index("Value")]
            value_override = p[headers.index("ValueOverride")]
            old_name = p[headers.index("OldName")]

            param = False
            if parameter_name in current_param_names:
                param = familyHasParameter(current_params, parameter_name)
            elif old_name and old_name in current_param_names:
                param = familyHasParameter(current_params, old_name)
                if param and para_type == "REPLACE":
                    param, error_state = replaceParam(
                        old_name,
                        parameter_name,
                        param,
                        shared_params,
                        para_group,
                        is_instance,
                        fam,
                    )
                    if param.Definition.Name == old_name or error_state:
                        error_items.append(
                            "ERROR: couldn't replace '{}' with '{}'".format(
                                old_name, parameter_name
                            )
                        )
                        error_items.append(
                            "Parameter is instance: " + str(param.IsInstance)
                        )
                        error_items.append("Excel is instance: " + str(is_instance))
                        param = False
                elif param and para_type == "RENAME":
                    # Rename a family parameter.
                    # public void RenameParameter(
                    # 	FamilyParameter familyParameter,
                    # 	string name
                    # )
                    fam.RenameParameter(param, parameter_name)
                    if param.Definition.Name == old_name:
                        error_items.append(
                            "ERROR: couldn't rename '{}' to '{}'".format(
                                old_name, parameter_name
                            )
                        )
                        param = False
            if not param:
                formula_override = True
                value_override = True

                if para_type == "SHARED":
                    if parameter_name in shared_params:
                        # public FamilyParameter AddParameter(
                        # 	ExternalDefinition familyDefinition,
                        # 	BuiltInParameterGroup parameterGroup,
                        # 	bool isInstance
                        # )
                        param = fam.AddParameter(
                            shared_params[parameter_name], para_group, is_instance
                        )
                    else:
                        error_items.append(
                            "ERROR: Shared parameter '{}' not found".format(
                                parameter_name
                            )
                        )
                elif para_type not in ["SORT", "REPLACE", "RENAME"]:
                    # public FamilyParameter AddParameter(
                    # 	string parameterName,
                    # 	BuiltInParameterGroup parameterGroup,
                    # 	ParameterType parameterType,
                    # 	bool isInstance
                    # )
                    param = fam.AddParameter(
                        parameter_name, para_group, para_type, is_instance
                    )

            if param:
                if param.Definition.ParameterGroup != para_group:
                    param.Definition.ParameterGroup = para_group
                if formula:
                    formula_params.append(
                        {
                            "parameter": param,
                            "name": parameter_name,
                            "formula": formula,
                            "dependents": depends,
                            "formulaOverride": formula_override,
                        }
                    )

                # Store Value to set for each type
                if not new_value == "" and not param.IsDeterminedByFormula:
                    value_params.append([param, new_value, value_override])

                new_params.append(param)

        # Set values for parameters
        family_types_itor = fam.Types.ForwardIterator()
        family_types_itor.Reset()
        while family_types_itor.MoveNext():
            family_type = family_types_itor.Current
            fam.CurrentType = family_type
            for i in value_params:
                param, new_value, value_override = i[0], i[1], i[2]
                if value_override or not family_type.HasValue(param):
                    setParam(param, new_value)

        # Add formulas
        updated_params = fam.GetParameters()
        for fx in formula_params:
            # public void SetFormula(
            # 	FamilyParameter familyParameter,
            # 	string formula
            # )
            has_depends = (
                False if fx["parameter"].Formula and not fx["formulaOverride"] else True
            )
            for d in fx["dependents"]:
                if not familyHasParameter(updated_params, d):
                    has_depends = False
            if has_depends:
                try:
                    fam.SetFormula(fx["parameter"], str(fx["formula"]))
                except:
                    error_items.append(
                        "ERROR: couldn't set formula for '{}'".format(fx["name"])
                    )

    # Report errors
    if len(error_items) > 0:
        forms.alert("\n".join(error_items), "errors")

    # Sort Parameters
    with Transaction("Sort {} parameters".format(category_name)):
        # Sort parameters according to excel order
        updated_params = fam.GetParameters()
        ordered_params = []
        for p in in_params:
            parameter_name = p[headers.index("Parameter")]
            param = familyHasParameter(updated_params, parameter_name)
            if param:
                ordered_params.append(param)
        try:
            fam.ReorderParameters(
                ordered_params + [x for x in updated_params if x not in ordered_params]
            )
        except:
            forms.alert(
                "{}".format(
                    "\n- ".join(
                        [
                            x.Definition.Name
                            for x in updated_params
                            if x not in ordered_params
                        ]
                    )
                )
            )


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
