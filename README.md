```markdown
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
- **Optional classification filter**: exclude noise, water, or unclassified points when your data is properly tagged
- Applies a **coordinate transformation** to shift real-world UTM coordinates to local origin
- Outputs a **32-bit float GeoTIFF heightmap** per tile using PDAL's GDAL writer at maximum point height per cell
- **Real-time PDAL output streaming**: watch processing progress live in the log
- Prints the exact **Midlevel** and **Strength** values to enter in Blender's Displace modifier for each tile

---

## Why Heightmaps Instead of Meshes

Converting LiDAR directly to a 3D mesh (via Poisson reconstruction or similar) produces hundreds of millions of triangles for urban areas - Blender cannot handle this efficiently. Uyaram instead generates a **high-resolution 32-bit float displacement texture**. In Blender this is paired with a simple subdivided plane and a Displace modifier, keeping geometry counts low while retaining full elevation fidelity including rooftop detail, antennas, and building edge definition.

---

## Requirements

| Dependency | Type | Notes |
|---|---|---|
| Python 3.8+ | Runtime | [python.org](https://www.python.org/downloads/) |
| QGIS | Software | https://qgis.org/download/ |
| laspy[lazrs] | Python package | Auto-installed on first run |
| PDAL | System binary | Must be installed separately - see below |

**Note**: Uyaram no longer requires `numpy`, `osgeo`, or `gdal` Python packages. All geospatial processing is handled by QGIS-bundled CLI tools.

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
1. Check for `laspy` - install it automatically via pip if missing
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
4. **Classification Filter** (optional) - click to expand and exclude specific LiDAR classes:
   - **Noise** (classes 7, 18): removes specular reflections and outliers
   - **Water** (class 9): removes water surface returns and reflections
   - **Unclassified** (class 1): removes points without classification tags
   - *Tip: If your data has no classifications, leave all classes enabled — no filter step is added to the pipeline*
5. **Mosaic output** (optional) - merge all tile heightmaps into a single GeoTIFF after processing
6. Click **▶ Process Files**

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
| `filename_heightmap.tif` | 32-bit float GeoTIFF, coordinate-shifted to local origin, DEFLATE compressed, **NoData = -2.0** |

The GeoTIFF retains full spatial metadata (projection, geotransform) so it can be loaded back into QGIS or ArcGIS Pro for verification.

**Why NoData = -2.0?**  
After the Z-shift, real ground equals `0.0`. Setting NoData to `-2.0` keeps empty cells visually distinct from terrain while avoiding Blender displacement artifacts. The slight negative offset is negligible in renders but prevents void blending.

---

## Using the Output in Blender

Uyaram prints the exact values to use in Blender's Displace modifier for each tile. Here is the full setup:

### 1. Import with BlenderGIS

Install the [BlenderGIS addon](https://github.com/domlysz/BlenderGIS), then:

```
GIS → Import → Georeferenced Raster
```

Select your `_heightmap.tif`. In the import options set **Mode** to `As Displacement Texture`.

### 2. Modifier Stack (Crash-Proof Setup)

Select the imported plane and confirm the modifier stack (Modifier Properties panel):

```
[ Subdivision Surface ]   ← must be above Displace
[ Displace             ]
```

Set **Subdivision Surface**:
- Viewport levels: `1`
- Render levels: `2` *(do not exceed 2 for 1km tiles to avoid crashes)*
- Type: `Simple`

### 3. Exact Vertex Mapping (Alternative to Subdivision)

For maximum control and zero interpolation artifacts:

1. Add a plane and scale to real-world size (e.g., `S → 1000` for 1km tile)
2. Edit Mode → Select All → Right Click → **Subdivide**
3. Set **Number of Cuts**: `1999` (for 2000×2000 vertices at 0.5m resolution)
4. Object Mode → Add **Displace** modifier only (no Subdivision modifier)

### 4. Displace Modifier Values

Use the values printed by Uyaram in the log:

| Field | Value | Source |
|---|---|---|
| **Midlevel** | e.g. `0.0` or `0.0842` | Printed per tile by Uyaram |
| **Strength** | e.g. `68.4` for 1× scale | Printed per tile - multiply for exaggeration |

**Critical settings**:
- **Color Space**: `Non-Color` (prevents gamma distortion on float data)
- **Direction**: `Z`
- **Midlevel**: Use the exact value printed. If your tile has depressions (negative values), Midlevel will be >0.0.
- **Strength**: Start with the printed value. Multiply by `1.5–3.0` for cartographic exaggeration.

**Z exaggeration guide:**
- `1×` - geographically accurate, buildings may look flat
- `2×` - good general balance
- `3×` - recommended for clay render aesthetic
- `5×` - dramatic, matches most published clay relief examples

### 5. Clay Material

In Material Properties → New material (Principled BSDF):

| Property | Value |
|---|---|
| Base Color | R: 0.85  G: 0.84  B: 0.82 |
| Roughness | 0.9 |
| Specular IOR Level | 0.0 |
| Metallic | 0.0 |
| **Shade Flat** | ✅ (do not use Shade Smooth) |

### 6. Lighting

Add a Sun lamp (`Shift+A → Light → Sun`):

| Property | Value |
|---|---|
| Rotation X | 55° |
| Rotation Z | 315° (northwest - cartographic convention) |
| Strength | 4.0 |
| Angle | 1.5° *(sharper shadows reveal fine LiDAR detail)* |

Enable **Ambient Occlusion** in Render Properties:
- Distance: `1.5m` *(adjust to match your tile scale)*
- Factor: `0.5`

### 7. Camera

- Type: **Orthographic**
- For top-down: Rotation `X: 90°`
- For slight oblique: Rotation `X: 75°, Z: 0°`

### 8. Render

- Engine: **Cycles** (not EEVEE)
- Device: GPU Compute
- Samples: `128` *(increase to 256 only if noise persists in deep shadows)*
- Resolution: `4096 × 4096` or higher for zoom-ready output
- Enable denoising

---

## Handling Water Reflections & Noise

If your heightmap shows water reflections or noise artifacts:

### Option 1: Classification Filter (If Data is Classified)
- Enable the Classification Filter in Uyaram
- Uncheck `#9 Water`, `#7 Low Noise`, `#18 High Noise`
- Process as normal

