# -*- coding: utf-8 -*-
import math
import os
import io

# --- Configuration Constants ---
# Limit the number of parallel lines to be drawn per line family.
# This prevents crashes/freezes from poorly formed PAT files (delta_x close to zero).
MAX_LINES_PER_FAMILY = 4096

# --- Data Structures for Enhanced PAT Library ---

class Line:
    """
    Represents a single line family definition from a .pat file.
    (Previously PatLine)
    """
    def __init__(self, angle, origin_x, origin_y, delta_x, delta_y, dashes):
        """
        Initializes a Line instance.

        Args:
            angle (float): The angle of the lines in degrees.
            origin_x (float): The x-coordinate of the origin point (Base Point).
            origin_y (float): The y-coordinate of the origin point (Base Point).
            delta_x (float): Perpendicular displacement (distance between lines).
            delta_y (float): Parallel displacement (stagger).
            dashes (list): Dash/gap lengths. Positive is line, negative is gap, zero is dot.
        """
        # Store angle in radians internally for math efficiency
        self._angle_rad = math.radians(angle)
        self.angle_deg = angle 
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.delta_x = delta_x
        self.delta_y = delta_y
        self.dashes = dashes if dashes is not None else []

    def get_length(self):
        """Calculates the total length of one full dash pattern repetition."""
        return sum(abs(d) for d in self.dashes)

    def scale(self, factor):
        """Scales the line family's base point, displacement, and dashes."""
        self.origin_x *= factor
        self.origin_y *= factor
        self.delta_x *= factor
        self.delta_y *= factor
        self.dashes = [d * factor for d in self.dashes]
    
    def rotate(self, angle_deg):
        """Rotates the line family's angle and base point by the given degrees."""
        angle_rad = math.radians(angle_deg)
        
        # Rotate base point
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        new_x = self.origin_x * cos_a - self.origin_y * sin_a
        new_y = self.origin_x * sin_a + self.origin_y * cos_a
        self.origin_x = new_x
        self.origin_y = new_y
        
        # Update angle
        self._angle_rad = (self._angle_rad + angle_rad) % (2 * math.pi)
        self.angle_deg = math.degrees(self._angle_rad)

    def get_svg_path_segment(self):
        """
        Generates an SVG path string for a single pattern repetition cycle.
        Returns commands like 'M 0 0 L 5 5 M 10 10 L 15 15'.
        """
        path = []
        cursor_x, cursor_y = 0.0, 0.0
        
        # Continuous line
        if not self.dashes:
            length = 10.0 # Arbitrary length for continuous line visualization
            end_x = length * math.cos(self._angle_rad)
            end_y = length * math.sin(self._angle_rad)
            return "M %s %s L %s %s" % (cursor_x, cursor_y, end_x, end_y)

        # Dashed line
        for dash in self.dashes:
            length = abs(dash)
            dx = length * math.cos(self._angle_rad)
            dy = length * math.sin(self._angle_rad)
            
            new_x = cursor_x + dx
            new_y = cursor_y + dy

            if dash > 0:
                # Positive dash: Line segment
                if not path:
                    # Start with a MoveTo command if this is the first segment
                    path.append("M %s %s" % (cursor_x, cursor_y))
                path.append("L %s %s" % (new_x, new_y))
            elif dash < 0:
                # Negative dash: Gap, move pen up and reposition
                path.append("M %s %s" % (new_x, new_y))

            cursor_x, cursor_y = new_x, new_y

        return " ".join(path)

