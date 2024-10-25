# -*- coding: utf-8 -*-
# from pyrevit import script
# from pyrevit import HOST_APP
from pyrevit import revit, script, forms
import wpf, os, clr

# .NET Imports
clr.AddReference("System")
from System.Windows import Window
from System import Uri
from System.Windows.Media.Imaging import BitmapImage

PATH_SCRIPT = script.get_script_path()


class BrickForm(Window):

    def __init__(self):
        # Initialize the defaults
        self.brick_width = "230"
        self.brick_height = "76"
        self.brick_depth = "70"
        self.brick_joint_size = "10"
        self.unit_is_metric = True

        # Connect to .xaml File (in same folder)
        path_xaml_file = os.path.join(PATH_SCRIPT, "brickpat.xaml")
        wpf.LoadComponent(self, path_xaml_file)

        # Set defaults
        self.Title = "Brick Input Form"
        self.Width = 450
        self.Height = 650

        brick_dims_uri = Uri(os.path.join(PATH_SCRIPT, "brickdims.png"))
        self.BrickDims.Source = BitmapImage(brick_dims_uri)

        self.ImagePalette.ItemsSource = self.get_image_thumbnails()


        self.WidthInput.Text = self.brick_width
        self.HeightInput.Text = self.brick_height
        self.DepthInput.Text = self.brick_depth
        self.JointSizeInput.Text = self.brick_joint_size
        self.MetricRadioButton.IsChecked = self.unit_is_metric

        # Show Form
        self.ShowDialog()

    def get_image_thumbnails(self):
        """Returns a list of image thumbnail paths."""
        brick_dims_uri = Uri(os.path.join(PATH_SCRIPT, "brickdims.png"))
        return [BitmapImage(brick_dims_uri)]


    # <!-- Events --->
    def Thumbnail_MouseLeftButtonDown(self, sender, e):
        thumbnail = sender.Source
        # test
        self.SelectedImage.Source = thumbnail

    def SubmitButton_Click(self, sender, e):
        """Handles the submit button click event."""
        self.brick_height = self.HeightInput.Text
        self.brick_width = self.WidthInput.Text
        self.brick_depth = self.DepthInput.Text
        self.brick_joint_size = self.JointSizeInput.Text
        self.unit_is_metric = self.MetricRadioButton.IsChecked

        self.Close()


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


template = """;%UNITS={units}

*BRICK_{width}x{height}x{mortar}ENGLISH_SL_WM,English bond {width} x {height}mm brick with {mortar}mm mortar - single line version
;%TYPE=MODEL
0,0,({height}+{mortar}/2),0,({height}+{mortar})
90,({width}-({width}+{mortar})/4-{mortar}/2),({height}*2+{mortar}*1.5),0,({width}+{mortar}),({height}+{mortar}),-({height}+{mortar})
90,({width}/2),({height}+{mortar}/2),0,({width}/2+{mortar}/2),({height}+{mortar}),-({height}+{mortar})
"""


def make_brick_pattern():
    # `SelectImageButton_Click` and `SubmitButton_Click
    # `HeightInput`, `WidthInput`, `DepthInput`, `JointSizeInput`, and `IsMetric`

    # Show form to the user
    UI = BrickForm()

    # Get User Input
    brick = {
        "width": UI.brick_width,
        "height": UI.brick_height,
        "depth": UI.brick_depth,
        "mortar": UI.brick_joint_size,
        "units": "MM" if UI.unit_is_metric else "IMPERIAL",
    }

    # Generate pattern
    print("Selected pattern = {}".format(str(UI.SelectedImage.Source)))
    pattern = template.format(**brick)
    print(pattern)
    pattern = do_math(pattern)
    print(pattern)


if __name__ == "__main__":
    make_brick_pattern()


# import clr
# import os

# # Add reference to PresentationFramework and WindowsBase
# clr.AddReference('PresentationFramework')
# clr.AddReference('WindowsBase')

