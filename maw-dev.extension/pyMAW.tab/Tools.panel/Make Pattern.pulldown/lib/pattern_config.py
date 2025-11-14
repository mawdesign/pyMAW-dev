# -*- coding: utf-8 -*-
"""
Shared library for handling pattern generation configuration.

Reads and writes to a 'pattern_settings.ini' file and provides
a simple editor UI.
"""

# pyRevit Imports
from pyrevit import forms

# Required Imports
import wpf
import os
import clr
import ConfigParser
from StringIO import StringIO  # Use Python 2.7 native StringIO

# .NET Imports
clr.AddReference("System")
from System.Windows import Window
from System.IO import MemoryStream, SeekOrigin  # Added for .NET stream
from System.Text import Encoding  # Added for .NET stream
from System.Windows.Media import SolidColorBrush, Color  # Added for UI feedback

# --- DEFAULT NAMING TEMPLATES (MASTER LIST) ---
# This dictionary contains defaults for ALL tools
DEFAULT_TEMPLATES = {
    # Roofing Patterns
    "Roofing Patterns": {
        "corrugated_normal_map": "Corrugate-{spacing}x{height}_normal_{size}mm",
        "corrugated_bump_map": "Corrugate-{spacing}x{height}_bump_{size}mm",
        "corrugated_pattern_name": "Corrugate {spacing}x{height}",
        "corrugated_region_name": "Corrugate {spacing}x{height}",
        "corrugated_material_name": "Roofing - Corrugate {spacing}x{height}",
        "trapezoidal_normal_map": "Trapezoidal-{rib_width}x{height}@{spacing}_normal_{size}mm",
        "trapezoidal_bump_map": "Trapezoidal-{rib_width}x{height}@{spacing}_bump_{size}mm",
        "trapezoidal_pattern_name": "Trapezoidal {rib_width}x{height}@{spacing}",
        "trapezoidal_region_name": "Trapezoidal {rib_width}x{height}@{spacing}",
        "trapezoidal_material_name": "Roofing - Trapezoidal {rib_width}x{height}@{spacing}",
        "ribbed_normal_map": "Standing Seam-{thickness}x{height}@{spacing}_normal_{size}mm",
        "ribbed_bump_map": "Standing Seam-{thickness}x{height}@{spacing}_bump_{size}mm",
        "ribbed_pattern_name": "Standing Seam {thickness}x{height}@{spacing}",
        "ribbed_region_name": "Standing Seam {thickness}x{height}@{spacing}",
        "ribbed_material_name": "Roofing - Standing Seam {thickness}x{height}@{spacing}",
    },
    # Brick Patterns (Placeholder for when you add them)
    "Brick Patterns": {
        "stretcher_normal_map": "Brick-Stretcher-{width}x{height}_normal_{size}mm",
        "stretcher_bump_map": "Brick-Stretcher-{width}x{height}_bump_{size}mm",
        "stretcher_pattern_name": "Brick Stretcher {width}x{height}",
        "stretcher_region_name": "Brick Stretcher {width}x{height}",
    },
}

CONFIG_FILE_NAME = "pattern_settings.ini"


def _find_config_path(script_path):
    """
    Finds the config file in the script's folder or one level up.
    Returns (path_to_config_file, is_general) or (None, None)
    """
    specific_path = os.path.join(script_path, CONFIG_FILE_NAME)
    general_path = os.path.abspath(os.path.join(script_path, "..", CONFIG_FILE_NAME))

    if os.path.exists(specific_path):
        return specific_path, False
    elif os.path.exists(general_path):
        return general_path, True
    else:
        return None, None


def load_config(script_path):
    """Loads naming templates from 'pattern_settings.ini'."""
    config = ConfigParser.ConfigParser()
    config_path, _ = _find_config_path(script_path)

    if config_path:
        try:
            config.read(config_path)
        except Exception as e:
            forms.alert(
                "Error reading config file, falling back to defaults. \nFile: {}\nError: ".format(
                    config_path
                )
                + str(e),
                title="Error reading config file",
            )
            return None  # Will trigger fallback
    return config


def get_template(config, section, key):
    """
    Gets a specific naming template from the config,
    or falls back to the default.
    """
    if config and config.has_section(section) and config.has_option(section, key):
        return config.get(section, key)
    else:
        # Fallback to defaults
        if section in DEFAULT_TEMPLATES and key in DEFAULT_TEMPLATES[section]:
            return DEFAULT_TEMPLATES[section][key]
        else:
            return "DefaultName"  # Final fallback


def _generate_ini_text(sections_to_include):
    """
    Generates INI-formatted text for the given sections from defaults.
    """
    s_io = StringIO()  # Use the imported StringIO
    if not sections_to_include:  # If empty, include all
        sections_to_include = DEFAULT_TEMPLATES.keys()

    for section in sections_to_include:
        if section in DEFAULT_TEMPLATES:
            s_io.write("[{}]\n".format(section))
            for key, value in DEFAULT_TEMPLATES[section].items():
                s_io.write("{} = {}\n".format(key, value))
            s_io.write("\n")
    return s_io.getvalue()


