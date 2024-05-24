# -*- coding: utf-8 -*-
import os.path as op
from pyrevit import revit, DB
from pyrevit import forms

fm = revit.doc.FamilyManager
tcUnits = []
tcPara = []
tcTypes = []
dump = ""

for fp in fm.GetParameters():
    if fp.IsDeterminedByFormula == False:
        pn = fp.Definition.Name
        ut = fp.Definition.UnitType
        u = revit.doc.GetUnits
        u = DB.Units(DB.UnitSystem.Metric)
        fo = u.GetFormatOptions(ut)
        s1 = DB.UnitUtils.GetTypeCatalogString(ut)
        s2 = DB.UnitUtils.GetTypeCatalogString(fo.DisplayUnits)
        if s1 == "NUMBER" and s2 == "GENERAL":
            s1 = "OTHER"
            s2 = ""
        tcUnits.append(pn + "##" + s1 + "##" + s2)
        tcPara.append(fp)

tcUnits.sort()

forms.alert(",".join(tcUnits))

for ft in fm.Types:
    tcTypes.append(ft.Name)

forms.alert(",".join(sorted(tcTypes)))

def FamilyParamValueString(ft, fp, doc):
    val = ft.AsValueString(fp)
    if fp.StorageType == DB.StorageType.String:
        val = "'" + ft.AsString(fp) + "' (string)"
    elif fp.StorageType == DB.StorageType.ElementId:
        pid = ft.AsElementId(fp)
        ele = doc.GetElement(pid)
        fName = ele.Family.Name
        eName = DB.Element.Name.__get__(ele)
        val = str(pid) + " (" + fName + ":" + eName + ")"
    elif fp.StorageType == DB.StorageType.Integer:
        val = str(ft.AsInteger(fp)) + " (int)";
    elif val is None and fp.StorageType == DB.StorageType.Double:
        val = str(ft.AsDouble(fp)) + " (double)"
    return val

for ft in fm.Types:
    name = ft.Name
    dump += name + "\r\n"
    for pn in tcPara:
        fp = pn.Definition.Name
        if ft.HasValue(pn):
            val = FamilyParamValueString(ft, pn, revit.doc )
            dump += ": " + fp + " = " + val + "\r\n"

forms.alert(dump)

