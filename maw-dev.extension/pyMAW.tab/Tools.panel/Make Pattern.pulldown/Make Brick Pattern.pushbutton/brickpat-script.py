# -*- coding: utf-8 -*-
# pyRevit Imports
from pyrevit import script, forms

# Required Imports
import wpf
import os
from pyrevit.coreutils import yaml

# Import Shared Config/Material Libraries
import pattern_utils
import brick_texture
import texture_editor

# .NET Imports
import clr

clr.AddReference("System")
from System.Windows import Window, Visibility
from System import Uri
from System.Windows.Media.Imaging import BitmapImage
from System.Drawing.Imaging import ImageFormat

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
            formula[curr_pos : curr_pos + span]
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
    _ready = False  # the XAML fires events while it loads, before the form is set up

    def __init__(self, settings):
        # Initialize the defaults
        self.settings = settings
        self.selected_pattern_name = None
        self.unit_is_metric = IS_METRIC

        # Connect to .xaml File (in same folder)
        path_xaml_file = os.path.join(PATH_SCRIPT, "brickpat.xaml")
        wpf.LoadComponent(self, path_xaml_file)

        # Texture and colour settings from the pyRevit config (edited in the texture editor)
        self.tex = brick_texture.TextureSettings.load(CONFIG)
        self.is_tile = False
        self._thumb_key = None
        self._sync_colours()

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
        except Exception:
            forms.alert("Could not load diagram images (brickdims.png, tiledims.png).")

        # Set unit selection
        self.MetricRadioButton.IsChecked = self.unit_is_metric
        self.ImperialRadioButton.IsChecked = not self.unit_is_metric
        self._update_ui_for_units()
        self.update_output_state()

        # Show Form
        self._ready = True
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

    def _sync_colours(self):
        """DB colours for the material, from the hex colours in the texture settings."""
        self.brick_color = pattern_utils.db_color_from_hex(self.tex.brick_hex)
        self.mortar_color = pattern_utils.db_color_from_hex(self.tex.mortar_hex)

    def update_output_state(self):
        """Apply Texture only means something when a bump or normal map is being made."""
        self.CheckApplyTexture.IsEnabled = bool(
            self.CheckNormal.IsChecked or self.CheckBump.IsChecked
        )

    def apply_texture(self):
        return bool(self.CheckApplyTexture.IsChecked and self.CheckApplyTexture.IsEnabled)

    def dims_mm(self):
        """(width, height, joint) in mm from the inputs, or None if any is not a valid dimension."""
        mm = []
        for box in (self.WidthInput, self.HeightInput, self.JointSizeInput):
            _, internal = pattern_utils.dim_from_string(
                box.Text, bool(self.MetricRadioButton.IsChecked)
            )
            if internal is None:
                return None
            mm.append(internal * brick_texture.MM_PER_FOOT)
        return mm

    def texture_pattern(self):
        """(cell pattern, joint mm) for the selected pattern and sizes; (None, reason) if not available."""
        if not self.selected_pattern_name:
            return None, "Select a pattern"
        entry = self.settings.get(self.selected_pattern_name)
        if not brick_texture.has_cells(self.selected_pattern_name, entry):
            return None, "No texture cells for this pattern"
        dims = self.dims_mm()
        if dims is None:
            return None, "Check the dimensions"
        return brick_texture.cell_pattern(self.selected_pattern_name, entry, *dims), dims[2]

    def refresh_thumbnail(self):
        """Redraw the lit colour thumbnail for the current pattern, sizes, texture and colours."""
        if not self._ready:
            return
        key = (
            self.selected_pattern_name,
            self.WidthInput.Text,
            self.HeightInput.Text,
            self.JointSizeInput.Text,
            bool(self.MetricRadioButton.IsChecked),
            self.apply_texture(),
            tuple(sorted(self.tex.__dict__.items())),
        )
        if key == self._thumb_key:
            return
        self._thumb_key = key
        try:
            pattern, mortar_mm = self.texture_pattern()
            if pattern is None:
                self.TexturePreview.Source = None
                self.TexturePlaceholder.Text = mortar_mm
                self.TexturePlaceholder.Visibility = Visibility.Visible
                return
            bmp = brick_texture.render_thumbnail(
                pattern, self.tex, self.apply_texture(), mortar_mm
            )
            self.TexturePreview.Source = brick_texture.to_wpf_image(bmp)
            bmp.Dispose()
            self.TexturePlaceholder.Visibility = Visibility.Collapsed
        except Exception as ex:
            self._thumb_key = None
            self.TexturePreview.Source = None
            self.TexturePlaceholder.Text = "Preview failed"
            self.TexturePlaceholder.Visibility = Visibility.Visible
            print("Thumbnail error: " + str(ex))

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
        self.refresh_thumbnail()

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
        self.is_tile = pattern_data.get("type") == "tile"
        self.BrickDims.Source = self.tile_diagram if self.is_tile else self.brick_diagram
        self.refresh_thumbnail()

    def Unit_Changed(self, sender, e):
        """Fires when Metric or Imperial radio buttons are clicked."""
        self._update_ui_for_units()

    def Output_Changed(self, sender, e):
        """Fires when an output checkbox changes."""
        if not self._ready:
            return
        self.update_output_state()
        self.refresh_thumbnail()

    def Dims_Changed(self, sender, e):
        """Fires when a dimension box loses focus."""
        self.refresh_thumbnail()

    def TexturePreview_Click(self, sender, e):
        """Opens the texture editor for the selected pattern and sizes."""
        try:
            pattern, mortar_mm = self.texture_pattern()
        except Exception as ex:
            forms.alert("Could not build the pattern cells:\n" + str(ex), title="Texture")
            return
        if pattern is None:
            forms.alert(mortar_mm + ".", title="Texture")
            return
        editor = texture_editor.TextureEditor(
            pattern, mortar_mm, self.tex, self.apply_texture(), self.is_tile
        )
        if editor.show():
            self.tex = editor.settings
            self._sync_colours()
            self.tex.save(CONFIG)
            script.save_config()
            self.refresh_thumbnail()

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
        self.gen_apply_texture = self.apply_texture()

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


