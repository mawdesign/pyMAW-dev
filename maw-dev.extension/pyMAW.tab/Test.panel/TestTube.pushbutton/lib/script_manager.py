# -*- coding: utf-8 -*-
import sys
import clr
import System
import os
import json
import traceback
from System.Collections.Generic import Dictionary
# Import Revit Attributes to control Transaction behavior
from Autodesk.Revit.Attributes import TransactionMode, RegenerationOption
from pyrevit import script

# Set TransactionMode to Manual. 
# This prevents pyRevit from opening a transaction, giving Dynamo full control 
# to manage its own database interactions without "API Context" errors.
__transaction__ = TransactionMode.Manual
__regeneration__ = RegenerationOption.Manual

def get_dynamo_assembly():
    """
    Iterates through loaded assemblies to find DynamoRevitDS.
    """
    domain = System.AppDomain.CurrentDomain
    assemblies = domain.GetAssemblies()
    
    for asm in assemblies:
        if "DynamoRevitDS" in asm.FullName: 
            return asm
            
    return None

def cleanup_temp_script(file_path):
    """
    Deletes the temporary Dynamo file.
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            script.journal_write("Dynamo Runner", "Cleaned up temporary file: {}".format(file_path))
    except Exception:
        sys.stderr.write("Warning: Could not delete temporary file {}.\n".format(file_path))
        traceback.print_exc()

def check_auto_dynamo_script(script_path):
    """
    Checks if the Dynamo script is set to 'Automatic' run mode.
    If 'Manual', creates a temporary copy set to 'Automatic'.
    
    Returns:
        tuple: (path_to_use, is_temporary_boolean)
    """
    try:
        with open(script_path, 'r') as f:
            data = json.load(f)
        
        # Safe navigation to the RunType node
        # Structure based on user snippet: root -> View -> Dynamo -> RunType
        view_data = data.get("View", {})
        dynamo_settings = view_data.get("Dynamo", {})
        run_type = dynamo_settings.get("RunType", "Manual") # Default to manual if key missing

        if run_type == "Automatic":
            script.journal_write("Dynamo Runner", "Script is already in Automatic mode.")
            return script_path, False
        
        script.journal_write("Dynamo Runner", "Script is in Manual mode. Creating temporary Automatic version...")
        
        # Change to Automatic
        if "View" not in data: data["View"] = {}
        if "Dynamo" not in data["View"]: data["View"]["Dynamo"] = {}
        data["View"]["Dynamo"]["RunType"] = "Automatic"

        # Generate Temp Path
        # script.get_universal_data_file creates a path in the pyRevit temp folder
        # We use the original filename prefix to make it identifiable
        filename = os.path.splitext(os.path.basename(script_path))[0]
        temp_path = script.get_universal_data_file(file_id="temp_auto_" + filename, file_ext="dyn")
        
        with open(temp_path, 'w') as f:
            json.dump(data, f)
            
        return temp_path, True

    except Exception:
        sys.stderr.write("Error checking/converting Dynamo RunType. Using original file.\n")
        traceback.print_exc()
        return script_path, False

def run_dynamo_script(script_path, journal_config_json=None):
    """
    Runs a Dynamo script using the DynamoRevit automation journal.
    
    Args:
        script_path (str): Full path to the .dyn file.
        journal_config_json (str, optional): A JSON string of key-value pairs to 
                                           override default journal settings.
                                           Example: '{"dynShowUI": "true"}'
    """
    # Safety check for the path
    if not os.path.exists(script_path):
        sys.stderr.write("Error: The Dynamo file was not found at: {}\n".format(script_path))
        return False

    script.journal_write("Dynamo Runner", "Preparing to run script: {}".format(script_path))
    
    # Check RunType and get path to use (Original vs Temp)
    path_to_run, is_temp_file = check_auto_dynamo_script(script_path)

    # Initialize cleanup in a try/finally block to ensure it happens even if Dynamo errors
    try:
        try:
            asm = get_dynamo_assembly()

            if not asm:
                raise Exception("Dynamo Assembly (DynamoRevitDS) not found. Is Dynamo installed?")

            # Using string names to get types prevents ImportErrors
            t_dynamo_revit = asm.GetType("Dynamo.Applications.DynamoRevit")
            t_command_data = asm.GetType("Dynamo.Applications.DynamoRevitCommandData")

            if not t_command_data or not t_dynamo_revit:
                raise Exception("Could not retrieve Dynamo types via Reflection.")

            # Create the CommandData instance
            cmd_data = System.Activator.CreateInstance(t_command_data)

            # Set the 'Application' property to the current Revit UIApplication
            # __revit__ is automatically provided by pyRevit context
            prop_app = t_command_data.GetProperty("Application")
            prop_app.SetValue(cmd_data, __revit__, None)

            # Create the Journal Data Dictionary
            journal_data = Dictionary[str, str]()

            # --- Default Configuration ---
            journal_data["dynShowUI"] = "false"          # Run without UI
            journal_data["dynAutomation"] = "true"       # Run without UI blocking
            journal_data["dynPath"] = path_to_run        # The path to the script (Original or Temp)
            journal_data["dynPathExecute"] = "true"      # Execute immediately
            journal_data["dynForceManualRun"] = "false"  # Don't force manual mode
            journal_data["dynModelShutDown"] = "false"   # Close when finished
            journal_data["dynModelNodesInfo"] = ""       # Log execution data to the journal

            # --- Apply Overrides ---
            if journal_config_json:
                try:
                    custom_data = json.loads(journal_config_json)
                    for key, value in custom_data.items():
                        # Ensure values are converted to strings for the C# Dictionary
                        journal_data["dyn" + key] = str(value)
                        script.journal_write("Dynamo Runner", "Overriding journal setting: {} = {}".format(key, value))
                except Exception:
                    sys.stderr.write("Warning: Failed to parse journal_config_json. Using defaults.\n")
                    traceback.print_exc()

            # Assign the dictionary to the CommandData
            prop_journal = t_command_data.GetProperty("JournalData")
            prop_journal.SetValue(cmd_data, journal_data, None)

            # Create an instance of the DynamoRevit application
            dynamo_inst = System.Activator.CreateInstance(t_dynamo_revit)

            # Get the ExecuteCommand method
            method_exec = t_dynamo_revit.GetMethod("ExecuteCommand")

            # Invoke it
            params = System.Array[object]([cmd_data])
            result = method_exec.Invoke(dynamo_inst, params)

            script.journal_write("Dynamo Runner", "Execution Result: {}".format(result))
            return result

        except Exception:
            sys.stderr.write("Critical Error running Dynamo script execution logic.\n")
            traceback.print_exc()
            return False

    finally:
        # cleanup if it was a temp file
        if is_temp_file:
            cleanup_temp_script(path_to_run)

def run_python_script(script_path):
    """
    Runs a Python script in a spoofed __main__ execution context.
    This allows the target script to run as if it were the primary file executed by pyRevit.
    
    Args:
        script_path (str): Full path to the .py file.
    """
    if not os.path.exists(script_path):
        sys.stderr.write("Error: The Python file was not found at: {}\n".format(script_path))
        return False
        
    script.journal_write("Dynamo Runner", "Executing Python Script: {}".format(script_path))
    
    try:
        # 1. Read the script content
        with open(script_path, 'r') as f:
            script_code = f.read()

        # 2. Create a copy of the current environment
        # This ensures the new script has access to __revit__, __doc__, etc.
        script_context = globals().copy()

        # 3. Force the script to think it is the main entry point
        script_context['__name__'] = "__main__"
        script_context['__file__'] = script_path
        
        # 4. Remove this module's specific functions to keep namespace clean (optional but recommended)
        # keys_to_remove = ['run_dynamo_script', 'run_python_script', 'run_script']
        # for key in keys_to_remove:
        #     if key in script_context:
        #         del script_context[key]

        # 5. Execute the code in that context
        exec(script_code, script_context)
        return True
        
    except Exception:
        sys.stderr.write("Error executing Python script {}:\n".format(script_path))
        traceback.print_exc()
        return False

def run_script(script_path, config_json=None):
    """
    Master dispatcher function. Detects file type and runs the appropriate runner.
    
    Args:
        script_path (str): Path to .dyn or .py file
        config_json (str, optional): Configuration string (Passed to Dynamo only)
    """
    if not script_path:
        sys.stderr.write("Error: No script path provided.\n")
        return False

    file_ext = os.path.splitext(script_path)[1].lower()
    
    if file_ext == ".dyn":
        return run_dynamo_script(script_path, config_json)
    elif file_ext == ".py":
        # Python scripts don't accept JSON config via this method, 
        # so we ignore config_json here.
        return run_python_script(script_path)
    else:
        sys.stderr.write("Error: Unsupported file type '{}'\n".format(file_ext))
        return False

if __name__ == "__main__":
    # --- CONFIGURATION ---
    # This block only runs when the script is executed directly (not imported)
    
    # Test path (Change this to test on your machine)
    test_file = os.path.join(os.environ['USERPROFILE'], 'Downloads', 'TestScript.dyn')
    
    # Test Config
    test_config = '{"ShowUI": "false"}'

    # Run via dispatcher
    run_script(test_file, test_config)