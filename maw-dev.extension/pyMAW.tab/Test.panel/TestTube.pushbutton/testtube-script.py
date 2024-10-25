# -*- coding: UTF-8 -*-

# from pyrevit import HOST_APP
# from pyrevit import revit
# from pyrevit import DB, UI
from pyrevit import forms

# from pyrevit.revit import query
# from pyrevit.framework import List
# from pyrevit.revit import Transaction
# from pyrevit.revit.db.transaction import Transaction
# from pyrevit.revit import create
# from pyrevit import script
# from pyrevit import EXEC_PARAMS
# from rpws import RevitServer
# import os
# import json
# import xlrd
# import re
# import sys


# create a python function to extract a vector outline from a black and white image

"""
Creating a vector outline from a black and white image involves several 
steps, including image processing to detect edges and then vectorizing 
those edges. One popular library for image processing in Python is OpenCV, 
and for vector graphics, you can use libraries like `svgwrite` or `shapely`.

Here’s a step-by-step function that uses OpenCV to detect edges and then 
converts those edges to a vector format using `svgwrite`.

First, make sure you have the necessary libraries installed:
```sh
pip install opencv-python-headless numpy svgwrite
```

Now, here's the Python function to extract a vector outline from a black 
and white image:
"""
import cv2
import numpy as np
import svgwrite


def extract_vector_outline(image_path, output_svg_path):
    # Load the image
    image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

    # Check if the image is loaded properly
    if image is None:
        raise ValueError(f"Image at path {image_path} could not be loaded.")

    # Detect edges using Canny edge detector
    edges = cv2.Canny(image, 100, 200)

    # Find contours from the edges
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Create an SVG drawing
    dwg = svgwrite.Drawing(output_svg_path, profile="tiny")

    # Add contours to the SVG drawing
    for contour in contours:
        # Convert contour to a list of tuples
        points = [(point[0][0], point[0][1]) for point in contour]
        # Add the contour as a polyline to the SVG drawing
        dwg.add(dwg.polyline(points, stroke=svgwrite.rgb(0, 0, 0, "%"), fill="none"))

    # Save the SVG file
    dwg.save()


# Example usage
extract_vector_outline("input_image.png", "output_vector.svg")
"""
### Explanation:
1. **Loading the Image**: The function reads the image in grayscale mode 
using `cv2.imread()`.
2. **Edge Detection**: The `cv2.Canny()` function is used to detect edges 
in the image. The thresholds (100 and 200) can be adjusted based on the 
image characteristics.
3. **Finding Contours**: The `cv2.findContours()` function retrieves the 
contours from the edge-detected image. `cv2.RETR_EXTERNAL` retrieves only 
the external contours, and `cv2.CHAIN_APPROX_SIMPLE` compresses horizontal, 
vertical, and diagonal segments and leaves only their end points.
4. **Creating SVG**: The `svgwrite` library is used to create an SVG file. 
Each contour is added as a polyline to the SVG drawing.
5. **Saving the SVG**: The `dwg.save()` function saves the SVG file to the 
specified path.

This function should work for most simple black and white images to extract 
vector outlines. For more complex images or specific use cases, additional 
processing steps might be required.

To extract a vector outline from a black and white image in Python, you can 
use libraries like OpenCV for image processing and NumPy for handling 
arrays. The process typically involves the following steps:

1. Load the image.
2. Convert it to grayscale (if it isn't already).
3. Apply edge detection to find the outlines.
4. Use contour detection to extract the vector outline.
5. Optionally, draw the contours on a blank canvas.

Here's a simple implementation of these steps:

"""
import cv2
import numpy as np


def extract_vector_outline(image_path, output_path):
    # Load the image
    image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

    # Check if the image is loaded properly
    if image is None:
        raise ValueError("Image not found or unable to load.")

    # Apply GaussianBlur to reduce noise and improve edge detection
    blurred = cv2.GaussianBlur(image, (5, 5), 0)

    # Use Canny edge detection to find edges
    edges = cv2.Canny(blurred, 50, 150)

    # Find contours from the edges
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Create a blank image to draw contours
    outline_image = np.zeros_like(image)

    # Draw contours on the blank image
    cv2.drawContours(outline_image, contours, -1, (255), thickness=cv2.FILLED)

    # Save the output image
    cv2.imwrite(output_path, outline_image)

    return contours  # Returning contours for further processing if needed


# Example usage
if __name__ == "__main__":
    input_image_path = "path_to_your_image.jpg"
    output_image_path = "output_vector_outline.png"

    contours = extract_vector_outline(input_image_path, output_image_path)
    print(f"Extracted {len(contours)} contours.")
