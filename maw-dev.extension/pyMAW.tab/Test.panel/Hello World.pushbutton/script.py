# from pyrevit import revit, DB
# from pyrevit import forms

from pyrevit import revit
from pyrevit import script
from rpws import RevitServer
import os

__fullframeengine__ = True
__context__ = 'zero-doc'

def OpenNpp (path = "", options = "", exepath = None):
    logger = script.get_logger()
    
    # get Notepad path
    if exepath == None:
        cfg = script.get_config("Notepad++")
        exepath = cfg.get_option('notepadpath', os.path.join(os.environ["ProgramFiles"], "Notepad++", "Notepad++.exe"))
    
    # open Notepad(++) with file
    if len(path) > 0:
        path = '"' + os.path.realpath(path) + '"'
    if not exepath is None and os.path.exists(exepath):
        command = u'start "Notepad++" "{0}" {1} {2}'.format(exepath, options, path)
        logger.debug(command)
        os.system(command)
    else:
        os.system('start notepad {0}'.format(path))


revit_server_name = '10.6.1.1'
revit_server_ver = '2021'

rs = RevitServer(revit_server_name, revit_server_ver)

text = '''
@echo off
setlocal
set caduser=MichaelWarwick7522
set revitserver=-s {rs_name}
set accelerator=-a 10.7.1.5

'''
text = text.format(rs_name = revit_server_name)

curr_folder_name = ""
folder_path = '''
set revitserverpath={rs_folder}
set revitlocalpath=C:\\revitlocal\\_%revitserverpath%

echo Updating local files {count}/[[f_total]] from %revitserver%\\%revitserverpath% to %revitlocalpath% as %caduser%, via accelerator %accelerator%
echo.
'''

model_download = '''

set modelname={rs_model}
echo updating {count}/{total} %revitlocalpath%\\{rs_model}.rvt
"C:\\Program Files\Autodesk\\Revit {rs_ver}\\RevitServerToolCommand\RevitServerTool.exe" createLocalRVT "%revitserverpath%\\%modelname%.rvt" %revitserver% %accelerator% -d "%revitlocalpath%\\%modelname%.rvt" -o
'''

syntax = "-lbatch"
m_count = 0
f_count = 0

for parent, folders, files, models in rs.walk():
    m_count = 0
    for m in models:
        m_count += 1
        model_name = m.path[m.path.rfind("\\")+1:-4].replace("&","^&")
        folder_name = m.path[1:m.path.rfind("\\")].replace("&","^&")
        if folder_name != curr_folder_name:
            f_count += 1
            text += folder_path.format(rs_folder = folder_name, count = f_count)
            curr_folder_name = folder_name
        text += model_download.format(rs_model = model_name, rs_ver = revit_server_ver, count = m_count, total = len(models))

if text != "":
    docname = "{}_{}".format(revit_server_name, revit_server_ver)
    text = text.replace("[[f_total]]", str(f_count))
    path = script.get_instance_data_file(docname)
    if path:
        tempfile = revit.files.write_text(path, text)
        revit.files.correct_text_encoding(path)

        # open file
        OpenNpp(path = path, options = syntax)

# print(text)

