```
██╗   ██╗██╗   ██╗ █████╗ ██████╗  █████╗ ███╗   ███╗
██║   ██║╚██╗ ██╔╝██╔══██╗██╔══██╗██╔══██╗████╗ ████║
██║   ██║ ╚████╔╝ ███████║██████╔╝███████║██╔████╔██║
██║   ██║  ╚██╔╝  ██╔══██║██╔══██╗██╔══██║██║╚██╔╝██║
╚██████╔╝   ██║   ██║  ██║██║  ██║██║  ██║██║ ╚═╝ ██║
 ╚═════╝    ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝                                                  
  Point Cloud → Heightmap  ·  Malayalam: Uyaram = Height
```

**Uyaram** converts LiDAR point clouds (`.las` / `.laz`) into georeferenced heightmap GeoTIFFs optimised for import into Blender as displacement textures. It is designed for producing high-fidelity clay-style 3D relief renders of urban terrain.

---

## What It Does

- Reads one or more `.las` / `.laz` files from a folder
- Calculates a **global coordinate offset** across all tiles so they sit flush together near Blender's world origin
- Filters to relevant LiDAR classification classes (ground + buildings)
- Applies a **coordinate transformation** to shift real-world UTM coordinates to local origin
- Outputs a **32-bit float GeoTIFF heightmap** per tile using PDAL's GDAL writer at maximum point height per cell
- Prints the exact **Midlevel** and **Strength** values to enter in Blender's Displace modifier for each tile

---

## Why Heightmaps Instead of Meshes

Converting LiDAR directly to a 3D mesh (via Poisson reconstruction or similar) produces hundreds of millions of triangles for urban areas - Blender cannot handle this efficiently. Uyaram instead generates a **high-resolution 32-bit float displacement texture**. In Blender this is paired with a simple subdivided plane and a Displace modifier, keeping geometry counts low while retaining full elevation fidelity including rooftop detail, antennas, and building edge definition.

---

## Requirements