"""

### Explanation:
- **Loading the Image**: The image is loaded in grayscale mode.
- **Gaussian Blur**: This step helps reduce noise which can affect edge 
detection.
- **Canny Edge Detection**: This algorithm detects edges in the image.
- **Contour Detection**: Contours are detected from the edges.
- **Drawing Contours**: The contours are drawn on a blank image.
- **Saving the Result**: The result is saved as a new image file.

### Requirements:
Make sure you have the required libraries installed. You can install them 
using pip:

```bash
pip install opencv-python numpy
```

### Note:
- Adjust the parameters in `Canny` and `GaussianBlur` for different images 
to get better results.
- This function assumes that the input image is a black-and-white image. If 
you have a colored image, you may need to convert it to grayscale first.

Certainly! A flood fill algorithm is often used in image processing to 
determine the area connected to a given node in a multi-dimensional array. 
Below is a Python function that implements the flood fill algorithm using 
recursion. This function takes an image (as a 2D list or a NumPy array) and 
a starting point (x, y) and returns a mask indicating the filled area.

Here's a simple implementation using NumPy:

```python
import numpy as np
"""


def flood_fill(image, start_point, target_color=None):
    """
    Perform a flood fill on the image starting from the start_point.

    Parameters:
        image (numpy.ndarray): The input image as a 2D array.
        start_point (tuple): The (x, y) coordinates to start the flood fill.
        target_color (int or tuple): The color to fill with. If None, it 
            will fill with the color of the start point.

    Returns:
        numpy.ndarray: A mask indicating the filled area.
    """
    # Get the dimensions of the image
    height, width = image.shape[:2]

    # Get the color at the start point
    x, y = start_point
    if target_color is None:
        target_color = image[x, y]

    # Create a mask to keep track of the filled areas
    mask = np.zeros_like(image, dtype=bool)

    # Define the flood fill function
    def fill(x, y):
        # Check if the current position is out of bounds
        if x < 0 or x >= height or y < 0 or y >= width:
            return
        # Check if the current position is already filled or not the target color
        if mask[x, y] or not np.array_equal(image[x, y], target_color):
            return

        # Fill the current position
        mask[x, y] = True

        # Recursively fill in all four directions
        fill(x + 1, y)  # Down
        fill(x - 1, y)  # Up
        fill(x, y + 1)  # Right
        fill(x, y - 1)  # Left

    # Start the flood fill
    fill(x, y)

    return mask


# Example usage
if __name__ == "__main__":
    # Create a sample image (3x3 with different colors)
    image = np.array([[1, 1, 0], [1, 0, 0], [0, 0, 0]])

    start_point = (1, 1)  # Starting point for flood fill
    mask = flood_fill(image, start_point)

    print("Original Image:")
    print(image)
    print("Flood Fill Mask:")
    print(mask)
"""

### Explanation:
- The `flood_fill` function initializes the flood fill process by checking 
the color of the starting point.
- It uses a nested `fill` function to perform the recursive filling. It 
checks boundaries and whether the pixel has already been filled or matches 
the target color.
- The mask is a boolean array of the same shape as the input image, where 
`True` indicates a filled pixel.

### Note:
- The function assumes that the input image is in a format that can be 
represented as a 2D array (e.g., grayscale or binary). If working with 
colored images, you might need to adapt the color comparison accordingly.
- For large images or deep recursion, consider implementing an iterative 
approach to avoid stack overflow issues.

Creating a paint fill (also known as flood fill) algorithm in Python can be 
accomplished using various libraries, such as OpenCV or PIL (Pillow). Below 
is an example of how you can implement a flood fill algorithm using the 
OpenCV library. This function will take an image and a point (x, y) as 
input and fill the area with a specified color.

First, ensure you have OpenCV installed. You can install it using pip if 
you haven't done so:

```bash
pip install opencv-python
```

Here's the code for the flood fill function:

"""
import cv2
import numpy as np


def flood_fill(image_path, point, fill_color):
    # Read the image
    image = cv2.imread(image_path)

    # Check if the image is loaded
    if image is None:
        print("Error: Could not read the image.")
        return None

    # Convert the fill color from RGB to BGR (OpenCV uses BGR format)
    fill_color = (
        fill_color[2],
        fill_color[1],
        fill_color[0],
    )  # Convert from RGB to BGR

    # Get the coordinates of the point
    x, y = point

    # Perform the flood fill operation
    # Use the flags cv2.FLOODFILL_MASK_ONLY to create a mask
    mask = np.zeros((image.shape[0] + 2, image.shape[1] + 2), np.uint8)
    cv2.floodFill(image, mask, (x, y), fill_color)

    # Save or display the result
    cv2.imshow("Flood Fill Result", image)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    return image


# Example usage
if __name__ == "__main__":
    image_path = "path/to/your/image.jpg"  # Specify the path to your image
    point = (100, 100)  # Specify the point (x, y) where the flood fill should start
    fill_color = (255, 0, 0)  # Specify the fill color in RGB (red in this case)

    flood_fill(image_path, point, fill_color)
"""

### Explanation:
- **Image Loading**: The function reads an image from the specified path 
using `cv2.imread`.
- **Fill Color**: The fill color is converted from RGB to BGR since OpenCV 
uses the BGR format.
- **Flood Fill**: The `cv2.floodFill` function is used to fill the area 
starting from the specified point. It creates a mask to manage the area 
that will be filled.
- **Display**: The resulting image is displayed in a window.

### Usage:
- Replace `'path/to/your/image.jpg'` with the path to your image file.
- Adjust the `point` variable to the pixel coordinates where you want to 
start the fill.
- Change the `fill_color` to your desired RGB color.

### Note:
Make sure that the point you provide is within the bounds of the image. If 
the point is outside the image, the function will not work correctly.
"""

