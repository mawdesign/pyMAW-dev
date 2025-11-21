import math
import clr
import System

# .NET Imports for Bitmap Generation
clr.AddReference('System.Drawing')
from System.Drawing import Bitmap, Graphics, Pen, SolidBrush, Color, Drawing2D
from System.Drawing.Imaging import ImageFormat

# .NET Imports for WPF Bitmap Conversion
clr.AddReference('PresentationCore')
clr.AddReference('PresentationFramework')
from System.IO import MemoryStream
from System.Windows.Media.Imaging import BitmapImage, PngBitmapEncoder


class PatternLineFamily:
    """
    Represents a single line family definition from a .pat file.
    
    This class is a simple data container for one line of a pattern definition,
    describing an infinite set of parallel lines.
    """
    def __init__(self, angle, origin_x, origin_y, delta_x, delta_y, dashes):
        """
        Initializes a PatternLineFamily instance.

        Args:
            angle (float): The angle of the lines in degrees.
            origin_x (float): The x-coordinate of the origin point.
            origin_y (float): The y-coordinate of the origin point.
            delta_x (float): Perpendicular displacement between lines in the family.
            delta_y (float): Parallel displacement (stagger) between lines.
            dashes (list[float]): A list of dash/gap lengths. Positive is a line,
                                  negative is a gap, zero is a dot.
        """
        self.angle = angle
        self.origin = (origin_x, origin_y)
        self.delta = (delta_x, delta_y)
        self.dashes = dashes if dashes is not None else []

