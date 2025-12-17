# -*- coding: utf-8 -*-
import math
import os
import io

# --- Configuration Constants ---
# Limit the number of parallel lines to be drawn per line family.
# This prevents crashes/freezes from poorly formed PAT files (delta_v close to zero).
MAX_LINES_PER_FAMILY = 4096

# --- Data Structures for Enhanced PAT Library ---


class Line:
    """
    Represents a single line family definition from a .pat file using Local Vector Basis.
    """

    def __init__(self, angle, origin_x, origin_y, delta_u, delta_v, dashes):
        """
        Initializes a Line instance.

        Args:
            angle (float): The angle of the lines in degrees.
            origin_x (float): The x-coordinate of the origin point (Base Point).
            origin_y (float): The y-coordinate of the origin point (Base Point).
            delta_u (float): Displacement parallel to the line angle.
            delta_v (float): Displacement perpendicular to the line angle.
            dashes (list): Dash/gap lengths. Positive is line, negative is gap, zero is dot.
        """
        # Store angle in radians internally for math efficiency
        self._angle_rad = math.radians(angle)
        self.angle_deg = angle
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.delta_u = delta_u
        self.delta_v = delta_v
        self.dashes = dashes if dashes is not None else []

    @property
    def vec_u(self):
        """Returns the unit vector parallel to the line: (cos(a), sin(a))."""
        return (math.cos(self._angle_rad), math.sin(self._angle_rad))

    @property
    def vec_v(self):
        """Returns the unit vector perpendicular to the line: (-sin(a), cos(a))."""
        return (-math.sin(self._angle_rad), math.cos(self._angle_rad))

    def get_family_offset(self):
        """
        Calculates the global offset vector to the next line in the family.
        Logic: Offset = (delta_v * vec_v) + (delta_u * vec_u)
        """
        u = self.vec_u
        v = self.vec_v

        # Offset vector calculation based on local basis
        off_x = round(self.delta_u * u[0] + self.delta_v * v[0], 8)
        off_y = round(self.delta_u * u[1] + self.delta_v * v[1], 8)

        return (off_x, off_y)

    def get_length(self):
        """Calculates the total length of one full dash pattern repetition."""
        return sum(abs(d) for d in self.dashes)

    def scale(self, factor):
        """Scales the line family's base point, displacement, and dashes."""
        self.origin_x *= factor
        self.origin_y *= factor
        self.delta_u *= factor
        self.delta_v *= factor
        self.dashes = [d * factor for d in self.dashes]

    def rotate(self, angle_deg):
        """Rotates the line family's angle and base point by the given degrees."""
        angle_rad = math.radians(angle_deg)

        # Rotate base point around (0,0)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        new_x = self.origin_x * cos_a - self.origin_y * sin_a
        new_y = self.origin_x * sin_a + self.origin_y * cos_a
        self.origin_x = new_x
        self.origin_y = new_y

        # Update angle (Basis vectors vec_u/vec_v update automatically via property)
        self.angle_deg = (self.angle_deg + angle_deg) % 360.0
        self._angle_rad = math.radians(self.angle_deg)