"""
\AKI 820412 Centreway Villas\Centreway Villas.rvt
\AKI 820412 Centreway Villas\Block 1 type F\Centreway Villas - Block 1.rvt
\AKI 820412 Centreway Villas\Block 1 type F\Centreway Villas - Unit Type F - 1.rvt
\AKI 820412 Centreway Villas\Block 1 type F\Centreway Villas - Unit Type F - 10.rvt
\AKI 820412 Centreway Villas\Block 1 type F\Centreway Villas - Unit Type F - 2, 5 & 8.rvt
\AKI 820412 Centreway Villas\Block 1 type F\Centreway Villas - Unit Type F - 3, 6 & 9.rvt
\AKI 820412 Centreway Villas\Block 1 type F\Centreway Villas - Unit Type F - 4 & 7.rvt
\AKI 820412 Centreway Villas\Block 1 type F\Centreway Villas - Unit Type F - Interior - Lift.rvt
\AKI 820412 Centreway Villas\Block 1 type F\Centreway Villas - Unit Type F - Interior 3.rvt
\AKI 820412 Centreway Villas\Block 1 type F\Centreway Villas - Unit Type F - Interior 4 & 8.rvt
\AKI 820412 Centreway Villas\Block 1 type F\Centreway Villas - Unit Type F - Interior 4.rvt
\AKI 820412 Centreway Villas\Block 1 type F\Centreway Villas - Unit Type F - Interior 5 & 6.rvt
\AKI 820412 Centreway Villas\Block 1 type F\Centreway Villas - Unit Type F - Interior 7.rvt
\AKI 820412 Centreway Villas\Block 1 type F\Centreway Villas - Unit Type F - Interior.rvt
\AKI 820412 Centreway Villas\Block 1 type F\Centreway Villas - Unit Type F - Interior_msalinasM9VHH.rvt
\AKI 820412 Centreway Villas\Block 1 type F\Centreway Villas - Unit Type F -Interior Unit 1 Option 2.rvt
\AKI 820412 Centreway Villas\Block 2 type B + C\Centreway Villas - Block 2.rvt
\AKI 820412 Centreway Villas\Block 2 type B + C\Centreway Villas - Unit Type B.rvt
\AKI 820412 Centreway Villas\Block 2 type B + C\Centreway Villas - Unit Type C - End.rvt
\AKI 820412 Centreway Villas\Block 2 type B + C\Centreway Villas - Unit Type C Unit 11.rvt
\AKI 820412 Centreway Villas\Block 2 type B + C\Centreway Villas - Unit Type C.rvt
\AKI 820412 Centreway Villas\Block 3 type E\Centreway Villas - Block 3.rvt
\AKI 820412 Centreway Villas\Block 3 type E\Centreway Villas - Unit Type E - 17.rvt
\AKI 820412 Centreway Villas\Block 3 type E\Centreway Villas - Unit Type E - 18 & 22.rvt
\AKI 820412 Centreway Villas\Block 3 type E\Centreway Villas - Unit Type E - 19 & 23.rvt
\AKI 820412 Centreway Villas\Block 3 type E\Centreway Villas - Unit Type E - 20.rvt
\AKI 820412 Centreway Villas\Block 3 type E\Centreway Villas - Unit Type E - 21.rvt
\AKI 820412 Centreway Villas\Block 3 type E\Centreway Villas - Unit Type E - 24.rvt
\AKI 820412 Centreway Villas\Block 3 type E\Centreway Villas - Unit Type E - Interior - Wide.rvt
\AKI 820412 Centreway Villas\Block 3 type E\Centreway Villas - Unit Type E - Interior Unit 19.rvt
\AKI 820412 Centreway Villas\Block 3 type E\Centreway Villas - Unit Type E - Interior Unit 24.rvt
\AKI 820412 Centreway Villas\Block 3 type E\Centreway Villas - Unit Type E - Interior.rvt
\AKI 820412 Centreway Villas\Block 4 type G\Centreway Villas - Block 4_Retail5.rvt
\AKI 820412 Centreway Villas\Block 4 type G\Centreway Villas - Unit Type G - 25.rvt
\AKI 820412 Centreway Villas\Block 4 type G\Centreway Villas - Unit Type G - 26.rvt
\AKI 820412 Centreway Villas\Block 4 type G\Centreway Villas - Unit Type G - 27.rvt
\AKI 820412 Centreway Villas\Block 4 type G\Centreway Villas - Unit Type G - 28.rvt
\AKI 820412 Centreway Villas\Block 4 type G\Centreway Villas - Unit Type G - Interior.rvt
\AKI 820412 Centreway Villas\Block 5 type D\Centreway Villas - Block 5 Stepped.rvt
\AKI 820412 Centreway Villas\Block 5 type D\Centreway Villas - Unit Type D - 29.rvt
\AKI 820412 Centreway Villas\Block 5 type D\Centreway Villas - Unit Type D - 30 & 33.rvt
\AKI 820412 Centreway Villas\Block 5 type D\Centreway Villas - Unit Type D - 31.rvt
\AKI 820412 Centreway Villas\Block 5 type D\Centreway Villas - Unit Type D - 33.rvt
\AKI 820412 Centreway Villas\Block 5 type D\Centreway Villas - Unit Type D - 34.rvt
\AKI 820412 Centreway Villas\Block 5 type D\Centreway Villas - Unit Type D - Interior - Wide.rvt
\AKI 820412 Centreway Villas\Block 5 type D\Centreway Villas - Unit Type D - Interior.rvt
\AKI 820412 Centreway Villas\Details\All _Floor Finishes Types.rvt
\AKI 820412 Centreway Villas\Details\All_RCP & Electrical Plans.rvt
\AKI 820412 Centreway Villas\Details\All_Wall & Bracing Finishes Plans.bak.rvt
\AKI 820436 Heimsath Alexander\AKI820436_HeimsathAlexander.rvt
\AKI 820436 Heimsath Alexander\AKI820436_HeimsathAlexander_01.rvt
\WEA 820731 Whangamata\_Resources.rvt
\WEA 820731 Whangamata\WEA820731_A00-Site.rvt
\WEA 820731 Whangamata\WEA820731_E00-Entourage.rvt
\WEA 820731 Whangamata\WEA820731_H00-House Site.rvt
\WEA 820731 Whangamata\WEA820731_H01-House Type A-1.rvt
\WEA 820731 Whangamata\WEA820731_H02-House Type A-2.rvt
\WEA 820731 Whangamata\WEA820731_H03-House Type A-3.rvt
\WEA 820731 Whangamata\WEA820731_H04-House Type B-1.rvt
\WEA 820731 Whangamata\WEA820731_H05-House Type B-2.rvt
\WEA 820731 Whangamata\WEA820731_H06-House Type B-3.rvt
\WEA 820731 Whangamata\WEA820731_H07-House Type C-1.rvt
\WEA 820731 Whangamata\WEA820731_H08-House Type C-2.rvt
\WEA 820731 Whangamata\WEA820731_H09-House Type C-3.rvt
\WEA 820731 Whangamata\WEA820731_H10-House Type D-1.rvt
\WEA 820731 Whangamata\WEA820731_H11-House Type D-2.rvt
\WEA 820731 Whangamata\WEA820731_H12-House Type D-3.rvt
\WEA 820731 Whangamata\WEA820731_H13-House Type D-4.rvt
\WEA 820731 Whangamata\WEA820731_H14-House Type E-1.rvt
\WEA 820731 Whangamata\WEA820731_H15-House Type E-2.rvt
\WEA 820731 Whangamata\WEA820731_H16-House Type D-5.rvt
\WEA 820731 Whangamata\WEA820731_T00-Townhouse Site.rvt
\WEA 820731 Whangamata\WEA820731_T20-Townhouse Common.rvt
\WEA 820731 Whangamata\WEA820731_T21-Townhouse T-1.rvt
\WEA 820731 Whangamata\WEA820731_T22-Townhouse T-2.rvt
\WEA 820731 Whangamata\WEA820731_T23-Townhouse T-3.rvt
\WEA 820731 Whangamata\WEA820731_T24-Bungalow.rvt
"""