class HatchPattern:
    """
    Represents a complete hatch pattern, containing metadata and line families.
    
    This class holds the definition for a pattern (e.g., 'ANSI31') and contains
    the core logic to generate the drawing geometry for a given area.
    """
    def __init__(self, name, description):
        """
        Initializes a HatchPattern instance.

        Args:
            name (str): The name of the pattern.
            description (str): The description of the pattern.
        """
        self.name = name
        self.description = description
        self.line_families = []

    def add_line_family(self, line_family):
        """Adds a PatternLineFamily to this pattern."""
        self.line_families.append(line_family)

    def estimate_scale(self, target_size, repetitions=3.0):
        """
        Calculates a reasonable scale to make the pattern visible in a preview.

        The goal is to fit a certain number of pattern repetitions within the
        target preview size.

        Args:
            target_size (float): The size (width or height) of the preview area.
            repetitions (float): The desired number of pattern repetitions to show.

        Returns:
            float: A calculated scale factor. Returns 1.0 if no scaling is needed.
        """
        max_displacement = 0.0
        for lf in self.line_families:
            # The perpendicular displacement (delta_x) is the key to pattern size
            max_displacement = max(max_displacement, abs(lf.delta[0]))
        
        if max_displacement == 0 or repetitions == 0:
            return 1.0
            
        return target_size / (repetitions * max_displacement)

    def generate_bitmap(self, width, height, scale=None, background_color=None, line_color=None):
        """
        Generates a System.Drawing.Bitmap of the hatch pattern.

        Args:
            width (int): The desired width of the bitmap.
            height (int): The desired height of the bitmap.
            scale (float, optional): A specific scale to apply to the pattern.
                                     If None, an estimated scale will be used.
            background_color (System.Drawing.Color, optional): The background color.
                                                            Defaults to Color.White.
            line_color (System.Drawing.Color, optional): The line color.
                                                        Defaults to Color.Black.

        Returns:
            System.Drawing.Bitmap: The generated bitmap object.
        """
        # Set default colors if not provided
        if background_color is None:
            background_color = Color.White
        if line_color is None:
            line_color = Color.Black

        # Create the bitmap and graphics objects
        bmp = Bitmap(width, height)
        gfx = Graphics.FromImage(bmp)

        # Set rendering quality
        gfx.SmoothingMode = Drawing2D.SmoothingMode.AntiAlias

        # Fill the background
        gfx.Clear(background_color)

        # Create the pen for drawing lines
        pen = Pen(line_color, 1) # 1-pixel wide lines

        # Use the existing logic to get line instructions
        # We use max(width, height) to ensure the generation covers the whole area
        # even for rotated patterns.
        lines = self.generate_drawing_instructions(max(width, height), scale)

        for line in lines:
            # Draw each line onto the graphics object
            try:
                gfx.DrawLine(pen, 
                             int(round(line['x1'])), int(round(line['y1'])), 
                             int(round(line['x2'])), int(round(line['y2'])))
            except Exception as e:
                # Catch potential overflow errors if lines are excessively long
                print("Warning: Error drawing line: {}".format(e))

        # Clean up .NET objects
        pen.Dispose()
        gfx.Dispose()

        return bmp

    def convert_to_wpf_bitmap(self, bitmap):
        """
        Converts a System.Drawing.Bitmap to a WPF-compatible BitmapSource.
        This is for use in the UI preview.
        
        Args:
            bitmap (System.Drawing.Bitmap): The bitmap to convert.

        Returns:
            System.Windows.Media.Imaging.BitmapSource: A WPF-compatible image.
        """
        stream = MemoryStream()
        bitmap.Save(stream, ImageFormat.Png)
        stream.Seek(0, System.IO.SeekOrigin.Begin)
        
        wpf_bitmap = BitmapImage()
        wpf_bitmap.BeginInit()
        wpf_bitmap.StreamSource = stream
        wpf_bitmap.CacheOption = System.Windows.Media.Imaging.BitmapCacheOption.OnLoad
        wpf_bitmap.EndInit()
        wpf_bitmap.Freeze() # Important for performance and cross-thread access

        # Dispose of the bitmap and stream
        stream.Close()
        stream.Dispose()
        bitmap.Dispose()

        return wpf_bitmap

    def generate_drawing_instructions(self, square_size, scale=None):
        """
        Generates the line segments required to fill a square with this pattern.

        This is the core method that performs the geometric calculations, including
        scaling, line generation, clipping, and dashing.

        Args:
            square_size (float): The side length of the square area to fill.
            scale (float, optional): A specific scale to apply to the pattern. 
                                     If None, an estimated scale will be used.

        Returns:
            list[dict]: A list of dictionaries, where each dict represents a line
                        segment with keys 'x1', 'y1', 'x2', 'y2'.
        """
        if not self.line_families:
            return []

        if scale is None:
            scale = self.estimate_scale(square_size)

        all_lines = []
        bounds = (0, 0, square_size, square_size)

        for lf in self.line_families:
            # Apply scale to all geometric properties of the line family
            scaled_origin_x = lf.origin[0] * scale
            scaled_origin_y = lf.origin[1] * scale
            scaled_delta_x = lf.delta[0] * scale
            scaled_delta_y = lf.delta[1] * scale
            scaled_dashes = [d * scale for d in lf.dashes]

            # Convert angle to radians for math functions
            angle_rad = math.radians(lf.angle)
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)

            # Define vectors for the line direction and the displacement
            line_dir_vec = (cos_a, sin_a)
            delta_vec = (-sin_a * scaled_delta_x, cos_a * scaled_delta_x)

            # Determine the range of lines needed to cover the bounding box.
            # We project the box corners onto the vector perpendicular to the lines
            # to find the min/max distance from the origin line.
            perp_dir_vec = (-sin_a, cos_a)
            max_proj = -float('inf')
            min_proj = float('inf')
            
            corners = [(0, 0), (square_size, 0), (0, square_size), (square_size, square_size)]
            for corner in corners:
                # Vector from scaled origin to corner
                vec_to_corner = (corner[0] - scaled_origin_x, corner[1] - scaled_origin_y)
                # Project this vector onto the perpendicular direction vector
                proj = vec_to_corner[0] * perp_dir_vec[0] + vec_to_corner[1] * perp_dir_vec[1]
                min_proj = min(min_proj, proj)
                max_proj = max(max_proj, proj)
            
            # scaled_delta_x is the distance between lines
            if scaled_delta_x == 0:
                # If delta_x is 0, we only have one line to draw
                i_min, i_max = 0, 1
            else:
                # Calculate how many steps of size delta_x we need in each direction
                i_min = math.floor(min_proj / scaled_delta_x)
                i_max = math.ceil(max_proj / scaled_delta_x)

            for i in range(i_min, i_max):
                # Calculate the origin point for this specific line in the family
                start_point_x = scaled_origin_x + i * delta_vec[0]
                start_point_y = scaled_origin_y + i * delta_vec[1]

                # Apply parallel displacement (stagger)
                stagger_offset = i * scaled_delta_y
                stagger_vec = (line_dir_vec[0] * stagger_offset, line_dir_vec[1] * stagger_offset)
                start_point_x += stagger_vec[0]
                start_point_y += stagger_vec[1]
                
                # We have an infinite line defined by a point and a direction.
                # Now, we clip it to the bounding box.
                # A simple way is to find intersection points with the box edges.
                # The line equation is P = start_point + t * line_dir_vec
                
                # Define a very long line segment that is guaranteed to cross the box
                p1_x = start_point_x - line_dir_vec[0] * square_size * 2
                p1_y = start_point_y - line_dir_vec[1] * square_size * 2
                p2_x = start_point_x + line_dir_vec[0] * square_size * 2
                p2_y = start_point_y + line_dir_vec[1] * square_size * 2

                # Cohen-Sutherland clipping algorithm could be used here for efficiency,
                # but a simpler line-box intersection logic works well for this case.
                clipped_line = self._clip_line(p1_x, p1_y, p2_x, p2_y, bounds)

                if clipped_line:
                    cx1, cy1, cx2, cy2 = clipped_line
                    # Apply dash pattern to the clipped line
                    if not scaled_dashes:
                        all_lines.append({'x1': cx1, 'y1': cy1, 'x2': cx2, 'y2': cy2})
                    else:
                        all_lines.extend(self._apply_dashes(cx1, cy1, cx2, cy2, scaled_dashes))

        return all_lines

    def _clip_line(self, x1, y1, x2, y2, bounds):
        """Clips a line segment to a rectangular boundary."""
        # This is a simplified Liang-Barsky-like clipping implementation
        xmin, ymin, xmax, ymax = bounds
        dx, dy = x2 - x1, y2 - y1
        p = [-dx, dx, -dy, dy]
        q = [x1 - xmin, xmax - x1, y1 - ymin, ymax - y1]
        t0, t1 = 0.0, 1.0

        for i in range(4):
            if p[i] == 0:
                if q[i] < 0:
                    return None
            else:
                t = q[i] / p[i]
                if p[i] < 0:
                    t0 = max(t0, t)
                else:
                    t1 = min(t1, t)
        
        if t0 > t1:
            return None

        clipped_x1 = x1 + t0 * dx
        clipped_y1 = y1 + t0 * dy
        clipped_x2 = x1 + t1 * dx
        clipped_y2 = y1 + t1 * dy
        return (clipped_x1, clipped_y1, clipped_x2, clipped_y2)

    def _apply_dashes(self, x1, y1, x2, y2, dashes):
        """Applies a dash pattern to a single line segment."""
        dashed_lines = []
        dx, dy = x2 - x1, y2 - y1
        line_length = math.sqrt(dx**2 + dy**2)
        if line_length == 0:
            return []
        
        # Normalize direction vector
        ux, uy = dx / line_length, dy / line_length

        total_dash_pattern_length = sum(abs(d) for d in dashes)
        current_pos = 0.0
        
        while current_pos < line_length:
            for dash in dashes:
                is_pen_down = dash >= 0
                dash_len = abs(dash)

                if current_pos >= line_length:
                    break
                
                start_d = current_pos
                end_d = min(current_pos + dash_len, line_length)

                if is_pen_down and start_d < end_d:
                    # Don't draw zero-length dots as lines
                    if dash > 0:
                        dash_x1 = x1 + start_d * ux
                        dash_y1 = y1 + start_d * uy
                        dash_x2 = x1 + end_d * ux
                        dash_y2 = y1 + end_d * uy
                        dashed_lines.append({'x1': dash_x1, 'y1': dash_y1, 'x2': dash_x2, 'y2': dash_y2})
                
                current_pos += dash_len

        return dashed_lines

