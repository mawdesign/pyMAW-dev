# -*- coding: utf-8 -*-
import sys
import clr
import System
import os
import json
from System.Collections.Generic import Dictionary
# Import Revit Attributes to control Transaction behavior
from Autodesk.Revit.Attributes import TransactionMode, RegenerationOption

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
        print("Error: The Dynamo file was not found at: {}".format(script_path))
        return False

    print("Preparing to run script: {}".format(script_path))

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
    journal_data["dynPath"] = script_path        # The path to the script
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
                print("Overriding journal setting: {} = {}".format(key, value))
        except Exception as e:
            print("Warning: Failed to parse journal_config_json. Using defaults. Error: {}".format(e))

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

    print("Execution Result: {}".format(result))
    return result

if __name__ == "__main__":
    # --- CONFIGURATION ---
    # This block only runs when the script is executed directly (not imported)
    demo_script_path = os.path.join(os.environ['USERPROFILE'], 'Downloads', 'RenameSheet.dyn')
    
    # Example of overriding settings: Show UI during execution
    demo_config = '{"ShowUI": "false"}'

    run_dynamo_script(demo_script_path, demo_config)
