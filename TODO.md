# TODO

## Material thumbnails in `revitmaterials.py` and the Export script

### Goal

Extract the thumbnail image Revit caches for each material, and embed it in the
Excel file written by `Export.pushbutton`.

### What is known

From the note that was in `revitmaterials.py` (removed in `b2aa158`, still in
history at `9480d3e`):

- Revit writes material thumbnails as PNG files in its temp folder, in a
  sub-folder named `MaterialThumbnails_PID_<hex>`.
- The path is reachable from the material: **appearance asset > rendering
  asset > find a string property by name > thumbnail path**.
- The stored value looks like
  `tmp:?MaterialThumbnails_PID_6d48\237ea2532c0Metal_Roofing_Trapezoidal(3).png`.
  Replacing the `tmp:?` prefix with the Revit temp folder gives the real path.
- Since Revit 2019 the temp folder has a GUID appended to the `TMP` environment
  value, so `tempfile.gettempdir()` (evaluated inside the Revit process) is the
  right base, not a hard-coded `%TEMP%`.

### Answered

1. **The rendering asset property** is named `thumbnail`:
   `AppearanceAssetElement.GetRenderingAsset().FindByName("thumbnail").Value`.
   The value is unreliable:
   - the property is sometimes missing;
   - it sometimes starts with `tmp:` (relative to the Revit temp folder);
   - it sometimes holds a full file path.

   A `tmp:` value or full path may have been written on another PC or in another
   session, so the file it names may not exist. Always check
   `os.path.isfile` before using it. A working helper is in
   `Test.panel/TestTube.pushbutton/scripts/export_material_thumbnails.py`.

### Not yet known (verify first)

2. **Whether `PID_6d48` is the Revit process id in hex.** 0x6d48 = 27976. If so
   the folder can be cross-checked with `hex(os.getpid())`, since pyRevit runs
   inside the Revit process. Treat this as a sanity check only; the stored
   string already names the folder.
3. **When Revit creates the file.** The file only exists after Revit has
   rendered that thumbnail (e.g. the material was shown in the Material
   Browser). Materials that were never displayed have no file.
4. **Whether the value is the same for project materials and library
   materials**, and for materials with the default "Generic" asset.

### Decisions made

| Question | Decision |
|---|---|
| How thumbnails appear in Excel | Embedded images in a cell on the Materials sheet |
| Materials with no cached thumbnail | Leave the cell blank, and do not report a count |
| Where the code lives | `lib/revitmaterials.py`, beside the other appearance asset helpers |

### Plan

#### 1. Spike: find the property (no production code)

- Write a throwaway pyRevit script that, for a few materials, walks
  `asset_elem.GetRenderingAsset()` and prints every `AssetPropertyString` whose
  value starts with `tmp:?` (print name, type, value).
- Record the property name in this file and in the new function's docstring.
- Check that the resolved file exists, and note whether materials not yet
  shown in the browser are missing the property or only the file.
- Try a project material, a library material and a material with no custom
  asset, to answer unknown 4.
- Decide from the result whether "force generation" is feasible. The user chose
  "leave blank", so only note the finding.

#### 2. Library functions (`lib/revitmaterials.py`)

Keep to IronPython 2.7 syntax: no `pathlib`, no f-strings, `os.path` only.

```python
TEMP_PREFIX = "tmp:?"

def get_revit_temp_path():
    """Revit temp folder (tempfile.gettempdir() evaluated in the Revit process)."""

def resolve_thumbnail_path(raw_path):
    """Replace the 'tmp:?' prefix with the temp folder. None if not a tmp: path."""

def get_material_thumbnail_path(doc, material):
    """Path of the cached thumbnail PNG, or None if the material has no
    appearance asset, no thumbnail property, or the file does not exist."""
```

- Follow the existing style: use `is_valid_id`, return `None` rather than
  raising, and catch `Exception` only around API calls that can throw.
- Resolve the temp path once per export (module-level cache or argument),
  not once per material.
- Reciprocal helper, only if needed by the Export step below:
  `copy_material_thumbnail(path, dest_folder)`. Skip it for the embedded-image
  design.

#### 3. Export integration (`Export.pushbutton`)

- Add a `Thumbnail` column to `HEADERS` in `export_materials_to_excel-script.py`.
  Place it next to `Material Name` or after `Appearance Asset`; pick one when
  implementing and keep column indices data-driven like `PATTERN_FIELDS`.
- Use `ws.insert_image(row, col, path, {"object_position": 1, "x_scale": ..,
  "y_scale": ..})` from xlsxwriter. Scale the image to fit the cell.
- Set the row height and thumbnail column width so the image fits. A row height
  of about 48-64 px is a reasonable starting point; confirm against the real
  thumbnail size from the spike.
- No cached thumbnail: write nothing in that cell, add no message.
- Wrap each insert in `try/except` so one unreadable PNG cannot abort the
  export; the existing per-material `except` already prints the failure.
- `Import.pushbutton` needs no change: it ignores columns it does not use. Use
  a named header (`Thumbnail`) so the importer does not treat the column as
  data. Confirm `import_materials_from_excel-script.py` skips it.

#### 4. Cleanup and tests

- Restore nothing from the old comment block: the facts above replace it.
- Run the pure-Python parts against stubs, as was done for `revitcolour`:
  `resolve_thumbnail_path` with and without the `tmp:?` prefix, and with
  `get_revit_temp_path` patched.
- Manual test in Revit on a project with:
  - materials that have been shown in the Material Browser;
  - materials that have not (cells must stay blank, export must complete);
  - a very large material count, to check export time and file size.
- Run `ruff check` and `ruff format`; keep the CRLF line endings.

### Risks

- The thumbnail files are in the Revit temp folder and are deleted when Revit
  closes, so the export is only complete for thumbnails generated in this
  session. This is accepted (blank when missing).
- Embedding hundreds of PNGs can make the `.xlsx` large and slow to write. If
  this is a problem, downscale before embedding (needs an imaging library, which
  may not be available in IronPython; `System.Drawing` is the alternative).
- The `tmp:?` convention is undocumented and could change between Revit
  versions. Return `None` on anything unexpected rather than guessing.

### Open questions

- Which column position do you want for the thumbnail?
- Should the thumbnail size be fixed (e.g. 48 px) or configurable?