class ConfigEditorWindow(Window):
    """
    A simple WPF window to edit the .ini file contents.
    """

    def __init__(self, xaml_file_stream, initial_text, save_path):
        wpf.LoadComponent(self, xaml_file_stream)  # Load from stream object

        # --- Store colors ---
        self.white_brush = SolidColorBrush(Color.FromRgb(255, 255, 255))
        self.pink_brush = SolidColorBrush(Color.FromRgb(255, 220, 220))  # Light Pink

        # --- Set initial state ---
        self.config_text.Text = initial_text
        self._save_path = save_path
        self.FeedbackBorder.Background = self.white_brush
        self.FeedbackText.Text = "Editing: " + self._save_path

        self.ShowDialog()

    @property
    def saved_text(self):
        return self.config_text.Text if self.DialogResult else None

    def save_config(self, sender, e):
        """Validate, save, and close."""
        text_content = self.config_text.Text
        parser = ConfigParser.RawConfigParser()
        try:
            # Try to parse the text to validate it
            # Use StringIO and encode to utf-8 for the 2.7 parser
            parser.readfp(StringIO(text_content.encode("utf-8")))

            # Validation passed, save the file
            with open(self._save_path, "w") as f:
                f.write(text_content.encode("utf-8"))

            # Validation passed, close the window
            self.DialogResult = True
            self.Close()

        except ConfigParser.Error as ex:
            # --- Config Parse Error ---
            # DO NOT CLOSE. Show error in feedback bar.
            self.FeedbackBorder.Background = self.pink_brush
            self.FeedbackText.Text = "Invalid INI Format: " + str(ex)

        except Exception as ex:
            # --- Other Error (e.g., File I/O) ---
            # DO NOT CLOSE. Show error in feedback bar.
            self.FeedbackBorder.Background = self.pink_brush
            self.FeedbackText.Text = "Error: " + str(ex)

    def cancel(self, sender, e):
        """Cancel and close."""
        self.DialogResult = False
        self.Close()


def edit_config(script_path, section_name):
    """
    Opens an editor for the 'pattern_settings.ini' file.
    """
    # Define the XAML for the editor window
    XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Pattern Naming Config Editor" Height="600" Width="600"
        WindowStartupLocation="CenterScreen" WindowStyle="ToolWindow">
    <Grid Margin="10">
        <Grid.RowDefinitions>
            <RowDefinition Height="*" />   <!-- Row 0: TextBox -->
            <RowDefinition Height="Auto" /> <!-- Row 1: Feedback -->
            <RowDefinition Height="Auto" /> <!-- Row 2: Buttons -->
        </Grid.RowDefinitions>
        
        <TextBox Name="config_text"
                 Grid.Row="0"
                 AcceptsReturn="True"
                 VerticalScrollBarVisibility="Auto"
                 HorizontalScrollBarVisibility="Auto"
                 FontFamily="Consolas"
                 FontSize="12" />
        
        <!-- NEW FEEDBACK BAR -->
        <Border Name="FeedbackBorder"
                Grid.Row="1"
                Margin="0,10,0,0"
                Padding="5"
                BorderThickness="1"
                BorderBrush="Gray"
                Background="White">
            <TextBlock Name="FeedbackText"
                       Text="Editing..."
                       TextWrapping="Wrap" />
        </Border>
                 
        <StackPanel Grid.Row="2" Orientation="Horizontal" 
                    HorizontalAlignment="Right" Margin="0,10,0,0">
            <Button Content="Save" Width="80" Margin="0,0,10,0"
                    IsDefault="True" Click="save_config" />
            <Button Content="Cancel" Width="80"
                    IsCancel="True" Click="cancel" />
        </StackPanel>
    </Grid>
</Window>
"""
    config_path, is_general = _find_config_path(script_path)
    save_path = ""
    initial_text = ""

    if config_path:
        # File exists, load it
        try:
            with open(config_path, "r") as f:
                initial_text = f.read().decode("utf-8")
            save_path = config_path
        except Exception as e:
            forms.alert("Could not read config file: " + str(e), title="File Error")
            return
    else:
        # File does not exist, ask user what to do
        forms.alert("No File")
        option = forms.CommandSwitchWindow.show(
            [
                "Create Specific Config (in this button's folder)",
                "Create General Config (in folder above)",
                "Cancel",
            ],
            message="'pattern_settings.ini' was not found. What would you like to do?",
        )

        if option == "Create Specific Config (in this button's folder)":
            initial_text = _generate_ini_text([section_name])
            save_path = os.path.join(script_path, CONFIG_FILE_NAME)
        elif option == "Create General Config (in folder above)":
            initial_text = _generate_ini_text(None)  # All sections
            save_path = os.path.abspath(
                os.path.join(script_path, "..", CONFIG_FILE_NAME)
            )
        else:
            return  # User cancelled

    # --- Load XAML from a .NET stream ---
    # Convert the Python string to a .NET MemoryStream
    xaml_bytes = Encoding.UTF8.GetBytes(XAML)
    xaml_stream = MemoryStream(xaml_bytes)
    xaml_stream.Seek(0, SeekOrigin.Begin)

    # Show the editor window
    # Pass the .NET stream, not a string or StringIO
    editor = ConfigEditorWindow(xaml_stream, initial_text, save_path)
