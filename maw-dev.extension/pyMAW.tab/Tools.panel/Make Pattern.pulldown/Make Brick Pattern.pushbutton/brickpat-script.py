# -*- coding: utf-8 -*-
# pyRevit Imports
from pyrevit import revit, script, forms, DB
from pyrevit.revit.db.transaction import Transaction

# Required Imports
import wpf, os
import glob
from pyrevit.coreutils import yaml

# Import Shared Config/Material Libraries
import pattern_config
import pattern_material

# .NET Imports
import clr
import System

clr.AddReference("System")
from System.Windows import Window
from System import Uri
from System.Windows.Media.Imaging import BitmapImage
from System.Windows.Media import SolidColorBrush, Color as MediaColor

# --- Script/Config Paths ---
PATH_SCRIPT = script.get_script_path()
PATH_IMAGES = os.path.join(PATH_SCRIPT, "images")
PATH_SETTINGS = os.path.join(PATH_SCRIPT, "brickpats.yaml")

# --- Load User Config ---
CONFIG = script.get_config("patterns")
IS_METRIC = CONFIG.get_option("Metric", True)


# --- CONVERSION FUNCTIONS ---


def db_color_to_wpf_brush(db_color):
    """Converts an Autodesk.Revit.DB.Color to a WPF.Media.Brush."""
    if not db_color or not db_color.IsValid:
        # Default to gray if invalid
        return SolidColorBrush(MediaColor.FromRgb(192, 192, 192))
    return SolidColorBrush(
        MediaColor.FromRgb(db_color.Red, db_color.Green, db_color.Blue)
    )


def db_color_from_hex(hex_color_string):
    """
    Converts a hex color string (e.g., '#FF0000' or 'FF0000') to a DB.Color object.
    """
    # Remove the '#' if it exists
    if hex_color_string.startswith("#"):
        hex_color_string = hex_color_string[1:]

    # Ensure the string is the correct length
    if len(hex_color_string) == 8:
        hex_color_string = hex_color_string[2:]  # remove alpha
    elif len(hex_color_string) != 6:
        raise ValueError("Invalid hex color string length. Expected 6 characters.")

    # Extract R, G, B components and convert them to integers
    r = int(hex_color_string[0:2], 16)
    g = int(hex_color_string[2:4], 16)
    b = int(hex_color_string[4:6], 16)

    # Create and return the DB.Color object
    return DB.Color(r, g, b)


def hex_from_db_color(db_color):
    # color_value = "#{:02X}{:02X}{:02X}".format(db_color.Red,db_color.Green,db_color.Blue)
    # isn't working with IroPyton 2.7 so ...
    r = db_color.Red
    g = db_color.Green
    b = db_color.Blue

    # Use the reliable '%' formatting style
    color_value = "#%02X%02X%02X" % (r, g, b)
    return color_value


def is_number(n):
    is_number = True
    try:
        num = float(n)
        # check for "nan" floats
        is_number = num == num
    except ValueError:
        is_number = False
    return is_number


def to_number(s):
    try:
        return int(s)
    except ValueError:
        return float(s)


# --- MATH EVALUATION FUNCTIONS ---


def eval_math(formula):
    if isinstance(formula, list) and len(formula) == 1:
        if is_number(formula[0]):
            return to_number(formula[0])
        else:
            raise Exception("Could not evaluate formula")
    elif isinstance(formula, (int, float)):
        return formula
    elif len(formula) < 3:
        raise Exception("Could not evaluate formula")
    if "+" in formula:
        operator_pos = formula.index("+")
        return eval_math(formula[:operator_pos]) + eval_math(
            formula[operator_pos + 1 :]
        )
    if "-" in formula:
        operator_pos = formula.index("-")
        return eval_math(formula[:operator_pos]) - eval_math(
            formula[operator_pos + 1 :]
        )
    if "*" in formula:
        operator_pos = formula.index("*")
        return eval_math(formula[:operator_pos]) * eval_math(
            formula[operator_pos + 1 :]
        )
    if "/" in formula:
        operator_pos = formula.index("/")
        return eval_math(formula[:operator_pos]) / eval_math(
            formula[operator_pos + 1 :]
        )
    raise Exception("Could not evaluate formula")