class Pattern:
    """
    Represents a complete hatch pattern.
    """

    def __init__(self, name, description, is_metric, pattern_type="Drafting"):
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
        self.lines = []  # List of Line objects

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

    def estimate_scale(self, target_size, repetitions=5.0):
        """
        Calculates a scale factor based primarily on perpendicular spacing (delta_v).
        """
        max_spacing = 0.0
        max_length = 0.0
        for lf in self.lines:
            # Use delta_v (perp spacing) and total dash length for scale estimation
            max_spacing = max(max_spacing, abs(lf.delta_v))
            max_length = max(max_length, lf.get_length())

        if max_spacing == 0 or repetitions == 0:
            print("Scale: 1.0 (max space = {})".format(max_spacing))
            return 1.0

        # Ensure at least one full repetition
        scale = target_size / max((repetitions * max_spacing), max_length)
        # print("Scale: {}".format(scale))
        return scale

    def generate_drawing_instructions(
        self, width, height=None, scale=None, rotation_deg=0.0
    ):
        """
        Generates the line segments required to fill a rectangle with this pattern.
        Uses local vector basis logic to ensure consistent texture mapping.
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

        # 1. Create a temporary copy to apply session-specific transformations
        temp_pattern = Pattern(
            self.name, self.description, self.is_metric, self.pattern_type
        )
        for lf in self.lines:
            # Copy properties to new instance
            temp_line = Line(
                lf.angle_deg,
                lf.origin_x,
                lf.origin_y,
                lf.delta_u,
                lf.delta_v,
                lf.dashes[:],
            )
            temp_pattern.add_line(temp_line)

        # 2. Apply session-specific rotation and scale
        if rotation_deg != 0.0:
            temp_pattern.rotate(rotation_deg)
        if current_scale != 1.0:
            temp_pattern.scale(current_scale)

        all_lines = []
        bounds = (0, 0, width, height)
        corners = [(0, 0), (width, 0), (0, height), (width, height)]

        for lf in temp_pattern.lines:
            # --- Vector Basis Logic ---
            u = lf.vec_u
            v = lf.vec_v
            fam_offset = lf.get_family_offset()

            # --- 3. Determine Line Family Range (k_min to k_max) ---
            # We project the bounding box onto the V-axis (perpendicular axis).
            # The line 'k' is located at distance: (Origin . V) + k * delta_v

            # Project box corners onto V
            v_projections = [c[0] * v[0] + c[1] * v[1] for c in corners]
            min_v_proj = min(v_projections)
            max_v_proj = max(v_projections)

            # Project Origin onto V
            origin_v = lf.origin_x * v[0] + lf.origin_y * v[1]

            # Calculate range of k indices that intersect the V-projection of the box
            if abs(lf.delta_v) < 1e-9:
                # Delta V is zero: all lines are collinear or it's a single line.
                # Render just the base line (k=0).
                k_min, k_max = 0, 0
            else:
                # Solve for k: min_v <= origin_v + k * delta_v <= max_v
                val1 = (min_v_proj - origin_v) / lf.delta_v
                val2 = (max_v_proj - origin_v) / lf.delta_v
                k_min = math.floor(min(val1, val2))
                k_max = math.ceil(max(val1, val2))

            # Safety clamp for massive number of lines
            if (k_max - k_min) > MAX_LINES_PER_FAMILY:
                k_max = k_min + MAX_LINES_PER_FAMILY
                # print "Warning: Hit max lines limit."

            # --- 4. Generate Segments for each line k ---
            for k in range(int(k_min), int(k_max) + 1):
                # Calculate "Pattern Origin" (P_k) for this specific line.
                # This point is where the dash pattern starts (t=0) for line k.
                # P_k = Origin + k * FamilyOffset
                pk_x = lf.origin_x + k * fam_offset[0]
                pk_y = lf.origin_y + k * fam_offset[1]

                # --- Parametric Clipping ---
                # We define the line as P(t) = P_k + t * U
                # We find the 't' values where this line enters and exits the box (0,0,W,H).
                # Inequalities:
                #   0 <= Pkx + t*ux <= Width
                #   0 <= Pky + t*uy <= Height

                t_enter = -float("inf")
                t_exit = float("inf")

                # Check X bounds
                if abs(u[0]) < 1e-9:
                    # Vertical line
                    if pk_x < 0 or pk_x > width:
                        continue  # Outside X bounds
                else:
                    t1 = (0 - pk_x) / u[0]
                    t2 = (width - pk_x) / u[0]
                    t_enter = max(t_enter, min(t1, t2))
                    t_exit = min(t_exit, max(t1, t2))

                # Check Y bounds
                if abs(u[1]) < 1e-9:
                    # Horizontal line
                    if pk_y < 0 or pk_y > height:
                        continue  # Outside Y bounds
                else:
                    t1 = (0 - pk_y) / u[1]
                    t2 = (height - pk_y) / u[1]
                    t_enter = max(t_enter, min(t1, t2))
                    t_exit = min(t_exit, max(t1, t2))

                # If valid segment found
                if t_enter <= t_exit:
                    if not lf.dashes:
                        # Continuous line
                        x1 = pk_x + t_enter * u[0]
                        y1 = pk_y + t_enter * u[1]
                        x2 = pk_x + t_exit * u[0]
                        y2 = pk_y + t_exit * u[1]
                        all_lines.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2})
                    else:
                        # Dashed line
                        # Pass t_enter/t_exit relative to P_k so dashes align correctly
                        segments = self._get_dashed_segments_basis(
                            pk_x, pk_y, u, t_enter, t_exit, lf.dashes
                        )
                        all_lines.extend(segments)

        return all_lines

    def _get_dashed_segments_basis(self, px, py, u, t_start, t_end, dashes):
        """
        Generates dashed segments along vector u starting from P(px, py).

        Crucial: 't' represents distance from the Pattern Origin P_k, not the screen edge.
        This ensures the texture doesn't 'swim' when the window is resized.
        """
        segments = []
        loop_len = sum(abs(d) for d in dashes)
        if loop_len == 0:
            return []

        current_t = t_start

        while current_t < t_end:
            # Determine phase in the dash cycle
            # (current_t % loop_len) works correctly in Python even for negative numbers
            cycle_phase = current_t % loop_len

            # Find which dash in the definition covers this phase
            dist_in_cycle = 0.0
            active_dash_idx = 0

            for idx, dash in enumerate(dashes):
                dash_len = abs(dash)
                if dist_in_cycle + dash_len > cycle_phase:
                    active_dash_idx = idx
                    break
                dist_in_cycle += dash_len

            # Calculate how much of the current dash is remaining
            offset_in_dash = cycle_phase - dist_in_cycle
            dash_val = dashes[active_dash_idx]
            dash_len = abs(dash_val)
            rem_dash = dash_len - offset_in_dash

            # Step size is the smaller of: remaining dash OR distance to end of visible line
            dist_to_end = t_end - current_t
            step = min(rem_dash, dist_to_end)

            # Draw if dash is positive (pen down)
            if dash_val > 0 and step > 1e-9:
                x1 = px + current_t * u[0]
                y1 = py + current_t * u[1]
                x2 = px + (current_t + step) * u[0]
                y2 = py + (current_t + step) * u[1]
                segments.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2})

            current_t += step
            # Epsilon nudge to prevent infinite loops on tiny float errors
            if step < 1e-9:
                current_t += 1e-9

        return segments

    def get_bitmap(
        self,
        width,
        height,
        scale=None,
        background_color=None,
        pen_width=1,
        line_color=None,
        border_width=0,
        border_color=None,
    ):
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
            System.Drawing.Bitmap: The generated bitmap object."""
        # .NET Imports
        # Only import if bitmap requested
        import clr

        try:
            clr.AddReference("System.Drawing")
            from System.Drawing import (
                Bitmap,
                Graphics,
                Pen,
                SolidBrush,
                Color,
                Drawing2D,
            )
        except:
            print("System.Drawing not available.")
            return None

        # Set default colors if not provided
        if background_color is None:
            background_color = Color.White
        if line_color is None:
            line_color = Color.Black

        bmp = Bitmap(width, height)
        gfx = Graphics.FromImage(bmp)
        gfx.SmoothingMode = Drawing2D.SmoothingMode.AntiAlias
        gfx.Clear(background_color)
        pen = Pen(line_color, pen_width)
        y_origin = height - 1

        lines = self.generate_drawing_instructions(width, height, scale)

        for line in lines:
            try:
                gfx.DrawLine(
                    pen,
                    int(round(line["x1"])),
                    int(round(y_origin - line["y1"])),
                    int(round(line["x2"])),
                    int(round(y_origin - line["y2"])),
                )
            except Exception as e:
                pass

        # Draw border
        if border_width > 0:
            # Set the graphics settings for no anti-aliasing (pixel-perfect drawing)
            gfx.SmoothingMode = Drawing2D.SmoothingMode.None
            gfx.PixelOffsetMode = Drawing2D.PixelOffsetMode.None

            rect_x = border_width // 2
            rect_y = border_width // 2
            rect_width = width - border_width
            rect_height = height - border_width

            if border_color is None:
                border_color = line_color
            pen = Pen(border_color, float(border_width))
            border_width = 2.0*(border_width - 1)
            try:
                gfx.DrawRectangle(
                    pen,
                    rect_x, rect_y, rect_width, rect_height,
                )
            except Exception as e:
                pass

        # Clean up .NET objects
        pen.Dispose()
        gfx.Dispose()
        return bmp


