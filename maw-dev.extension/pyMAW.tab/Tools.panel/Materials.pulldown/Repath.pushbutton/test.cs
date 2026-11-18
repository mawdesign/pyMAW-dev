// Visual Studio 2022 Configuration Requirements

// To compile this without references breaking or generating execution errors, 
// use these exact parameters when constructing your project:

// 1. Project Template: Choose Console App (.NET Framework). 
// 2. Target Framework: Select .NET Framework 4.8 from the dropdown. Do not 
//    choose standard .NET Core / .NET 5+, as they parse COM interops 
//    differently without a complex wrapper.
// 3. Add Reference: 
//    * Click *Project > Add Reference... > Browse*.
//    * Navigate to your Inventor 2024 installation directory (typically 
//      `C:\Program Files\Autodesk\Inventor 2024\Bin\Public Assemblies\`).
//    * Select `Autodesk.Inventor.Interop.dll`.
// 4. Modify Reference Properties (Critical):
//    * Expand the References tree inside your Solution Explorer.
//    * Left-click `Autodesk.Inventor.Interop`.
//    * Look at your Properties window panel and verify that Embed Interop 
//      Types is set to `False`. *(If left as True, your application will throw 
//      an invalid cast runtime exception when passing assets back and forth).*

using System;
using System.IO;
using System.Runtime.InteropServices;
using Inventor;

namespace InventorMaterialManager
{
    class Program
    {
        static void Main(string[] args)
        {
            Console.Title = "Autodesk Material Library (.adsklib) Manager";
            
            // 1. Establish the target library path (via args or fallback)
            string libraryPath = @"C:\YourCompanyData\Materials\CustomMaterials.adsklib";
            if (args.Length > 0)
            {
                libraryPath = args[0];
            }

            if (!File.Exists(libraryPath))
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine($"Error: Target file not found at '{libraryPath}'");
                Console.ResetColor();
                Console.WriteLine("Press any key to exit...");
                Console.ReadKey();
                return;
            }

            Console.WriteLine($"Target Library: {libraryPath}");
            Console.WriteLine("Initializing Autodesk Inventor 2024 Engine...");

            Inventor.Application invApp = null;
            bool createdNewInstance = false;
            PartDocument tempDoc = null;

