import random
from pyrevit import revit, DB, forms

__context__ = 'selection'

testList = [1 for _ in range(46)]    # Light Orange
testList.extend(2 for _ in range(45)) # Maroon
testList.extend(3 for _ in range(46)) # Orange
testList.extend(4 for _ in range(45)) # Purple
testList.extend(5 for _ in range(45)) # Red
testList.append(6)

# get current selection
selection = revit.get_selection()

print('The original list is\n'+str(testList))

# using Fisher-Yates shuffle alogorithm
# modified for no repeats

for i in range(len(testList)-1, 1, -1):
    
    j = random.randint(0,i)
    testList[i-1], testList[j] = testList[j], testList[i-1]

    #fix if two in a row
    a = 0
    while testList[i] == testList[i-1] and a < i+2:
        j = random.randint(0,i-1)
        testList[i-1], testList[j] = testList[j], testList[i-1]
        a += 1
        print('Re-shuffle {0}'.format(a))


    print('The shuffled list at step {0} looks like:'.format(i))
    print(str(testList)+' {0} {1}'.format(testList[i],testList[i-1]))

testList.pop()

print(str(testList))

with revit.Transaction("Randomise Property"):
    for i in range (0,len(testList)):
        with forms.WarningBar(title="Pick source object {0}:".format(i)):
            obj = revit.pick_element()
        current = obj.LookupParameter("Selected Material")
        print(str(current))
        print(str(current.AsInteger()))
        current.Set(testList[i])
    
    
