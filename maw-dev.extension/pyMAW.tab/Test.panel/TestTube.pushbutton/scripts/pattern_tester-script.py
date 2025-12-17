# -*- coding: utf-8 -*-
"""
Pattern Tester
"""
"""
Test script for the 'pat_lib' library.

This script imports the 'pat_lib' module from the extension's 'lib'
folder and tests the bitmap generation and saving functionality.
"""

# pyRevit Imports
from pyrevit import forms

# Standard Library Imports
import os
import traceback

# .NET Imports (for the ImageFormat, just in case)
import clr
try:
    clr.AddReference('System.Drawing')
    from System.Drawing.Imaging import ImageFormat
except Exception as e:
    forms.alert("Failed to import System.Drawing.Imaging:\n{}".format(e),
                title="Test Failed: .NET Import Error")
    raise

# --- Import the Library to be Tested ---
try:
    import pat_lib as Hatch
except ImportError as e:
    forms.alert("Failed to import 'pat_lib.py'.\n"
                "Ensure 'pat_lib.py' is in your extension's 'lib' folder.\n\n"
                "Error: {}".format(e),
                title="Test Failed: Import Error")
    raise
except Exception as e:
    forms.alert("An unknown error occurred importing 'pat_lib.py':\n{}"
                .format(traceback.format_exc()),
                title="Test Failed: Unknown Import Error")
    raise