class PatParse:
    """
    Parses Autodesk .pat files into a collection of HatchPattern objects.
    """
    def __init__(self):
        """Initializes the parser with an empty pattern dictionary."""
        self.patterns = {}

    def parse_file(self, file_path):
        """
        Parses a .pat file from a given file path.

        Args:
            file_path (str): The path to the .pat file.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        with open(file_path, 'r') as f:
            content = f.read()
        self.parse_string(content)

    def parse_string(self, pat_content):
        """
        Parses the content of a .pat file from a string.

        Args:
            pat_content (str): A string containing the .pat file data.
        """
        lines = pat_content.splitlines()
        current_pattern = None

        for line in lines:
            line = line.strip()
            if not line or line.startswith(';'):
                continue
            
            if line.startswith('*'):
                # This is a header line, start of a new pattern
                parts = line[1:].split(',', 1)
                name = parts[0].strip()
                description = parts[1].strip() if len(parts) > 1 else ""
                current_pattern = HatchPattern(name, description)
                self.patterns[name] = current_pattern
            elif current_pattern:
                # This is a data line for the current pattern
                try:
                    parts = [float(p) for p in line.split(',')]
                    angle, ox, oy, dx, dy = parts[0:5]
                    dashes = parts[5:]
                    line_family = PatternLineFamily(angle, ox, oy, dx, dy, dashes)
                    current_pattern.add_line_family(line_family)
                except (ValueError, IndexError):
                    print(f"Warning: Could not parse line for pattern '{current_pattern.name}': {line}")

    def get_pattern(self, name):
        """
        Retrieves a parsed pattern by its name.

        Args:
            name (str): The name of the pattern to retrieve.

        Returns:
            HatchPattern: The corresponding HatchPattern object, or None if not found.
        """
        return self.patterns.get(name)

    def get_pattern_names(self):
        """Returns a list of all parsed pattern names."""
        return list(self.patterns.keys())

if __name__ == '__main__':
    # --- Example Usage ---
    
    # 1. Define a sample .pat file content as a string
    sample_pat_data = """
    ; This is a comment
    *ANSI31, ANSI Iron, Brick, Stone masonry
    45, 0,0, 0,0.125
    *BRICK, Standard brick pattern with mortar joints
    0, 0,0, 0,8, 16,-8
    90, 8,0, 8,8, 8,-8
    *DOTS, A simple dot pattern
    0, 0,0, 0.25,0.25, 0,-0.25
    """

    # 2. Create a parser and parse the string data
    parser = PatParse()
    parser.parse_string(sample_pat_data)

    print(f"Parsed patterns: {parser.get_pattern_names()}")

    # 3. Get a specific pattern
    brick_pattern = parser.get_pattern("BRICK")
    
    if brick_pattern:
        print(f"\n--- Generating instructions for '{brick_pattern.name}' ---")
        
        # 4. Generate drawing instructions for a 200x200 square
        
        # Option A: Let the library estimate a good scale
        print("\nUsing estimated scale:")
        auto_scaled_lines = brick_pattern.generate_drawing_instructions(square_size=200)
        print(f"Generated {len(auto_scaled_lines)} line segments.")
        # for line in auto_scaled_lines:
        #     print(line)

        # Option B: Provide a specific scale
        print("\nUsing a custom scale of 4.0:")
        custom_scaled_lines = brick_pattern.generate_drawing_instructions(square_size=200, scale=4.0)
        print(f"Generated {len(custom_scaled_lines)} line segments.")
        # for line in custom_scaled_lines:
        #     print(line)

        # --- NEW: Test Bitmap Generation ---
        print("\n--- Generating Bitmap Test ---")
        try:
            # Generate a bitmap using the custom scale
            bmp = brick_pattern.generate_bitmap(200, 200, scale=4.0)
            
            # Save it to a file
            save_path = "test_pattern_preview.png"
            bmp.Save(save_path, ImageFormat.Png)
            bmp.Dispose()
            print(f"Successfully saved test bitmap to: {save_path}")
            
            # Note: To test the WPF converter, you would need a WPF application context,
            # which is not available in this simple console test.
            
        except Exception as e:
            print(f"Error during bitmap generation: {e}")
