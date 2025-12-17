# -*- coding: utf-8 -*-
"""
Concrete Tester
"""
from pyrevit import revit, script, forms, DB
import wpf
import sys
import os
import clr
import time

# -------------------- .NET Imports --------------------
clr.AddReference("System.Drawing")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")

from System.IO import MemoryStream, SeekOrigin, FileStream, FileMode
from System.Windows import Window, Visibility
from System.Windows.Media.Imaging import BitmapImage, BitmapCacheOption, PngBitmapEncoder, BitmapFrame
from System.Drawing.Imaging import ImageFormat
import Microsoft.Win32 

# -------------------- Local Import --------------------
current_dir = os.path.dirname(__file__)
if current_dir not in sys.path:
    sys.path.append(current_dir)

import concrete_texture
PATH_SCRIPT = script.get_script_path()

# -------------------- Logic --------------------

class ConcreteTester(Window):
    def __init__(self):
        # Load XAML file
        path_xaml_file = os.path.join(PATH_SCRIPT, "concrete_tester.xaml")
        try:
            wpf.LoadComponent(self, path_xaml_file)
        except Exception as e:
            print("Error loading XAML: {}".format(e))
            return

        self.btnUpdate.Click += self.update_texture
        self.btnSave.Click += self.save_image
        self.ShowDialog()

    def get_resolution(self):
        try:
            w = int(self.txtWidth.Text)
            h = int(self.txtHeight.Text)
            return w, h
        except:
            return 512, 512

    def update_texture(self, sender, args):
        self.statusText.Text = "Generating..."
        self.placeholderText.Visibility = Visibility.Collapsed
        
        # Get Inputs
        w, h = self.get_resolution()
        seed = 1234
        
        pit_density = self.sliderDensity.Value
        pit_depth = self.sliderDepth.Value
        grain = self.sliderGrain.Value
        base_depth = self.sliderBaseDepth.Value
        trowel = self.sliderTrowel.Value
        scale = self.sliderScale.Value
        normal_str = self.sliderNormal.Value

        start_time = time.time()

        try:
            # Call Generator
            bump_bmp, normal_bmp, _ = concrete_texture.create_concrete_textures(
                width=w, 
                height=h, 
                seed=seed,
                normal_strength=normal_str,
                pit_density=pit_density,
                pit_depth=pit_depth,
                grain_strength=grain,
                base_scale=scale,
                base_depth=base_depth,
                trowel_strength=trowel
            )

            # Convert System.Drawing.Bitmap -> WPF BitmapImage
            ms = MemoryStream()
            bump_bmp.Save(ms, ImageFormat.Png)
            ms.Seek(0, SeekOrigin.Begin)

            bmp_image = BitmapImage()
            bmp_image.BeginInit()
            bmp_image.StreamSource = ms
            bmp_image.CacheOption = BitmapCacheOption.OnLoad
            bmp_image.EndInit()
            bmp_image.Freeze()

            self.imgPreview.Source = bmp_image
            
            end_time = time.time()
            elapsed = end_time - start_time
            
            self.statusText.Text = "Complete" 
            self.timeText.Text = "Time: {:.3f} sec".format(elapsed)

            bump_bmp.Dispose()
            normal_bmp.Dispose()
            ms.Close()

        except Exception as e:
            self.statusText.Text = "Error: " + str(e)
            print(e)

    def save_image(self, sender, args):
        """Saves the currently displayed image to disk."""
        if self.imgPreview.Source is None:
            self.statusText.Text = "No image to save."
            return

        dialog = Microsoft.Win32.SaveFileDialog()
        dialog.FileName = "concrete_texture"
        dialog.DefaultExt = ".png"
        dialog.Filter = "PNG Files (.png)|*.png"
        
        if dialog.ShowDialog() == True:
            try:
                # Use WPF Encoder to save the existing BitmapSource
                encoder = PngBitmapEncoder()
                encoder.Frames.Add(BitmapFrame.Create(self.imgPreview.Source))
                
                with FileStream(dialog.FileName, FileMode.Create) as stream:
                    encoder.Save(stream)
                
                self.statusText.Text = "Image Saved."
            except Exception as e:
                self.statusText.Text = "Save Error: " + str(e)

if __name__ == "__main__":
    ConcreteTester()
