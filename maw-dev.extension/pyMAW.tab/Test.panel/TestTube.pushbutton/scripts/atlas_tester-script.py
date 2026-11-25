# -*- coding: utf-8 -*-
"""Bump Atlas Tester.

Builds a seamless bump-map atlas for a brick / paver fill pattern from the baked
texture sheets in ../textures and the cell outlines in lib/pattern_cells.yaml.
Enter the real-world size shown after generating as the Revit bump map width and height.
"""

from pyrevit import script
import wpf
import sys
import os
import clr
import time
import traceback

# -------------------- .NET Imports --------------------
clr.AddReference("System.Drawing")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")

from System.IO import MemoryStream, SeekOrigin
from System.Windows import Window, Visibility
from System.Windows.Media.Imaging import BitmapImage, BitmapCacheOption
from System.Drawing import Bitmap, Graphics
from System.Drawing.Imaging import ImageFormat, PixelFormat
import Microsoft.Win32

# -------------------- Local Import --------------------
lib_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "Tools.panel",
    "Make Pattern.pulldown",
    "lib",
)
if lib_dir not in sys.path:
    sys.path.append(lib_dir)

import pattern_cells
import texture_atlas

PATH_SCRIPT = script.get_script_path()

MATERIALS = [("brick", "Clay brick"), ("concrete", "Concrete"), ("block", "Concrete block (vertical drag)")]


class AtlasTester(Window):
    def __init__(self):
        wpf.LoadComponent(self, os.path.join(PATH_SCRIPT, "atlas_tester.xaml"))

        self.catalog = pattern_cells.load_catalog()
        self.keys = list(self.catalog.keys())
        for key in self.keys:
            self.cmbPattern.Items.Add("{} - {}".format(key, self.catalog[key].get("name", key)))
        for _, label in MATERIALS:
            self.cmbMaterial.Items.Add(label)
        self.cmbMaterial.SelectedIndex = 0
        self.cmbPattern.SelectionChanged += self.pattern_changed
        self.cmbPattern.SelectedIndex = self.keys.index("STRETCHERHALF") if "STRETCHERHALF" in self.keys else 0

        self.btnGenerate.Click += self.generate
        self.btnSave.Click += self.save_image
        self.last_bmp = None
        self.last_plan = None
        self.last_joint = 0.5
        self.last_preview_outline = False
        self.ShowDialog()

    def pattern_changed(self, sender, args):
        params = self.catalog[self.keys[self.cmbPattern.SelectedIndex]].get("params", {})
        for box, name in ((self.txtWidth, "width"), (self.txtHeight, "height"), (self.txtMortar, "mortar"), (self.txtLength, "length")):
            if name in params:
                box.Text = "{:g}".format(float(params[name]))

    def _float(self, box, default):
        try:
            return float(box.Text)
        except ValueError:
            return default

    def generate(self, sender, args):
        self.statusText.Text = "Generating..."
        self.placeholderText.Visibility = Visibility.Collapsed
        try:
            start = time.time()
            key = self.keys[self.cmbPattern.SelectedIndex]
            material = MATERIALS[self.cmbMaterial.SelectedIndex][0]
            mortar = self._float(self.txtMortar, 0.0)
            extra = {}
            if "length" in self.catalog[key].get("params", {}):
                extra["length"] = self._float(self.txtLength, 609.6)

            pattern = pattern_cells.build_pattern(
                key,
                width=self._float(self.txtWidth, None),
                height=self._float(self.txtHeight, None),
                mortar=mortar,
                catalog=self.catalog,
                **extra
            )
            min_size = self._float(self.txtMinSize, 800.0)
            plan = texture_atlas.plan_atlas(
                pattern,
                material,
                pit_level=int(self.sliderPits.Value),
                scratch_level=int(self.sliderScratch.Value),
                ppm=self._float(self.txtPpm, 2.0),
                seed=int(self._float(self.txtSeed, 1)),
                mortar=mortar,
                min_size_mm=min_size,
            )
            outline = 1 if self.chkOutline.IsChecked else 0
            bmp = texture_atlas.render_atlas(plan, joint_level=self.sliderJoint.Value, outline_px=outline)

            if self.last_bmp is not None:
                self.last_bmp.Dispose()
            self.last_bmp = bmp
            self.last_plan = plan
            self.last_joint = self.sliderJoint.Value
            self.last_preview_outline = bool(outline)

            base = bmp
            if self.chkColour.IsChecked:
                rgb = self.parse_colour(self.txtColour.Text)
                if rgb is None:
                    self.statusText.Text = "Colour must be hex like #A8553A"
                    return
                base = texture_atlas.render_colour_preview(plan, bmp, rgb, rgb, self.sliderBump.Value)

            shown = base
            if self.chkTile.IsChecked:
                shown = Bitmap(base.Width * 2, base.Height * 2, PixelFormat.Format32bppArgb)
                g = Graphics.FromImage(shown)
                for ty in (0, 1):
                    for tx in (0, 1):
                        g.DrawImage(base, tx * base.Width, ty * base.Height, base.Width, base.Height)
                g.Dispose()
            self.show_bitmap(shown)
            if shown is not base:
                shown.Dispose()
            if base is not bmp:
                base.Dispose()

            width_mm, height_mm = plan.size_mm
            self.sizeText.Text = "Revit bump size: {:.2f} x {:.2f} mm".format(width_mm, height_mm)
            self.statusText.Text = "{}x{} px, {}x{} repeats, {} cells, {:.2f} px/mm".format(
                plan.width_px, plan.height_px, plan.repeats[0], plan.repeats[1], len(plan.jobs), plan.ppm
            )
            self.timeText.Text = "Time: {:.3f} sec".format(time.time() - start)
        except Exception as e:
            self.statusText.Text = "Error: {}".format(e)
            print(traceback.format_exc())

    @staticmethod
    def parse_colour(text):
        text = text.strip().lstrip("#")
        if len(text) != 6:
            return None
        try:
            return [int(text[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
        except ValueError:
            return None

    def show_bitmap(self, bmp):
        ms = MemoryStream()
        bmp.Save(ms, ImageFormat.Png)
        ms.Seek(0, SeekOrigin.Begin)
        image = BitmapImage()
        image.BeginInit()
        image.StreamSource = ms
        image.CacheOption = BitmapCacheOption.OnLoad
        image.EndInit()
        image.Freeze()
        self.imgPreview.Source = image
        ms.Close()

    def save_image(self, sender, args):
        if self.last_bmp is None:
            self.statusText.Text = "Nothing to save - generate first."
            return
        dialog = Microsoft.Win32.SaveFileDialog()
        dialog.FileName = "{}_bump".format(self.keys[self.cmbPattern.SelectedIndex].lower())
        dialog.DefaultExt = ".png"
        dialog.Filter = "PNG Files (.png)|*.png"
        if dialog.ShowDialog():
            try:
                if self.last_preview_outline:
                    # the preview outlines are an aid only; save the clean atlas
                    clean = texture_atlas.render_atlas(self.last_plan, joint_level=self.last_joint)
                    clean.Save(dialog.FileName, ImageFormat.Png)
                    clean.Dispose()
                else:
                    self.last_bmp.Save(dialog.FileName, ImageFormat.Png)
                self.statusText.Text = "Saved: {}".format(dialog.FileName)
            except Exception as e:
                self.statusText.Text = "Save Error: {}".format(e)


if __name__ == "__main__":
    try:
        AtlasTester()
    except Exception:
        print(traceback.format_exc())