| Dependency | Type | Notes |
|---|---|---|
| Python 3.8+ | Runtime | [python.org](https://www.python.org/downloads/) |
| tkinter | Built-in | Ships with Python on all platforms |
| laspy | Python package | Auto-installed on first run |
| numpy | Python package | Auto-installed on first run |
| PDAL | System binary | Must be installed separately - see below |

### Getting PDAL

PDAL is a system-level tool and cannot be auto-installed. The easiest route on Windows is to install **QGIS** - it bundles a full PDAL installation automatically.

- **QGIS (recommended):** [qgis.org/download](https://qgis.org/download/) - installs PDAL to `C:\Program Files\QGIS x.x\bin\pdal.exe`
- **PDAL standalone:** [pdal.io/en/latest/download.html](https://pdal.io/en/latest/download.html)
- **Conda:** `conda install -c conda-forge pdal`

Uyaram will automatically search common PDAL install locations on startup. If found, it uses the detected path silently. If not found, it presents download links directly in the startup window.

---

## Installation

No pip install required. Just download and run.

```bash
git clone https://github.com/A-Charvin/Uyaram.git
cd Uyaram
python Uyaram.py
```

On first run Uyaram will:
1. Check for `laspy` and `numpy` - install them automatically via pip if missing
2. Search for a PDAL binary - report where it was found or guide you to install it
3. Launch the main interface once all dependencies are confirmed

---

## Usage

### GUI

```bash
python Uyaram.py
```

1. **Source Folder** - browse to or type the path of a folder containing `.las` or `.laz` files
2. **Output Folder** - optionally set a different output location
   - Leave blank → heightmaps are written alongside the source files
   - Type a path that doesn't exist → Uyaram creates the folder automatically
3. **Resolution** - set the output pixel size in metres per pixel (default: `0.5`)
   - `0.5` - high detail, good for urban areas up to ~2km²
   - `1.0` - medium detail, faster, suitable for larger extents
   - `2.0` - coarse, fast, large area overviews
4. Click **▶ Process Files**

### Command Line (headless)

For scripted or server workflows, the core pipeline logic can be run without the GUI:

```bash
python Uyaram.py --nogui --source /path/to/laz --output /path/to/output --resolution 0.5
```

> Note: `--nogui` mode is on the roadmap. Currently GUI mode is required.

---

## Output Files

For each input `.laz` file, Uyaram produces:

| File | Description |
|---|---|
| `filename_heightmap.tif` | 32-bit float GeoTIFF, coordinate-shifted to local origin, DEFLATE compressed |

The GeoTIFF retains full spatial metadata (projection, geotransform) so it can be loaded back into QGIS or ArcGIS Pro for verification.

---

## Using the Output in Blender

Uyaram prints the exact values to use in Blender's Displace modifier for each tile. Here is the full setup:

### 1. Import with BlenderGIS

Install the [BlenderGIS addon](https://github.com/domlysz/BlenderGIS), then:

```
GIS → Import → Georeferenced Raster
```

Select your `_heightmap.tif`. In the import options set **Mode** to `As Displacement Texture`.

### 2. Modifier Stack

Select the imported plane and confirm the modifier stack (Modifier Properties panel):

```
[ Subdivision Surface ]   ← must be above Displace
[ Displace             ]
```

Set **Subdivision Surface**:
- Viewport levels: `1`
- Render levels: `6`

### 3. Displace Modifier Values

Use the values printed by Uyaram in the log:

| Field | Value | Source |
|---|---|---|
| **Midlevel** | e.g. `0.0842` | Printed per tile by Uyaram |
| **Strength** | e.g. `68.4` for 1× scale | Printed per tile - multiply for exaggeration |

**Z exaggeration guide:**
- `1×` - geographically accurate, buildings may look flat
- `2×` - good general balance
- `3×` - recommended for clay render aesthetic
- `5×` - dramatic, matches most published clay relief examples

### 4. Clay Material

In Material Properties → New material (Principled BSDF):

| Property | Value |
|---|---|
| Base Color | R: 0.85  G: 0.84  B: 0.82 |
| Roughness | 0.9 |
| Specular IOR Level | 0.0 |
| Metallic | 0.0 |

### 5. Lighting

Add a Sun lamp (`Shift+A → Light → Sun`):

| Property | Value |
|---|---|
| Rotation X | 55° |
| Rotation Z | 315° (northwest - cartographic convention) |
| Strength | 4.0 |
| Angle | 0.5° |

Enable **Ambient Occlusion** in Render Properties:
- Distance: `2.0m`
- Factor: `0.5`

### 6. Camera

- Type: **Orthographic**
- For top-down: Rotation `X: 0°`
- For slight oblique: Rotation `X: 15°, Z: 30°`

### 7. Render

- Engine: **Cycles** (not EEVEE)
- Device: GPU Compute
- Samples: `256`
- Resolution: `4096 × 4096`
- Enable denoising

---

## Multi-Tile Datasets

Uyaram handles multiple tiles automatically. It calculates a **single global offset** from the average centre of all tile bounding boxes, then applies that same offset to every tile. This ensures all tiles share a common local origin and sit flush against each other in Blender without gaps or overlaps.

Import all tile heightmaps into Blender - they will align correctly because they share the same coordinate shift.

---

## LiDAR Data Sources

| Source | Coverage | URL |
|---|---|---|
| LiDAR Point Clouds - CanElevation Series| [open.canada.ca](https://open.canada.ca/data/en/dataset/7069387e-9986-4297-9f55-0288e9676947) |
| USGS 3DEP | USA national | [apps.nationalmap.gov/downloader](https://apps.nationalmap.gov/downloader/) |
| OpenTopography | Global (curated) | [opentopography.org](https://opentopography.org) |
| Environment Agency | England | [environment.data.gov.uk](https://environment.data.gov.uk/DefraDataDownload/?Mode=survey) |
| AHN | Netherlands | [ahn.nl](https://www.ahn.nl) |


---

## Troubleshooting

**PDAL not found after installing QGIS**
- Restart Uyaram after installing QGIS
- Use the **Installed - retry** button in the startup checker
- If still not found, locate `pdal.exe` manually (usually in `C:\Program Files\QGIS x.x\bin\`) and add it to your system PATH

**Terrain appears flat in Blender**
- Ensure Subdivision Surface is above Displace in the modifier stack
- Set Midlevel to the value printed by Uyaram (not the default 0.5)
- Increase Strength - try 3× exaggeration first

**Terrain floating above ground**
- Midlevel is the key - use the exact value printed in the Uyaram log
- Alternatively: select the mesh, press `G → Z` and nudge it down to Z=0

**Tiles have gaps between them**
- This should not happen with Uyaram's global offset approach
- Verify all tiles were processed in the same Uyaram batch (not separate runs)
- Separate runs recalculate the global offset from only the files present - always process all tiles together in one batch

**Output GeoTIFF has 0,0,0 dimensions in BlenderGIS**
- Do not post-process the heightmap with external tools after Uyaram generates it - this can corrupt the GeoTransform metadata
- Use the raw `_heightmap.tif` output directly

---

## Roadmap

- [ ] `--nogui` headless/CLI mode
- [ ] Custom classification filter selection in UI
- [ ] Automatic Blender `.py` script export with pre-filled Displace modifier values
- [ ] Batch progress bar per file
- [ ] Optional vegetation filter (remove class 3/4/5 trees for bare-earth + buildings only)
- [ ] Windows `.exe` standalone build via PyInstaller

---

## Contributing

Issues and pull requests are welcome. This tool was built for a specific cartographic workflow - if you have edge cases, unusual LiDAR formats, or coordinate system issues, I don't think I can help with those.

---

## Licence

MIT - see `LICENSE` for details.

---

## Acknowledgements

Built on top of [PDAL](https://pdal.io) and [laspy](https://github.com/laspy/laspy). Inspired by the clay-style 3D relief mapping tradition in cartographic design.