class PatternSet:
    """
    Parses Autodesk .pat files into an ordered collection of Pattern objects.
    """

    def __init__(self, source=None):
        """Initializes the parser with an empty pattern list and name map."""
        self.patterns = []
        self.name_map = {}
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
        should_close = False

        if isinstance(source, basestring):
            if os.path.exists(source):
                content_stream = open(source, "r")
                should_close = True
            else:
                content_stream = io.StringIO(source)
        elif hasattr(source, "read"):
            content_stream = source
        else:
            print("Invalid source type for parsing.")
            return

        self._parse_stream(content_stream)

        if should_close:
            content_stream.close()

    def _parse_stream(self, content_stream):
        """Internal method to parse data from a stream."""
        # Read all lines into a list to support multi-pass processing (look-ahead)
        all_lines = [line.strip() for line in content_stream if line.strip()]

        # Only check control lines at the very beginning of the file
        is_metric = False
        for line in all_lines:
            if line.upper().startswith(";%UNITS=MM"):
                is_metric = True
                break
            if line.startswith("*"):
                break

        current_pattern = None
        current_type = None

        self.patterns = []
        self.name_map = {}

        for line in all_lines:
            if (
                current_pattern
                and not current_type
                and line.upper().startswith(";TYPE=")
            ):
                line_part = line.upper()[6:]
                current_type = "Model" if line_part.startswith("MODEL") else "Drafting"
                continue

            if line.startswith(";"):
                continue

            if line.startswith("*"):
                # This is a header line, start of a new pattern
                parts = line[1:].split(",", 1)
                name = parts[0].strip()
                description = parts[1].strip() if len(parts) > 1 else ""
                pattern_type = current_type if current_type else "Drafting"

                current_pattern = Pattern(name, description, is_metric, pattern_type)
                self.patterns.append(current_pattern)
                self.name_map[name] = current_pattern
                current_type = None

            elif current_pattern:
                # This is a data line for the current pattern
                try:
                    # Filter out empty strings from split() before converting to float
                    parts_str = [p.strip() for p in line.split(",")]
                    parts = [float(p) for p in parts_str if p]

                    if len(parts) < 5:
                        continue

                    # --- PARAMETER MAPPING ---
                    # Standard PAT: Angle, X, Y, Delta-U (Parallel), Delta-V (Perp), Dashes
                    angle, ox, oy = parts[0], parts[1], parts[2]
                    delta_u, delta_v = parts[3], parts[4]
                    # remove string of zeros as sometimes used for continuous lines
                    dashes = [] if all(x == 0 for x in parts[5:]) else parts[5:]

                    line_family = Line(angle, ox, oy, delta_u, delta_v, dashes)
                    current_pattern.add_line(line_family)
                except Exception as e:
                    print(
                        "Warning: Could not parse line for pattern '%s': %s (Error: %s)"
                        % (current_pattern.name, line, str(e))
                    )

    def get_pattern(self, name):
        """Retrieves a parsed pattern by its name (alias for self[name])."""
        return self.name_map.get(name)

    def get_pattern_names(self):
        """Returns a list of all parsed pattern names in order."""
        return [p.name for p in self.patterns]