class Pattern:
    """
    Represents a complete hatch pattern.
    """
    def __init__(self, name, description, is_metric, pattern_type = "Drafting"):
        """
        Initializes a Pattern instance.

        Args:
            name (str): The name of the pattern.
            description (str): The description of the pattern.
            is_metric (bool): True if pattern definition uses metric units.
            pattern_type (str): Revit pattern type ("Drafting" or "Model").
        """
        self.name = name
        self.description = description
        self.is_metric = is_metric
        self.pattern_type = pattern_type
        self.lines = [] # List of Line objects

    def add_line(self, line):
        """Adds a Line to this pattern."""
        self.lines.append(line)

    def scale(self, factor):
        """Scales all line families in the pattern."""
        for line in self.lines:
            line.scale(factor)

    def rotate(self, angle_deg):
        """Rotates all line families in the pattern by the given degrees."""
        for line in self.lines:
            line.rotate(angle_deg)

    def estimate_scale(self, target_size, repetitions = 3.0):
        """
        Calculates a scale factor to fit a certain number of pattern repetitions
        within the target preview size.
        """
        max_displacement = 0.0
        for lf in self.lines:
            max_displacement = max(max_displacement, abs(lf.delta_x))
        
        if max_displacement == 0 or repetitions == 0:
            return 1.0
            
        return target_size / (repetitions * max_displacement)


    def generate_drawing_instructions(self, width, height = None, scale = None, rotation_deg = 0.0):
        """
        Generates the line segments required to fill a rectangle with this pattern.
        
        Args:
            width (float): The width of the rectangular area.
            height (float, optional): The height of the rectangular area. Defaults to width (square).
            scale (float, optional): A specific scale to apply to the pattern.
            rotation_deg (float, optional): An additional rotation applied to the entire pattern.

        Returns:
            list: A list of dictionaries [{'x1':..., 'y1':..., 'x2':..., 'y2':...}].
        """
        if not self.lines:
            return []

        if height is None:
            height = width
            
        max_size = max(width, height)
        current_scale = scale if scale is not None else self.estimate_scale(max_size)

        # 1. Create a temporary deep copy to apply session-specific transformations
        # This is a manual copy for IronPython 2.7 compatibility.
        temp_pattern = Pattern(self.name, self.description, self.is_metric, self.pattern_type)
        for lf in self.lines:
            # Copy all primitive fields and the dashes list
            temp_line = Line(lf.angle_deg, lf.origin_x, lf.origin_y, lf.delta_x, lf.delta_y, lf.dashes[:])
            temp_pattern.add_line(temp_line)

        # 2. Apply session-specific rotation and scale to the temporary pattern
        if rotation_deg != 0.0:
            temp_pattern.rotate(rotation_deg)
        if current_scale != 1.0:
            temp_pattern.scale(current_scale)

        # The bounding box is always axis-aligned from (0,0) to (width, height)
        all_lines = []
        bounds = (0, 0, width, height)

        for lf in temp_pattern.lines:
            # Retrieve transformed properties from the temporary Line object
            scaled_dx = lf.delta_x
            scaled_dy = lf.delta_y
            scaled_dashes = lf.dashes
            angle_rad = lf._angle_rad
            origin_x, origin_y = lf.origin_x, lf.origin_y # Transformed base point

            # Define vectors for line direction and perpendicular displacement
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)
            line_dir_vec = (cos_a, sin_a)
            delta_vec = (-sin_a * scaled_dx, cos_a * scaled_dx)
            
            # --- Geometric Projection to determine iteration range (i_min, i_max) ---
            
            perp_dir_vec = (-sin_a, cos_a)
            max_proj = -float('inf')
            min_proj = float('inf')
            
            # Project all four corners of the rectangular bounding box onto the perpendicular vector
            corners = [(0, 0), (width, 0), (0, height), (width, height)]
            
            for corner_x, corner_y in corners:
                # Vector from transformed origin to corner
                vec_to_corner = (corner_x - origin_x, corner_y - origin_y)
                # Projection: dot product
                proj = vec_to_corner[0] * perp_dir_vec[0] + vec_to_corner[1] * perp_dir_vec[1]
                min_proj = min(min_proj, proj)
                max_proj = max(max_proj, proj)
            
            # Calculate iteration bounds
            i_min, i_max = 0, 1 # Default if delta_x is zero
            if scaled_dx != 0:
                i_min = math.floor(min_proj / scaled_dx)
                i_max = math.ceil(max_proj / scaled_dx)
            
            # Apply safety limit
            if i_max - i_min > MAX_LINES_PER_FAMILY:
                i_max = i_min + MAX_LINES_PER_FAMILY
                print "Warning: Line family '%s' hit max line limit of %s." % (lf.angle_deg, MAX_LINES_PER_FAMILY)


            for i in range(int(i_min), int(i_max)):
                # Calculate the start point of this specific line iteration
                start_point_x = origin_x + i * delta_vec[0]
                start_point_y = origin_y + i * delta_vec[1]

                # Apply parallel displacement (stagger)
                stagger_offset = i * scaled_dy
                stagger_vec = (line_dir_vec[0] * stagger_offset, line_dir_vec[1] * stagger_offset)
                start_point_x += stagger_vec[0]
                start_point_y += stagger_vec[1]
                
                # --- Clipping ---
                # Define a very long line segment guaranteed to cross the box
                long_length = max_size * 2 # Use max_size to ensure coverage
                p1_x = start_point_x - line_dir_vec[0] * long_length
                p1_y = start_point_y - line_dir_vec[1] * long_length
                p2_x = start_point_x + line_dir_vec[0] * long_length
                p2_y = start_point_y + line_dir_vec[1] * long_length

                clipped_line = self._clip_line(p1_x, p1_y, p2_x, p2_y, bounds)

                if clipped_line:
                    cx1, cy1, cx2, cy2 = clipped_line
                    
                    if not scaled_dashes:
                        # Continuous line
                        all_lines.append({'x1': cx1, 'y1': cy1, 'x2': cx2, 'y2': cy2})
                    else:
                        # Dashed line: Delegate the dashing to a method
                        all_lines.extend(self._get_dashed_segments(cx1, cy1, cx2, cy2, scaled_dashes))

        return all_lines

    def get_bitmap(self, width, height, scale=None, background_color=None, pen_width = 1, line_color=None):
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

        # .NET Imports for Bitmap Generation
        # Only import if bitmap requested
        # .NET Imports
        import clr
        clr.AddReference('System.Drawing')
        from System.Drawing import Bitmap, Graphics, Pen, SolidBrush, Color, Drawing2D
        from System.Drawing.Imaging import ImageFormat

        # .NET Imports for WPF Bitmap Conversion
        clr.AddReference('PresentationCore')
        clr.AddReference('PresentationFramework')
        from System.IO import MemoryStream
        from System.Windows.Media.Imaging import BitmapImage, PngBitmapEncoder

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
        pen = Pen(line_color, pen_width) # 1-pixel wide lines

        # Use the vector logic to get line instructions
        lines = self.generate_drawing_instructions(width, height, scale)

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

    def _clip_line(self, x1, y1, x2, y2, bounds):
        """Clips a line segment to a rectangular boundary using Liang-Barsky-like logic."""
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

    def _get_dashed_segments(self, x1, y1, x2, y2, dashes):
        """
        Applies a dash pattern to a single line segment and returns the visible parts.
        """
        dashed_lines = []
        dx, dy = x2 - x1, y2 - y1
        line_length = math.sqrt(dx**2 + dy**2)
        if line_length == 0:
            return []
        
        # Normalize direction vector
        if line_length > 0:
            ux, uy = dx / line_length, dy / line_length
        else:
            return []

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

