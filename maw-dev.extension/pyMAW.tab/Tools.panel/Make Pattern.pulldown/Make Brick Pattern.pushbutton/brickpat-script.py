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
import pattern_utils

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


# --- MATH EVALUATION FUNCTIONS ---


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


def eval_math(formula):
    # Takes a list of tokens (numbers and operators) and
    # evaluates the math.
    # First and last tokens must be numbers, and there
    # must be an operator between each number,
    # order of operations is /, *, -, +
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
    # Takes a string formula and splits into tokens: numbers, operators, nested formulae
    operators = set(["+", "-", "*", "/"])
    digits = ".0123456789"
    tokens = []
    last_type = "operator"  # i.e. not a number
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
    # Takes a string, finds formulae in brackets, and evaluates them
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
            self.brick_color = pattern_utils.db_color_from_hex(brick_color_ini)
        else:
            self.brick_color = pattern_utils.db_color_from_hex(
                "#91412F"
            )  # Default brick red

        mortar_color_ini = CONFIG.get_option("MortarColor", "not set")
        if mortar_color_ini != "not set":
            self.mortar_color = pattern_utils.db_color_from_hex(mortar_color_ini)
        else:
            self.mortar_color = pattern_utils.db_color_from_hex(
                "#ECECEC"
            )  # Default light gray

        # Set color swatch backgrounds
        self.BrickColorSwatch.Background = pattern_utils.db_color_to_wpf_brush(
            self.brick_color
        )
        self.MortarColorSwatch.Background = pattern_utils.db_color_to_wpf_brush(
            self.mortar_color
        )

        # Load thumbnails
        self.ImagePalette.ItemsSource = self.get_image_thumbnails()

        # Load diagram
        try:
            self.brick_diagram = BitmapImage(
                Uri(os.path.join(PATH_IMAGES, "brickdims.png"))
            )
            self.tile_diagram = BitmapImage(
                Uri(os.path.join(PATH_IMAGES, "tiledims.png"))
            )
            self.BrickDims.Source = self.brick_diagram
        except Exception as e:
            forms.alert("Could not load diagram images (brickdims.png, tiledims.png).")

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
            self.BrickColorLabel.Text = "Tile Colour:"
            self.MortarColorLabel.Text = "Grout Joint Colour:"
            self.BrickDims.Source = self.tile_diagram
        else:
            self.BrickColorLabel.Text = "Brick Face Colour:"
            self.MortarColorLabel.Text = "Mortar Joint Colour:"
            self.BrickDims.Source = self.brick_diagram

    def Unit_Changed(self, sender, e):
        """Fires when Metric or Imperial radio buttons are clicked."""
        self._update_ui_for_units()

    def SelectBrickColor_Click(self, sender, e):
        """Fires when the brick/tile color swatch is clicked."""
        new_color = forms.ask_for_color(default="#FF91412F")
        if new_color:
            db_color = pattern_utils.db_color_from_hex(new_color)
            if db_color and db_color.IsValid:
                self.brick_color = db_color
                # Update the swatch background
                self.BrickColorSwatch.Background = pattern_utils.db_color_to_wpf_brush(
                    db_color
                )
                # Save to config
                CONFIG.set_option("BrickColor", "#" + new_color[-6:])
                script.save_config()

    def SelectMortarColor_Click(self, sender, e):
        """Fires when the mortar/grout color swatch is clicked."""
        new_color = forms.ask_for_color(default="#FFECECEC")
        if new_color:
            db_color = pattern_utils.db_color_from_hex(new_color)
            if db_color and db_color.IsValid:
                self.mortar_color = db_color
                # Update the swatch background
                self.MortarColorSwatch.Background = pattern_utils.db_color_to_wpf_brush(
                    db_color
                )
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
        self.gen_normal = self.CheckNormal.IsChecked
        self.gen_bump = self.CheckBump.IsChecked
        self.gen_pattern = self.CheckPattern.IsChecked
        self.gen_fillregion = self.CheckFillRegion.IsChecked
        self.gen_material = self.CheckMaterial.IsChecked

        # Check unit selection and save if it changed
        if (
            self.unit_is_metric != IS_METRIC
            or CONFIG.get_option("metric", None) != IS_METRIC
        ):
            CONFIG.set_option("Metric", self.unit_is_metric)
            script.save_config()
            IS_METRIC = self.unit_is_metric  # Update global for this session

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

    # --- Generation logic ---
    if UI.DialogResult:
        # This block executes after the window is closed by "Generate"

        try:
            # --- 1. Get Selected Pattern Template ---
            selected_pattern = settings.get(UI.selected_pattern_name)
            if not selected_pattern:
                raise Exception("Could not find selected pattern data.")
            template_prefix = ";%UNITS={units}\n;%VERSION=3.0\n; Generated using pyRevit Brick Pattern Maker\n; MAW 2025\n\n"
            template = template_prefix + selected_pattern["template"]

            # --- 2. Parse Dimensions ---
            h_disp, h_int = pattern_utils.dim_from_string(
                UI.brick_height_str, IS_METRIC
            )
            w_disp, w_int = pattern_utils.dim_from_string(UI.brick_width_str, IS_METRIC)
            d_disp, d_int = pattern_utils.dim_from_string(UI.brick_depth_str, IS_METRIC)
            m_disp, m_int = pattern_utils.dim_from_string(
                UI.brick_joint_size_str, IS_METRIC
            )

            if not all([h_int, w_int, d_int, m_int]):
                raise ValueError("One or more dimensions are invalid.")

            # Create dictionary for formatting
            # The .pat templates use the display units (mm or in)
            brick_values = {
                "width": w_disp,
                "height": h_disp,
                "depth": d_disp,
                "mortar": m_disp,
                "unit": "mm" if IS_METRIC else "in",  # for naming
                "units": "MM" if IS_METRIC else "INCHES",  # for .pat %UNITS= setting
            }

            # --- 3. Generate .PAT file content ---
            pat_content = template.format(**brick_values)
            pat_content_math = do_math(pat_content)

            print("--- PATTERN CONTENT ---")
            print(pat_content_math)
            print("-----------------------")

            # --- 4. Get Naming Templates ---
            # (Placeholder for next step)
            # config = pattern_config.load_config(PATH_SCRIPT)
            # ... get templates ...

            # --- 5. Run Generation Logic (Placeholders) ---

            if UI.gen_pattern or UI.gen_fillregion or UI.gen_material:
                # TODO: Create .pat file, then create FillPatternElement
                print("TODO: Create Fill Pattern from .pat file")
                # pattern_element, reason = create_revit_fill_pattern_from_pat(...)

                if UI.gen_fillregion:
                    # TODO: Create Filled Region
                    print("TODO: Create Filled Region")
                    # success, fr_reason = pattern_utils.create_filled_region_type(...)
                    pass

            if UI.gen_normal or UI.gen_bump:
                # TODO: Get save path from user
                print("TODO: Ask for save path for images")
                # save_path = forms.save_file(...)

                if UI.gen_bump:
                    # TODO: Call bump map generator
                    print("TODO: Generate Bump Map")

                if UI.gen_normal:
                    # TODO: Call normal map generator
                    print("TODO: Generate Normal Map")

            if UI.gen_material:
                # TODO: Create material
                print("TODO: Create Material")
                # material, message = pattern_material.create_or_update_material(...)
                pass

            forms.alert(
                "Generation logic initiated. See console for details.",
                title="Generation Started",
            )

        except Exception as e:
            # Catch errors during parsing or math eval
            forms.alert(
                "An error occurred during pattern generation:\n" + str(e),
                title="Generation Error",
            )


if __name__ == "__main__":
    make_brick_pattern()