def eval_math_str(formula):
    # split formula into tokens: numbers, operators, nested formulae
    operators = set(["+", "-", "*", "/"])
    digits = ".0123456789"
    tokens = []
    last_type = "operator" # i.e. not a number
    curr_pos = 0
    while curr_pos < len(formula):
        c = formula[curr_pos : curr_pos + 1]
        c1 = formula[curr_pos + 1 : curr_pos + 2]
        if c == " ":
            curr_pos += 1  # skip white space
        elif c in digits or (c == "-" and c1 in digits and last_type == "operator"):
            span = 2 if c == "-" else 1
            number = formula[curr_pos : curr_pos + span]
            number_valid = True
            while number_valid:
                if is_number(
                    formula[curr_pos : curr_pos + span + 1]
                ) and curr_pos + span < len(formula):
                    span += 1
                else:
                    number_valid = False
            tokens.append(formula[curr_pos : curr_pos + span].strip())
            last_type = "number"
            curr_pos += span
        elif c in operators:
            tokens.append(c)
            last_type = "operator"
            curr_pos += 1
        elif c == "(":
            nest_level = 1
            span = 1
            while nest_level != 0:
                if c1 == "(":
                    nest_level += 1
                elif c1 == ")":
                    nest_level -= 1
                c1 = formula[curr_pos + span + 1 : curr_pos + span + 2]
                span += 1
                if curr_pos + span > len(formula):
                    raise Exception("Could not resolve nested brackets")
            # also tokenise nested formulae
            nested_formula = formula[curr_pos + 1 : curr_pos + span - 1]
            tokens.append(eval_math_str(nested_formula))
            last_type = "number"
            curr_pos += span
        else:
            curr_pos += 1

    # return if we have just a number
    if len(tokens) == 1:
        if is_number(tokens[0]):
            return to_number(tokens[0])
        else:
            raise Exception("Could not evaluate formula")
    elif len(tokens) < 3:
        raise Exception("Could not evaluate formula")

    # or evaluate the formula
    result = str(round(eval_math(tokens), 6))
    result = result.rstrip("0").rstrip(".") if "." in result else result
    return result


def do_math(text):
    level = 0
    return_text = ""
    curr_math = ""
    for t in text:
        if t == "(":
            level += 1
            curr_math += t
        elif t == ")" and level > 0:
            level -= 1
            curr_math += t
            if level == 0:
                return_text += str(eval_math_str(curr_math))
                curr_math = ""
        elif level > 0:
            curr_math += t
        else:
            return_text += t
    return return_text


# --- Revit pattern and filled region functions ---


# --- UI & Generation ---