class PatternSet:
    """
    Parses Autodesk .pat files into an ordered collection of Pattern objects.
    (Previously PatParser)
    """
    def __init__(self, source=None):
        """Initializes the parser with an empty pattern list and name map."""
        self.patterns = []    # Stores Pattern objects in file order
        self.name_map = {}    # Maps name string to Pattern object
        if source is not None:
            self.parse(source)

    def __iter__(self):
        """Allows iteration over the patterns in the order they were parsed."""
        return iter(self.patterns)
        
    def __len__(self):
        """Returns the number of parsed patterns."""
        return len(self.patterns)
        
    def __getitem__(self, name):
        """Allows accessing patterns by name (dictionary-style lookup)."""
        return self.name_map.get(name)

    def parse(self, source):
        """
        Parses hatch patterns from a string, filepath, or stream.

        Args:
            source (str or file-like object): The content to parse. Can be a 
                                              file path, a string containing PAT data,
                                              or an open file/stream object.
            is_metric (bool): True if pattern definition uses metric units.
        """
        content_stream = None
        
        if isinstance(source, basestring):
            if os.path.exists(source):
                # File path provided
                try:
                    content_stream = open(source, 'r')
                except Exception, e:
                    print "Error opening file %s: %s" % (source, str(e))
                    return
            else:
                # Content string provided
                content_stream = io.StringIO(source)
        elif hasattr(source, 'read'):
            # Stream/file-like object provided
            content_stream = source
        else:
            print "Invalid source type for parsing."
            return

        self._parse_stream(content_stream)
        
        # If we opened a file, close it
        if isinstance(source, basestring) and os.path.exists(source):
            content_stream.close()

    def _parse_stream(self, content_stream):
        """Internal method to parse data from a stream."""
        # Read all lines into a list to support multi-pass processing (look-ahead)
        all_lines = [line.strip() for line in content_stream if line.strip()]
        
        # --- 1. Determine File-level Unit (is_metric) ---
        is_metric = False # Default to Imperial
        
        # Only check control lines at the very beginning of the file
        for line in all_lines:
            if line.upper().startswith(';%UNITS=MM'):
                is_metric = True
                break
            # Stop looking for unit if we hit the first header line
            if line.startswith('*'):
                break

        # --- 2. Parse Patterns ---
        current_pattern = None
        current_type = None

        # Reset pattern collections for a fresh parse
        self.patterns = []
        self.name_map = {}

        for line in all_lines:
            if current_pattern and not current_type and line.upper().startswith(';TYPE='):
                line_part = line.upper()[6:]
                current_type = "Model" if line_part.startswith('MODEL') else 'Drafting'
                continue

            if line.startswith(';'):
                continue
            
            if line.startswith('*'):
                # This is a header line, start of a new pattern
                parts = line[1:].split(',', 1)
                name = parts[0].strip()
                
                description = parts[1].strip() if len(parts) > 1 else ""
                pattern_type = current_type if current_type else 'Drafting'

                current_pattern = Pattern(name, description, is_metric, pattern_type)
                
                # Add to ordered list and name map
                self.patterns.append(current_pattern)
                self.name_map[name] = current_pattern
                current_type = None # reset for next pattern
                
            elif current_pattern:
                # This is a data line for the current pattern
                try:
                    # Filter out empty strings from split() before converting to float
                    parts_str = [p.strip() for p in line.split(',')]
                    parts = [float(p) for p in parts_str if p]
                    
                    if len(parts) < 5:
                        print "Warning: Skipping incomplete line in pattern '%s': %s" % (current_pattern.name, line)
                        continue
                        
                    angle, ox, oy, dx, dy = parts[0:5]
                    dashes = parts[5:]
                    line_family = Line(angle, ox, oy, dx, dy, dashes)
                    current_pattern.add_line(line_family)
                except Exception, e:
                    print "Warning: Could not parse line for pattern '%s': %s (Error: %s)" % (current_pattern.name, line, str(e))

    def get_pattern(self, name):
        """Retrieves a parsed pattern by its name (alias for self[name])."""
        return self.name_map.get(name)

    def get_pattern_names(self):
        """Returns a list of all parsed pattern names in order."""
        return [p.name for p in self.patterns]