def run_pat_lib_test():
    """
    Runs the test for parsing a PAT string and saving a bitmap.
    """
    print("--- Starting pat_lib Test ---")
    
    # 1. Define a sample .pat file content as a string
    sample_pat_data = """;%UNITS=MM
;%VERSION=3.0
;;Exported by pyMAW, based on script by Sean Page 2022
;;https://forum.dynamobim.com/t/export-fill-pattern-pat-file-from-revit/83014
;;
*BRICK230X76X10ENGLISH_SL, BRICK_230x76x10ENGLISH_SL
;%TYPE=MODEL
0.0,0.0,81.0,0.0,86.0,0.0,0.0
90.0,175.0,167.0,0.0,240.0,86.0,-86.0
90.0,115.0,81.0,0.0,120.0,86.0,-86.0
;;
*BRICK230X76X10ENGLISH, BRICK_230x76x10ENGLISH
;%TYPE=MODEL
0.0,180.0,0.0,0.0,172.0,230.0,-10.0
0.0,180.0,76.0,0.0,172.0,230.0,-10.0
0.0,120.0,86.0,0.0,172.0,110.0,-10.0
0.0,120.0,162.0,0.0,172.0,110.0,-10.0
90.0,170.0,0.0,0.0,240.0,76.0,-96.0
90.0,180.0,0.0,0.0,240.0,76.0,-96.0
90.0,110.0,86.0,0.0,120.0,76.0,-96.0
90.0,120.0,86.0,0.0,120.0,76.0,-96.0
;;
*BRICK230X76X10FLEMISH_SL, BRICK_230x76x10FLEMISH_SL
;%TYPE=MODEL
0.0,0.0,81.0,0.0,86.0,0.0,0.0
90.0,115.0,81.0,86.0,180.0,86.0,-86.0
90.0,355.0,81.0,86.0,180.0,86.0,-86.0
;;
*BRICK230X76X10FLEMISH, BRICK_230x76x10FLEMISH
;%TYPE=MODEL
0.0,180.0,0.0,180.0,86.0,110.0,-10.0,230,-10
0.0,180.0,76.0,180.0,86.0,110.0,-10.0,230,-10
90.0,170.0,0.0,86.0,180.0,76.0,-96.0
90.0,180.0,0.0,86.0,180.0,76.0,-96.0
90.0,290.0,0.0,86.0,180.0,76.0,-96.0
90.0,300.0,0.0,86.0,180.0,76.0,-96.0
;;
*BRICK230X76X10STACKED_SL, BRICK_230x76x10STACKED_SL
;%TYPE=MODEL
0.0,0.0,81.0,0.0,86.0,0.0,0.0
90.0,235.0,0.0,0.0,240.0,0.0,0.0
;;
*BRICK230X76X10STACKED, BRICK_230x76x10STACKED
;%TYPE=MODEL
0.0,0.0,0.0,0.0,86.0,230.0,-10.0
0.0,0.0,76.0,0.0,86.0,230.0,-10.0
90.0,0.0,0.0,0.0,240.0,76.0,-10.0
90.0,230.0,0.0,0.0,240.0,76.0,-10.0
;;
*BRICK230X76X10STRETCHERHALF_SL, BRICK_230x76x10STRETCHERHALF_SL
;%TYPE=MODEL
0.0,0.0,81.0,0.0,86.0,0.0,0.0
90.0,115.0,81.0,86.0,120.0,86.0,-86.0
;;
*BRICK230X76X10STRETCHERHALF, BRICK_230x76x10STRETCHERHALF
;%TYPE=MODEL
0.0,0.0,0.0,120.0,86.0,230.0,-10.0
0.0,0.0,76.0,120.0,86.0,230.0,-10.0
90.0,0.0,0.0,86.0,120.0,76.0,-96.0
90.0,230.0,0.0,86.0,120.0,76.0,-96.0
;;
*BRICK230X76X10STRETCHERTHIRD_SL, BRICK_230x76x10STRETCHERTHIRD_SL
;%TYPE=MODEL
0.0,0.0,81.0,0.0,86.0
90.0,75.0,81.0,0.0,240.0,86.0,-86.0
90.0,235.0,167.0,0.0,240.0,86.0,-86.0
;;
*BRICK230X76X10STRETCHERTHIRD, BRICK_230x76x10STRETCHERTHIRD
;%TYPE=MODEL
0.0,0.0,0.0,0.0,172.0,230.0,-10.0
0.0,0.0,76.0,0.0,172.0,230.0,-10.0
0.0,80.0,86.0,0.0,172.0,230.0,-10.0
0.0,80.0,162.0,0.0,172.0,230.0,-10.0
90.0,0.0,0.0,0.0,240.0,76.0,-96.0
90.0,230.0,0.0,0.0,240.0,76.0,-96.0
90.0,70.0,86.0,0.0,240.0,76.0,-96.0
90.0,80.0,86.0,0.0,240.0,76.0,-96.0
;;
*TILE_120x120OCTAGONAL_SL, Octagonal 120 x 120mm tiles with no grout 
;%TYPE=MODEL 
0.0,0.0,0.0,84.852787,84.852787,49.705618,-120.0
0.0,0.0,49.705618,84.852787,84.852787,49.705618,-120.0
90.0,0.0,0.0,84.852787,84.852787,49.705618,-120.0
90.0,49.705618,0.0,84.852787,84.852787,49.705618,-120.0
45.0,49.705618,49.705618,120.0,120.0,49.705618,-70.294381
-45.0,49.705618,0.0,120.0,120.0,49.705618,-70.294381
"""

    try:
        # 2. Create a parser and parse the string data
        print("Parsing pattern string...")
        patterns = Hatch.PatternSet(sample_pat_data)

        # 3. Get a the patterns
        for brick_pattern in patterns:
            print("Getting '{}' pattern...".format(brick_pattern.name))
        
            if not brick_pattern:
                forms.alert("Test failed: Could not find this pattern after parsing.",
                            title="Test Failed: Parsing Error")
                return

            # 4. Generate a bitmap
            print("Generating 200x200 bitmap with scale 0.5...")
            pen_width = 1 if '_SL' in brick_pattern.name else 1
            bmp = brick_pattern.get_bitmap(594, 511, 1.188372, pen_width = pen_width, border_width=2)
            
            # 5. Define a save path (e.g., user's Downloads folder)
            try:
                # os.path.expanduser('~/Downloads') is the most reliable way
                downloads_path = os.path.join(os.path.expanduser('~'), r'Downloads\patterns')
                if not os.path.exists(downloads_path):
                     # Fallback to user's home directory if Downloads doesn't exist
                     downloads_path = os.path.expanduser('~')
                
                save_path = os.path.join(downloads_path, "{}_play.png".format(brick_pattern.name))
            except Exception as e:
                print("Error getting save path: {}".format(e))
                # Fallback to a relative path
                save_path = "pyrevit_pat_lib_test.png"
            
            # 6. Save the bitmap to a file
            print("Saving bitmap to: {}".format(save_path))
            bmp.Save(save_path, ImageFormat.Png)
            bmp.Dispose()
        
        # 7. Report Success
        print("Test successful!")
        # forms.alert("Test Successful!\n\nBitmap saved to:\n{}".format(save_path),
                    # title="pat_lib Test Complete")

    except Exception as e:
        # 8. Report Failure
        print("--- TEST FAILED ---")
        print(traceback.format_exc())
        print("-------------------")
        forms.alert("The pat_lib test failed. See console for details.\n\n"
                    "Error: {}".format(e),
                    title="Test Failed: Runtime Error")


# --- Main execution point ---
if __name__ == '__main__':
    run_pat_lib_test()