class BrickForm(Window):
    def __init__(self, settings):
        # Initialize the defaults
        self.settings = settings
        self.selected_pattern_name = None
        self.unit_is_metric = IS_METRIC

        # Connect to .xaml File (in same folder)
        path_xaml_file = os.path.join(PATH_SCRIPT, "brickpat.xaml")
        wpf.LoadComponent(self, path_xaml_file)

        # Load material colors from pyRevit config
        brick_color_ini = CONFIG.get_option("BrickColor", "not set")
        if brick_color_ini != "not set":
            self.brick_color = db_color_from_hex(brick_color_ini)
        else:
            self.brick_color = db_color_from_hex("#91412F")  # Default brick red

        mortar_color_ini = CONFIG.get_option("MortarColor", "not set")
        if mortar_color_ini != "not set":
            self.mortar_color = db_color_from_hex(mortar_color_ini)
        else:
            self.mortar_color = db_color_from_hex("#ECECEC")  # Default light gray

        # Set color swatch backgrounds
        self.BrickColorSwatch.Background = db_color_to_wpf_brush(self.brick_color)
        self.MortarColorSwatch.Background = db_color_to_wpf_brush(self.mortar_color)

        # Load thumbnails
        self.ImagePalette.ItemsSource = self.get_image_thumbnails()

        # Load diagram
        brick_dims_uri = Uri(os.path.join(PATH_IMAGES, "brickdims.png"))
        self.BrickDims.Source = BitmapImage(brick_dims_uri)

        # Set unit selection
        self.MetricRadioButton.IsChecked = self.unit_is_metric
        self.ImperialRadioButton.IsChecked = not self.unit_is_metric
        self._update_ui_for_units()

        # Show Form
        self.ShowDialog()

    def get_image_thumbnails(self):
        """Returns a list of image thumbnail paths."""
        thumbs = [
            BrickThumb(
                {
                    "Name": pat,
                    "ToolTip": pdef["name"],
                    "Thumbnail": os.path.join(PATH_IMAGES, pdef["thumbnail"]),
                }
            )
            for pat, pdef in self.settings.items()
        ]
        return thumbs

    def _update_ui_for_units(self):
        """Updates UI text and default values based on unit system."""
        global IS_METRIC
        IS_METRIC = self.MetricRadioButton.IsChecked

        unit_suffix = "(mm)" if IS_METRIC else "(in)"
        self.DimensionsGroup.Header = "Dimensions " + unit_suffix

        # Set appropriate default values
        self.HeightInput.Text = "76" if IS_METRIC else "3"
        self.WidthInput.Text = "230" if IS_METRIC else "9"
        self.DepthInput.Text = "70" if IS_METRIC else "2.75"
        self.JointSizeInput.Text = "10" if IS_METRIC else "0.375"

    # --- Events ---
    def Thumbnail_MouseLeftButtonDown(self, sender, e):
        """Handles selection of a pattern thumbnail."""
        self.selected_pattern_name = sender.Tag
        pattern_data = self.settings.get(self.selected_pattern_name)
        if not pattern_data:
            return

        # Update preview image
        preview_path = os.path.join(PATH_IMAGES, pattern_data["preview"])
        if os.path.isfile(preview_path):
            self.SelectedImage.Source = BitmapImage(Uri(preview_path))

        # Update description
        self.SelectedTitle.Text = pattern_data["name"]
        self.SelectedDescription.Text = pattern_data["description"]

        # Update terminology (Brick vs Tile)
        if pattern_data.get("type") == "tile":
            self.BrickColorLabel.Text = "Tile Color:"
            self.MortarColorLabel.Text = "Grout Joint Color:"
        else:
            self.BrickColorLabel.Text = "Brick Face Color:"
            self.MortarColorLabel.Text = "Mortar Joint Color:"

    def Unit_Changed(self, sender, e):
        """Fires when Metric or Imperial radio buttons are clicked."""
        self._update_ui_for_units()

    def SelectBrickColor_Click(self, sender, e):
        """Fires when the brick/tile color swatch is clicked."""
        new_color = forms.ask_for_color(default="#FF91412F")
        if new_color:
            db_color = db_color_from_hex(new_color)
            if db_color and db_color.IsValid:
                self.brick_color = db_color
                # Update the swatch background
                self.BrickColorSwatch.Background = db_color_to_wpf_brush(db_color)
                # Save to config
                CONFIG.set_option("BrickColor", "#" + new_color[-6:])
                script.save_config()

    def SelectMortarColor_Click(self, sender, e):
        """Fires when the mortar/grout color swatch is clicked."""
        new_color = forms.ask_for_color(default="#FFECECEC")
        if new_color:
            db_color = db_color_from_hex(new_color)
            if db_color and db_color.IsValid:
                self.mortar_color = db_color
                # Update the swatch background
                self.MortarColorSwatch.Background = db_color_to_wpf_brush(db_color)
                # Save to config
                CONFIG.set_option("MortarColor", "#" + new_color[-6:])
                script.save_config()

    def GenerateButton_Click(self, sender, e):
        """Handles the generate button click event."""
        global IS_METRIC

        if not self.selected_pattern_name:
            forms.alert("Please select a pattern first.", title="No Pattern Selected")
            return

        # --- Read Dimension Inputs ---
        self.brick_height_str = self.HeightInput.Text
        self.brick_width_str = self.WidthInput.Text
        self.brick_depth_str = self.DepthInput.Text
        self.brick_joint_size_str = self.JointSizeInput.Text
        self.unit_is_metric = self.MetricRadioButton.IsChecked

        # --- Read Output Checkboxes (Placeholder) ---
        gen_normal = self.CheckNormal.IsChecked
        gen_bump = self.CheckBump.IsChecked
        gen_pattern = self.CheckPattern.IsChecked
        gen_fillregion = self.CheckFillRegion.IsChecked
        gen_material = self.CheckMaterial.IsChecked

        # Check unit selection and save if it changed
        if (
            self.unit_is_metric != IS_METRIC
            or CONFIG.get_option("metric", None) != IS_METRIC
        ):
            CONFIG.set_option("Metric", self.unit_is_metric)
            script.save_config()
            IS_METRIC = self.unit_is_metric  # Update global for this session

        # In a real implementation, you would now:
        # 1. Parse all dimension strings using a function like dim_from_string
        # 2. Get naming templates from pattern_config.py
        # 3. Call generation functions for images, patterns, and materials.

        print("--- Generation Started (Placeholder) ---")
        print("Units: {}".format("mm" if IS_METRIC else "in"))
        print("Selected Pattern: {}".format(self.selected_pattern_name))
        print(
            "Height: {}, Width: {}".format(self.brick_height_str, self.brick_width_str)
        )
        print("Normal Map: {}, Bump Map: {}".format(gen_normal, gen_bump))
        print("Fill Pattern: {}, Fill Region: {}".format(gen_pattern, gen_fillregion))
        print("Material: {}".format(gen_material))
        print("Brick Color: {}".format(hex_from_db_color(self.brick_color)))
        print("Mortar Color: {}".format(hex_from_db_color(self.mortar_color)))

        self.DialogResult = True
        self.Close()