### Option 2: Intensity Filtering (If Unclassified)
Water reflections often have extreme intensity values. Add this to your pipeline (advanced):

```python
# In Uyaram.py, add to pipeline_steps:
{
    "type": "filters.range",
    "limits": "Intensity[1000:50000]"  # Adjust thresholds based on your data
}
```

Typical intensity ranges:
- **Water**: Often `< 500` or `> 60000` (saturated)
- **Ground/Buildings**: `1000–40000`

### Option 3: Post-Process in Blender
If PDAL filtering doesn't fully remove artifacts:
1. In Blender, add a **Mask modifier** or use **Vertex Groups**
2. Paint mask over water areas
3. Set masked vertices to Z=0 or delete them

---

## Multi-Tile Datasets

Uyaram handles multiple tiles automatically. It calculates a **single global offset** from the average centre of all tile bounding boxes, then applies that same offset to every tile. This ensures all tiles share a common local origin and sit flush against each other in Blender without gaps or overlaps.

Import all tile heightmaps into Blender - they will align correctly because they share the same coordinate shift.

---

## LiDAR Data Sources

| Source | Coverage | URL |
|---|---|---|
| LiDAR Point Clouds - CanElevation Series | Canada | [open.canada.ca](https://open.canada.ca/data/en/dataset/7069387e-9986-4297-9f55-0288e9676947) |
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
- Verify **Color Space** is set to `Non-Color` on the displacement texture

**Terrain floating above ground or extending downward**
- Midlevel is the key - use the exact value printed in the Uyaram log
- The output GeoTIFF uses `NoData = -2.0`; Blender reads this as a slight downward offset. If you see extreme downward spikes, ensure you are using the latest Uyaram version.

**Tiles have gaps between them**
- This should not happen with Uyaram's global offset approach
- Verify all tiles were processed in the same Uyaram batch (not separate runs)
- Separate runs recalculate the global offset from only the files present - always process all tiles together in one batch

**Output GeoTIFF has 0,0,0 dimensions in BlenderGIS**
- Do not post-process the heightmap with external tools after Uyaram generates it - this can corrupt the GeoTransform metadata
- Use the raw `_heightmap.tif` output directly

**Blender crashes on Subdivision**
- For 1km tiles at 0.5m resolution, do not exceed Subdivision Render Level 2
- Use the **Exact Vertex Mapping** method (1999 cuts) for crash-proof, interpolation-free results
- Ensure your GPU has sufficient VRAM (8GB+ recommended for large tiles)

---

## Roadmap

- [ ] `--nogui` headless/CLI mode
- [ ] Intensity/Z filtering UI controls for water reflection removal
- [ ] Automatic Blender `.py` script export with pre-filled Displace modifier values
- [ ] Batch progress bar per file
- [ ] Optional vegetation filter (remove class 3/4/5 trees for bare-earth + buildings only)
- [ ] Windows `.exe` standalone build via PyInstaller

---

## Contributing

Issues and pull requests are welcome. This tool was built for a specific cartographic workflow - if you have edge cases, unusual LiDAR formats, or coordinate system issues, please open an issue with sample data and I'll do my best to help.

---

## Acknowledgements

Built on top of [PDAL](https://pdal.io) and [laspy](https://github.com/laspy/laspy). Inspired by the clay-style 3D relief mapping tradition in cartographic design.