            try
            {
                // 2. Connect to or launch a full headless instance of Inventor 2024
                try
                {
                    invApp = (Inventor.Application)Marshal.GetActiveObject("Inventor.Application");
                    Console.WriteLine("Connected to an active, running instance of Inventor.");
                }
                catch
                {
                    Type invType = Type.GetTypeFromProgID("Inventor.Application");
                    invApp = (Inventor.Application)Activator.CreateInstance(invType);
                    invApp.Visible = false; // Keep it headless/hidden in the background
                    createdNewInstance = true;
                    Console.WriteLine("Launched a hidden background instance of Inventor.");
                }

                // 3. Create a scratchpad document required for editing assets
                tempDoc = (PartDocument)invApp.Documents.Add(
                    DocumentTypeEnum.kPartDocumentObject,
                    invApp.FileManager.GetTemplateFile(DocumentTypeEnum.kPartDocumentObject),
                    true
                );

                // 4. Open the material library file
                AssetLibrary customLib = invApp.AssetLibraries.Open(libraryPath);
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine($"Successfully loaded library: {customLib.DisplayName}\n");
                Console.ResetColor();

                // ========================================================
                // TASK A: READ MATERIAL & APPEARANCE DATA
                // ========================================================
                Console.WriteLine("--- ANALYSING APPEARANCE ASSETS ---");
                foreach (Asset appearance in customLib.AppearanceAssets)
                {
                    Console.ForegroundColor = ConsoleColor.Cyan;
                    Console.WriteLine($"\nAppearance Asset: {appearance.DisplayName}");
                    Console.ResetColor();
                    Console.WriteLine($"  Name (Internal Id): {appearance.Name}");
                    Console.WriteLine($"  Category: {appearance.Category?.DisplayName ?? "Root"}");
                    Console.WriteLine($"  HasTexture: {appearance.HasTexture}");
                    Console.WriteLine($"  IsReadOnly: {appearance.IsReadOnly}");
                    Console.WriteLine("  Properties:");

                    // Safely iterate down into the underlying properties
                    foreach (AssetValue val in appearance)
                    {
                        PrintAssetValue(val, 4);
                    }
                }

                // ========================================================
                // TASK B: ADD A NEW MATERIAL
                // ========================================================
                Console.WriteLine("\n--- ADDING NEW MATERIAL ---");
                string newMaterialName = "My Custom Nylon 2024";
                
                // Construct the asset inside our document scratchpad first
                Asset newDocMaterial = tempDoc.Assets.Add(
                    AssetTypeEnum.kAssetTypeMaterial,
                    "Generic",
                    "Internal_Nylon_Unique_Key",
                    newMaterialName
                );
                
                // Save it down to the library
                Asset newLibMaterial = newDocMaterial.CopyTo(customLib);
                Console.WriteLine($"Added material '{newMaterialName}' to the library.");

                // ========================================================
                // TASK C: EDIT AN EXISTING MATERIAL
                // ========================================================
                Console.WriteLine("\n--- EDITING EXISTING MATERIAL ---");
                if (customLib.MaterialAssets.Count > 0)
                {
                    // Pull an asset down to our document scratchpad to make it editable
                    Asset libMaterialToEdit = customLib.MaterialAssets[newMaterialName];
                    Asset localCopy = libMaterialToEdit.CopyTo(tempDoc, true);

                    // Modify a visual metadata field
                    localCopy.DisplayName = "My Custom Nylon 2024 - Revised";

                    // Save the changed data back down to the library, overwriting the old one (true)
                    localCopy.CopyTo(customLib, true);
                    Console.WriteLine("Successfully modified and saved material revisions back to library.");
                }

            }
            catch (Exception ex)
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine($"\nRuntime Error: {ex.Message}");
                Console.ResetColor();
            }
            finally
            {
                // 5. Meticulous cleanup to avoid leaving orphaned background instances
                if (tempDoc != null)
                {
                    try { tempDoc.Close(true); } catch { }
                }

                if (invApp != null && createdNewInstance)
                {
                    Console.WriteLine("\nClosing background Inventor engine cleanly...");
                    try { invApp.Quit(); } catch { }
                }

                // Release COM pointers immediately
                if (invApp != null)
                {
                    Marshal.ReleaseComObject(invApp);
                }

                Console.WriteLine("\nOperation finished. Press any key to close window.");
                Console.ReadKey();
            }
        }

        private static void PrintAssetValue(AssetValue val, int indentLevel)
        {
            string indent = new string(' ', indentLevel);
            
            try
            {
                switch (val.ValueType)
                {
                    case AssetValueTypeEnum.kAssetValueTypeString:
                        StringAssetValue strVal = (StringAssetValue)val;
                        Console.WriteLine($"{indent}• {val.Name} [String]: \"{strVal.Value}\"");
                        break;

                    case AssetValueTypeEnum.kAssetValueTypeBoolean:
                        BooleanAssetValue boolVal = (BooleanAssetValue)val;
                        Console.WriteLine($"{indent}• {val.Name} [Boolean]: {boolVal.Value}");
                        break;

                    case AssetValueTypeEnum.kAssetValueTypeInteger:
                        IntegerAssetValue intVal = (IntegerAssetValue)val;
                        Console.WriteLine($"{indent}• {val.Name} [Integer]: {intVal.Value}");
                        break;

                    case AssetValueTypeEnum.kAssetValueTypeFloat:
                        FloatAssetValue floatVal = (FloatAssetValue)val;
                        Console.WriteLine($"{indent}• {val.Name} [Float]: {floatVal.Value}");
                        break;

                    case AssetValueTypeEnum.kAssetValueTypeColor:
                        ColorAssetValue colorVal = (ColorAssetValue)val;
                        Color color = colorVal.Value;
                        Console.WriteLine($"{indent}• {val.Name} [Color]: R:{color.Red}, G:{color.Green}, B:{color.Blue}");
                        break;

                    case AssetValueTypeEnum.kAssetValueTypeFilename:
                        FilenameAssetValue fileVal = (FilenameAssetValue)val;
                        Console.WriteLine($"{indent}• {val.Name} [FilePath]: {fileVal.Value}");
                        break;

                    case AssetValueTypeEnum.kAssetValueTypeTexture:
                        TextureAssetValue textureVal = (TextureAssetValue)val;
                        Asset textureAsset = textureVal.Value;
                        Console.WriteLine($"{indent}• {val.Name} [Linked Texture Asset]: {textureAsset.DisplayName}");
                        
                        // Recursive check down into texture maps (e.g. mapping scales, offsets)
                        foreach (AssetValue subVal in textureAsset)
                        {
                            PrintAssetValue(subVal, indentLevel + 4);
                        }
                        break;

                    case AssetValueTypeEnum.kAssetValueTypeChoice:
                        ChoiceAssetValue choiceVal = (ChoiceAssetValue)val;
                        choiceVal.GetChoice(out string activeChoice, out _);
                        Console.WriteLine($"{indent}• {val.Name} [Choice]: Selection => {activeChoice}");
                        break;

                    default:
                        Console.WriteLine($"{indent}• {val.Name} [{val.ValueType}]: (Complex Structure)");
                        break;
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"{indent}• {val.Name} [Error parsing value: {ex.Message}]");
            }
        }
    }
}