class BrickThumb(object):
    """Helper class for thumbnail data binding in WPF."""

    def __init__(self, thumb):
        self.PatternName = thumb["Name"]
        self.ToolTip = thumb["ToolTip"]
        self.Thumbnail = BitmapImage(Uri(thumb["Thumbnail"]))


# --- Main execution ---


def make_brick_pattern():
    global IS_METRIC
    # Load settings from YAML
    try:
        settings = yaml.load_as_dict(PATH_SETTINGS)
    except Exception as e:
        forms.alert(
            "Error loading 'brickpats.yaml'. Make sure the file exists and is valid.\nError: "
            + str(e),
            title="Config Error",
            exitscript=True,
        )
        return

    # Show form to the user
    UI = BrickForm(settings)

    # --- Generation logic would go here, using UI results ---
    if UI.DialogResult:
        # This block executes after the window is closed by "Generate"

        # Get User Input
        brick = {
            "width": UI.brick_width_str,
            "height": UI.brick_height_str,
            "depth": UI.brick_depth_str,
            "mortar": UI.brick_joint_size_str,
            "units": "MM" if IS_METRIC else "IMPERIAL",
        }

        # Generate pattern
        template = """;%UNITS={units}

        *BRICK_{width}x{height}x{mortar}ENGLISH_SL_WM,English bond {width} x {height}mm brick with {mortar}mm mortar - single line version
        ;%TYPE=MODEL
        0,0,({height}+{mortar}/2),0,({height}+{mortar})
        90,({width}-({width}+{mortar})/4-{mortar}/2),({height}*2+{mortar}*1.5),0,({width}+{mortar}),({height}+{mortar}),-({height}+{mortar})
        90,({width}/2),({height}+{mortar}/2),0,({width}/2+{mortar}/2),({height}+{mortar}),-({height}+{mortar})
        """

        print("Selected pattern = {}".format(str(UI.SelectedImage.Source)))
        pattern = template.format(**brick)
        print(pattern)
        pattern = do_math(pattern)
        print(pattern)


if __name__ == "__main__":
    make_brick_pattern()
