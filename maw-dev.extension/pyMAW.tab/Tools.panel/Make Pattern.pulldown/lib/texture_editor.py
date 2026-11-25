# -*- coding: utf-8 -*-
"""Texture editor window for the brick / tile pattern tools.

Opened from the pattern dialog once the pattern and sizes are known. Edits a
brick_texture.TextureSettings and shows the result lit on the chosen colours,
always as a 2 x 2 tiling so seams show.
"""
from __future__ import division

import os
import time
import traceback

import clr
import wpf

clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")

from System import TimeSpan
from System.Windows import Window, Visibility
from System.Windows.Media import Color, SolidColorBrush
from System.Windows.Threading import DispatcherTimer
from pyrevit import forms

import brick_texture

XAML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "texture_editor.xaml")
RENDER_DELAY_MS = 250       # wait for the user to stop dragging a slider before re-rendering
PREVIEW_MAX_PX = 1600       # atlas side; the 2 x 2 preview is twice this


def _brush(hex_text):
    rgb = brick_texture.parse_hex(hex_text)
    if rgb is None:
        return None
    return SolidColorBrush(Color.FromRgb(*[int(round(v * 255)) for v in rgb]))


class TextureEditor(Window):
    """Use: editor = TextureEditor(...); if editor.show(): settings = editor.settings."""

    _ready = False

    def __init__(self, pattern, mortar_mm, settings, apply_texture, tile_type=False):
        wpf.LoadComponent(self, XAML_PATH)
        self.pattern = pattern
        self.mortar_mm = mortar_mm
        self.settings = settings.copy()
        self.apply_texture = apply_texture
        self._key = None
        self._plan = None
        self._bump = None

        if tile_type:
            self.BrickLabel.Text = "Tile"
            self.MortarLabel.Text = "Grout joint"
        for key, label in brick_texture.MATERIALS:
            self.MaterialCombo.Items.Add(label)

        s = self.settings
        self.MaterialCombo.SelectedIndex = [k for k, _ in brick_texture.MATERIALS].index(s.material)
        self.PitsSlider.Value = s.pits
        self.ScratchSlider.Value = s.scratch
        self.SeedInput.Text = str(s.seed)
        self.DepthSlider.Value = round(s.joint_depth * 100)
        self.ReliefSlider.Value = round(s.relief * 100)
        self.BrickHex.Text = s.brick_hex
        self.MortarHex.Text = s.mortar_hex
        self._update_swatches()
        self._update_labels()

        if not apply_texture:
            self.NoteText.Visibility = Visibility.Visible
            self.TextureGroup.IsEnabled = False

        self.timer = DispatcherTimer()
        self.timer.Interval = TimeSpan.FromMilliseconds(RENDER_DELAY_MS)
        self.timer.Tick += self.on_tick

        for slider in (self.PitsSlider, self.ScratchSlider, self.DepthSlider, self.ReliefSlider):
            slider.ValueChanged += self.on_changed
        self.MaterialCombo.SelectionChanged += self.on_changed
        self.SeedInput.TextChanged += self.on_changed
        self.BrickHex.TextChanged += self.on_hex_changed
        self.MortarHex.TextChanged += self.on_hex_changed
        self.Closed += self.on_closed
        self._ready = True

    # ------------------------------------------------------------ public
    def show(self):
        self.refresh()
        return bool(self.ShowDialog())

    # ------------------------------------------------------------ state
    def read_settings(self):
        s = self.settings
        s.material = brick_texture.MATERIALS[max(0, self.MaterialCombo.SelectedIndex)][0]
        s.pits = int(self.PitsSlider.Value)
        s.scratch = int(self.ScratchSlider.Value)
        s.joint_depth = self.DepthSlider.Value / 100.0
        s.relief = self.ReliefSlider.Value / 100.0
        try:
            s.seed = int(self.SeedInput.Text)
        except ValueError:
            pass
        for box, attr in ((self.BrickHex, "brick_hex"), (self.MortarHex, "mortar_hex")):
            if brick_texture.parse_hex(box.Text):
                setattr(s, attr, brick_texture.normal_hex(box.Text, getattr(s, attr)))
        return s

    def _update_labels(self):
        self.PitsValue.Text = str(int(self.PitsSlider.Value))
        self.ScratchValue.Text = str(int(self.ScratchSlider.Value))
        self.DepthValue.Text = "{:d}%".format(int(self.DepthSlider.Value))
        self.ReliefValue.Text = "{:d}%".format(int(self.ReliefSlider.Value))

    def _update_swatches(self):
        for button, box in ((self.BrickSwatch, self.BrickHex), (self.MortarSwatch, self.MortarHex)):
            brush = _brush(box.Text)
            if brush is not None:
                button.Background = brush
        # red text marks a colour that cannot be read yet; the last good colour stays in use
        for box in (self.BrickHex, self.MortarHex):
            box.Foreground = SolidColorBrush(Color.FromRgb(0, 0, 0) if brick_texture.parse_hex(box.Text) else Color.FromRgb(200, 0, 0))

    # ------------------------------------------------------------ events
    def on_changed(self, sender, args):
        if not self._ready:
            return
        self._update_labels()
        self.timer.Stop()
        self.timer.Start()

    def on_hex_changed(self, sender, args):
        if not self._ready:
            return
        self._update_swatches()
        self.on_changed(sender, args)

    def on_tick(self, sender, args):
        self.timer.Stop()
        self.refresh()

    def BrickSwatch_Click(self, sender, e):
        self._pick(self.BrickHex)

    def MortarSwatch_Click(self, sender, e):
        self._pick(self.MortarHex)

    def _pick(self, box):
        current = brick_texture.normal_hex(box.Text, brick_texture.DEFAULT_BRICK_HEX)
        picked = forms.ask_for_color(default="#FF" + current[1:])
        if picked:
            box.Text = brick_texture.normal_hex(picked, current)

    def OkButton_Click(self, sender, e):
        self.timer.Stop()
        self.read_settings()
        self.DialogResult = True
        self.Close()

    def CancelButton_Click(self, sender, e):
        self.DialogResult = False
        self.Close()

    def on_closed(self, sender, args):
        self.timer.Stop()
        self._dispose_bump()

    # ------------------------------------------------------------ rendering
    def _dispose_bump(self):
        if self._bump is not None:
            self._bump.Dispose()
            self._bump = None

    def refresh(self):
        """Render the preview: a new bump atlas when the texture changed, else only the colour pass."""
        self.StatusText.Text = "Rendering..."
        start = time.time()
        try:
            s = self.read_settings()
            key = (s.material, s.pits, s.scratch, s.seed, round(s.joint_depth, 4))
            if key != self._key or self._bump is None:
                self._dispose_bump()
                self._plan = brick_texture.make_plan(
                    self.pattern, s, self.apply_texture, self.mortar_mm, ppm=2.0, max_px=PREVIEW_MAX_PX
                )
                self._bump = brick_texture.render_bump(self._plan, s)
                self._key = key
            colour = brick_texture.render_colour(self._plan, self._bump, s)
            tiled = brick_texture.tile_2x2(colour)
            self.PreviewImage.Source = brick_texture.to_wpf_image(tiled)
            colour.Dispose()
            tiled.Dispose()
            self.PlaceholderText.Visibility = Visibility.Collapsed

            width_mm, height_mm = self._plan.size_mm
            self.SizeText.Text = "Revit bump size: {:.2f} x {:.2f} mm".format(width_mm, height_mm)
            self.StatusText.Text = "{}x{} px per tile, {}x{} repeats, {:.2f} px/mm   ({:.2f} s)".format(
                self._plan.width_px, self._plan.height_px, self._plan.repeats[0], self._plan.repeats[1],
                self._plan.ppm, time.time() - start,
            )
        except Exception as e:
            self.StatusText.Text = "Error: {}".format(e)
            print(traceback.format_exc())