# # Import necessary WPF namespaces
# from System.Windows import Application, Window
# from System.Windows.Controls import StackPanel, TextBlock, TextBox, Button, Image, RadioButton, ItemsControl, WrapPanel
# from System.Windows.Input import MouseButtonEventArgs


class ImageSelectorForm(Window):
    def __init__(self):
        # Initialize the window
        self.Title = "Dimensions Input Form"
        self.Width = 400
        self.Height = 400
        self.Margin = 20

        # Create a StackPanel
        self.panel = StackPanel()

        # Add components to the panel
        self.setup_ui()

        # Set the content of the window
        self.Content = self.panel

    def setup_ui(self):
        # TextBlock for image selection
        self.panel.Children.Add(TextBlock(Text="Select an Image:", FontWeight="Bold"))

        # Image Palette
        self.image_palette = ItemsControl()
        self.image_palette.ItemsSource = self.get_image_thumbnails()

        # Set ItemsPanel to WrapPanel
        self.image_palette.ItemsPanel = ItemsPanelTemplate(WrapPanel())

        # Create the ItemTemplate for thumbnails
        thumbnail_template = DataTemplate()
        thumbnail_image = Image()
        thumbnail_image.Width = 50
        thumbnail_image.Height = 50
        thumbnail_image.MouseLeftButtonDown += self.thumbnail_click
        thumbnail_template.VisualTree = thumbnail_image

        self.image_palette.ItemTemplate = thumbnail_template

        self.panel.Children.Add(self.image_palette)

        # Selected Image Preview
        self.selected_image = Image(Width=100, Height=100, Margin=20)
        self.panel.Children.Add(
            TextBlock(Text="Selected Image Preview:", FontWeight="Bold")
        )
        self.panel.Children.Add(self.selected_image)

        # Dimensions Section
        self.panel.Children.Add(
            TextBlock(Text="Dimensions:", FontWeight="Bold", FontSize=16)
        )

        self.height_input = self.create_input("Height:", "100")
        self.width_input = self.create_input("Width:", "100")
        self.depth_input = self.create_input("Depth:", "50")
        self.joint_size_input = self.create_input("Joint Size:", "5")

        # Unit of Measurement
        self.panel.Children.Add(
            TextBlock(Text="Unit of Measurement:", FontWeight="Bold")
        )
        self.metric_radio = RadioButton(Content="Metric", IsChecked=True)
        self.imperial_radio = RadioButton(Content="Imperial")

        self.panel.Children.Add(self.metric_radio)
        self.panel.Children.Add(self.imperial_radio)

        # Submit Button
        self.submit_button = Button(Content="Submit")
        self.submit_button.Click += self.submit
        self.panel.Children.Add(self.submit_button)

    def create_input(self, label, default_value):
        """Creates a labeled TextBox for input."""
        stack = StackPanel(Orientation=Horizontal)
        stack.Children.Add(TextBlock(Text=label, VerticalAlignment="Center"))
        text_box = TextBox(Width=50, Margin=5)
        text_box.Text = default_value
        stack.Children.Add(text_box)
        self.panel.Children.Add(stack)
        return text_box

    def get_image_thumbnails(self):
        """Returns a list of image thumbnail paths."""
        # Here you should return the actual paths to your images
        return ["path/to/image1.jpg", "path/to/image2.jpg", "path/to/image3.jpg"]

    def thumbnail_click(self, sender, e):
        """Handles thumbnail click event to update the selected image."""
        # Update the selected image source
        thumbnail = sender.Source
        self.selected_image.Source = thumbnail.Source

    def submit(self, sender, e):
        """Handles the submit button click event."""
        # Handle the submission logic here
        height = self.height_input.Text
        width = self.width_input.Text
        depth = self.depth_input.Text
        joint_size = self.joint_size_input.Text
        is_metric = self.metric_radio.IsChecked
        is_imperial = self.imperial_radio.IsChecked

        # This is where you would process the input values
        print(
            "Height: {height}, Width: {width}, Depth: {depth}, Joint Size: {joint_size}, Metric: {is_metric}"
        )


# Entry point for the application
# if __name__ == "__main__":
# Application().Run(ImageSelectorForm())