"""
Creating a filled region in Revit using an SVG outline involves several 
steps, including parsing the SVG file, converting its coordinates to 
Revit's coordinate system, and then creating the filled region. pyRevit can 
help in automating these steps. Below you will find a step-by-step example 
of how to achieve this.

Ensure you have pyRevit installed and set up, and you are familiar with 
basic Revit API concepts.

### Step-by-Step Guide

1. **Install SVG Parser Package**:
   You will be using `svgpathtools` to parse the SVG file and extract the 
path coordinates. Ensure you have it installed.
   ```sh
   pip install svgpathtools
   ```

2. **pyRevit Script**:
   Here is a complete script to create a filled region from an SVG outline:

"""
import clr

clr.AddReference("RevitAPI")
clr.AddReference("RevitServices")
clr.AddReference("RevitNodes")
clr.AddReference("RevitAPIUI")
clr.AddReference("Revit")
clr.AddReference("System")

from Autodesk.Revit.DB import *
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager
from svgpathtools import svg2paths
from System.Collections.Generic import List
import os

# Get the current document
doc = DocumentManager.Instance.CurrentDBDocument

# Load the SVG file and extract paths
svg_file_path = r"path_to_your_svg_file.svg"
paths, attributes = svg2paths(svg_file_path)


# Function to convert SVG path to Revit CurveArray
def convert_svg_to_revit_curves(svg_path, scale=1.0):
    curves = List[Curve]()
    for segment in svg_path:
        start = XYZ(segment.start.real * scale, segment.start.imag * scale, 0)
        end = XYZ(segment.end.real * scale, segment.end.imag * scale, 0)
        if isinstance(segment, svgpathtools.Line):
            line = Line.CreateBound(start, end)
            curves.Add(line)
        elif isinstance(segment, svgpathtools.CubicBezier):
            control1 = XYZ(
                segment.control1.real * scale, segment.control1.imag * scale, 0
            )
            control2 = XYZ(
                segment.control2.real * scale, segment.control2.imag * scale, 0
            )
            bezier = HermiteSpline.Create([start, control1, control2, end], False)
            curves.Add(bezier)
    return curves


# Convert the first path to Revit curves
if paths:
    revit_curves = convert_svg_to_revit_curves(paths[0])

# Create a filled region in Revit
TransactionManager.Instance.EnsureInTransaction(doc)

filled_region_type = (
    FilteredElementCollector(doc).OfClass(FilledRegionType).FirstElement()
)
view = doc.ActiveView
new_filled_region = FilledRegion.Create(
    doc, filled_region_type.Id, view.Id, revit_curves
)

TransactionManager.Instance.TransactionTaskDone()

print("Filled region created from SVG outline.")
"""

### Important Points:
- **Path Parsing**: This script uses the `svgpathtools` library to parse 
the SVG file and extract path data.
- **Coordinate Conversion**: The `convert_svg_to_revit_curves` function 
converts each SVG segment to a Revit curve.
- **Transaction Management**: Transactions are used to ensure safe and 
atomic operations in Revit.
- **Filled Region Type**: The script retrieves a filled region type from 
the document; you may need to adjust this to match your specific 
requirements.

### How to Run:
1. Save this script in the pyRevit `extensions` directory.
2. Change the `svg_file_path` to the path of your SVG file.
3. Load the script into Revit through pyRevit and run it.

This basic example assumes the SVG consists of simple line and cubic Bezier 
segments. More complex SVG features might require additional handling and 
translation to Revit's API.
"""


def main():
    doc = revit.doc
    app = __revit__.Application
    fam = doc.FamilyManager
    text = ""

    # get shared parameters
    sharedParams = {}
    sharedParamFile = app.OpenSharedParameterFile()
    for sg in sharedParamFile.Groups:
        sgName = sg.Name
        for sp in sg.Definitions:
            if sp.Description:
                sharedParams[sp.Name] = sp
                text += "[{}] {}\r\n;{}\r\n".format(sp.Name, sp.GUID, sp.Description)
    forms.alert(text)


if EXEC_PARAMS.config_mode:
    # Settings (shift-click)
    forms.alert("Boo")
else:
    main()

# This script performs flood fill as before, but after filling the region, it uses the findContours function to find the
# outlines of the filled region. The outlines are returned as a list of contours.

# Please note that this function will return multiple contours if the filled region is non-convex or consists of 
# multiple connected components. You may want to choose one or process all of them as per your requirement.

import cv2
import numpy as np

# Assuming the input is a binary image.
def flood_fill_and_outline(img, point):
    h, w = img.shape[:2]
    mask = np.zeros((h + 2, w + 2), np.uint8)

    # Perform flood fill
    cv2.floodFill(img, mask, point, 255, 0, 0, flags=4 | cv2.FLOODFILL_FIXED_RANGE)

    # Find the contours of the filled region
    contours, hierarchy = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    return contours

# Usage:
img = np.zeros((500, 500, 3), np.uint8)
point = (200, 200)
contours = flood_fill_and_outline(img, point)