from pyrevit import DB
from pyrevit import revit
from pyrevit import forms
from pyrevit import HOST_APP
# import os

doc = revit.doc

# for img in DB.FilteredElementCollector(doc).OfClass(DB.ImageType).ToElements():
    # name = img.Path
    # name = name[name.find("\\")+1:]
    # file = open("C:\\_Revit\\{}".format(name), 'wb')
    # bitmap = img.GetImage().ToString()
    # try:
        # ##### Write binary data to file
        # file.write(img.GetImage())
    # finally:
        # ### Close the file
        # file.close()

# forms.alert(str(name))


def get_all_project_parameters(document):
    it = iter(document.ParameterBindings)
    proj_params = []
    while it.MoveNext():
        proj_params.append([it.Key, it.Current])

    pps = []

    for pp, pb in proj_params:
        pp_ut = DB.UnitUtils.GetTypeCatalogString(pp.UnitType)
        pp_group = str(pp.ParameterGroup)
        if HOST_APP.is_newer_than(2022):
            t = pp.GetDataType()
            pp_type = DB.LabelUtils.GetLabelForSpec(t).replace("/", "")
        else:
            pp_type = str(pp.ParameterType)
            if pp_type == "Invalid":
                pp_type = "Built-in"
        pp_binding = []
        for b in pb.Categories:
            pp_binding.append(b.Name)
        pps.append([pp.Id.IntegerValue, pp.Name, pp_group, pp_type, ", ".join(pp_binding)])

    return pps

forms.alert(str(get_all_project_parameters(doc)))


# def string_diff(s1, s2):
    # d1, d2 = [], []
    # i1 = i2 = 0
    # l1 = len(s1)
    # l2 = len(s2)
    # while True:
        # if i1 >= len(s1) or i2 >= len(s2):
            # d1.extend(s1[i1:])
            # d2.extend(s2[i2:])
            # break
        # if s1[i1] != s2[i2]:
            # e1 = l1 - i1
            # e2 = l2 - i2
            # if e1 > e2:
                # d1.append(s1[i1])
                # i2 -= 1
            # elif e1 < e2:
                # d2.append(s2[i2])
                # i1 -= 1
            # else:
                # d1.append(s1[i1])
                # d2.append(s2[i2])
        # i1 += 1
        # i2 += 1
    # return ["".join(d1), "".join(d2)]

# regex = r"\"CLD:\\\\.*{(.*)}(.*)\\{(.*)}(.*)\.rvt\""

# test_str = "< ModelPath Created: Is server path = True, Region = \"US\", Central server = \"\", Path = \"CLD:\\\\US\\{aa82cbb1-52a0-414c-be34-9cdbd5aba6d5}Wellington Town Hall\\{620771ec-fba6-48f1-bbcf-d1b2b7be37e9}WTH-NLC-STR-00-CM-AB-RVT_22.rvt\""

# test_str = strings[0]

# text = ""

# matches = re.finditer(regex, test_str)

# for matchNum, match in enumerate(matches, start=1):
    
    # text += "\nMatch {matchNum} was found at {start}-{end}: {match}".format(matchNum = matchNum, start = match.start(), end = match.end(), match = match.group())
    
    # for groupNum in range(0, len(match.groups())):
        # groupNum = groupNum + 1
        
        # text += "Group {groupNum} found at {start}-{end}: {group}\n".format(groupNum = groupNum, start = match.start(groupNum), end = match.end(groupNum), group = match.group(groupNum))

# forms.alert(str(string_diff(strings[0],test_str)) + text)








# # Set filled region boundaries to invisible lines
# from pyrevit import DB
# from pyrevit import revit
# from pyrevit.revit import Transaction

# doc = revit.doc

# text = ""
# for ls in DB.FilteredElementCollector(doc).OfClass(DB.GraphicsStyle):
    # text += "{}\r\n".format(ls.Name)
    # if ls.Name == "<Invisible lines>":
        # ilStyle = ls
        # break

# with Transaction("MAW filled region update", doc):
    # for r in DB.FilteredElementCollector(doc).OfClass(DB.FilledRegion).WhereElementIsNotElementType().ToElements():
        # r.SetLineStyleId(ilStyle.Id)






# import random
# from pyrevit import revit, DB, forms

# __context__ = 'selection'

# testList = [1 for _ in range(46)]    # Light Orange
# testList.extend(2 for _ in range(45)) # Maroon
# testList.extend(3 for _ in range(46)) # Orange
# testList.extend(4 for _ in range(45)) # Purple
# testList.extend(5 for _ in range(45)) # Red
# testList.append(6)

# # get current selection
# selection = revit.get_selection()

# print('The original list is\n'+str(testList))

# # using Fisher-Yates shuffle alogorithm
# # modified for no repeats

# for i in range(len(testList)-1, 1, -1):
    
    # j = random.randint(0,i)
    # testList[i-1], testList[j] = testList[j], testList[i-1]

    # #fix if two in a row
    # a = 0
    # while testList[i] == testList[i-1] and a < i+2:
        # j = random.randint(0,i-1)
        # testList[i-1], testList[j] = testList[j], testList[i-1]
        # a += 1
        # print('Re-shuffle {0}'.format(a))


    # print('The shuffled list at step {0} looks like:'.format(i))
    # print(str(testList)+' {0} {1}'.format(testList[i],testList[i-1]))

# testList.pop()

# print(str(testList))

# with revit.Transaction("Randomise Property"):
    # for i in range (0,len(testList)):
        # with forms.WarningBar(title="Pick source object {0}:".format(i)):
            # obj = revit.pick_element()
        # current = obj.LookupParameter("Selected Material")
        # print(str(current))
        # print(str(current.AsInteger()))
        # current.Set(testList[i])
    
    
