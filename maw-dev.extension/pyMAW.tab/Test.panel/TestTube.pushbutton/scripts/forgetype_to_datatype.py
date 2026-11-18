# -*- coding: utf-8 -*-
"""Forgetype To Datatype."""

from Autodesk.Revit.DB import (
    UnitUtils,
    LabelUtils,
    SpecUtils,
)


def forgetype_to_datatype():
    print("Print all specs")
    results = set()

    # spec_ids = UnitUtils.GetAllMeasurableSpecs()
    # spec_ids = UnitUtils.GetAllSpecs()
    spec_ids = SpecUtils.GetAllSpecs()
    print(len(spec_ids))
    for spec_id in spec_ids:
        forge = spec_id.TypeId
        forgename = LabelUtils.GetLabelForSpec(spec_id)
        try:
            myname = UnitUtils.GetTypeCatalogStringForSpec(spec_id)
        except:
            myname = "not measurable"
        try:
            results.add((myname, forgename, forge))
        except:
            pass

    for r in sorted(results):
        print(r[2])
        print(r[1])
        print(r[0])
        print("------")


if __name__ == "__main__":
    forgetype_to_datatype()