# --- Texture output ---


def save_bump_map(ui, entry, name_base, dims_internal):
    """Render the bump map atlas for the selected pattern and save it as a PNG."""
    if not brick_texture.has_cells(ui.selected_pattern_name, entry):
        forms.alert(
            "This pattern has no texture cell definition yet, so no bump map was made.",
            title="Bump Map",
        )
        return
    w_mm, h_mm, m_mm = [d * brick_texture.MM_PER_FOOT for d in dims_internal]
    pattern = brick_texture.cell_pattern(ui.selected_pattern_name, entry, w_mm, h_mm, m_mm)
    plan = brick_texture.make_plan(pattern, ui.tex, ui.gen_apply_texture, m_mm)

    size_w, size_h = plan.size_mm
    if not IS_METRIC:
        size_w, size_h = size_w / 25.4, size_h / 25.4
    size_name = "{:g}x{:g}{}".format(round(size_w, 2), round(size_h, 2), "mm" if IS_METRIC else "in")
    path = forms.save_file(
        file_ext="png",
        default_name="{}_bump-{}".format(name_base, size_name),
        title="Save bump map",
    )
    if not path:
        return
    bump = brick_texture.render_bump(plan, ui.tex)
    try:
        bump.Save(path, ImageFormat.Png)
    finally:
        bump.Dispose()
    print("Bump map saved: {}".format(path))
    print("Enter {} as the bump map size in the Revit material.".format(size_name))


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
    ui = BrickForm(settings)

    # --- Generation logic ---
    if ui.DialogResult:
        # This block executes after the window is closed by "Generate"

        try:
            # --- 1. Get Selected Pattern Template ---
            selected_pattern = settings.get(ui.selected_pattern_name)
            if not selected_pattern:
                raise Exception("Could not find selected pattern data.")
            template_prefix = ";%UNITS={units}\n;%VERSION=3.0\n; Generated using pyRevit Brick Pattern Maker\n; MAW 2025\n;\n"
            template = template_prefix + selected_pattern["template"]

            # --- 2. Parse Dimensions ---
            h_disp, h_int = pattern_utils.dim_from_string(
                ui.brick_height_str, IS_METRIC
            )
            w_disp, w_int = pattern_utils.dim_from_string(ui.brick_width_str, IS_METRIC)
            d_disp, d_int = pattern_utils.dim_from_string(ui.brick_depth_str, IS_METRIC)
            m_disp, m_int = pattern_utils.dim_from_string(
                ui.brick_joint_size_str, IS_METRIC
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

            if ui.gen_pattern or ui.gen_fillregion or ui.gen_material:
                # TODO: Create .pat file, then create FillPatternElement
                print("TODO: Create Fill Pattern from .pat file")
                # pattern_element, reason = create_revit_fill_pattern_from_pat(...)

                if ui.gen_fillregion:
                    # TODO: Create Filled Region
                    print("TODO: Create Filled Region")
                    # success, fr_reason = pattern_utils.create_filled_region_type(...)
                    pass

            if ui.gen_bump:
                save_bump_map(
                    ui,
                    selected_pattern,
                    "{}_{}x{}x{}".format(
                        ui.selected_pattern_name,
                        brick_values["width"],
                        brick_values["height"],
                        brick_values["mortar"],
                    ),
                    [w_int, h_int, m_int],
                )

            if ui.gen_normal:
                # TODO: Call normal map generator (same atlas as the bump map)
                print("TODO: Generate Normal Map")

            if ui.gen_material:
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
