#!/usr/bin/env python3
"""
Uyaram - Point Cloud to Heightmap
Malayalam: Uyaram = height

Standalone GUI. Zero osgeo, zero numpy, zero pip gdal.
Requires : Python 3.8+, tkinter, laspy[lazrs]
Detects  : QGIS/OSGeo4W via PATH + filesystem scan

Features:
  - Global XY + Z ground shift (ground = 0.0 across all tiles)
  - Optional per-class classification filter (collapsed by default)
  - Optional per-class heightmap export (split mode)
  - Split mode uses nodata=-1 so layers stack cleanly in Blender
  - Real-time PDAL output streaming
  - Optional mosaic via gdal_merge.py
  - Per-tile Blender Displace modifier values printed in log
"""

import sys
import json
import subprocess
import shutil
import glob
import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext
from pathlib import Path

# ── Colour palette ───────────────────────────────────────────────────────────
BG       = "#0f0f10"
SURFACE  = "#161618"
SURFACE2 = "#1e1e21"
BORDER   = "#2a2a2e"
ACCENT   = "#7eb8d4"
TEXT     = "#d8d8dc"
TEXT_DIM = "#7a7a82"
TEXT_BRT = "#f0f0f4"
SUCCESS  = "#6dbb8a"
ERROR    = "#d47e7e"
WARN     = "#d4b896"

FONT_MONO  = ("Courier New", 9)
FONT_LABEL = ("Segoe UI", 9)
FONT_HEAD  = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 8)

# ── Placeholder strings — exact match used for guards ────────────────────────
PLACEHOLDER_SOURCE = "Folder with .las / .laz files"
PLACEHOLDER_OUTPUT = "Leave blank — outputs alongside source files"

# ── ASCII logo ────────────────────────────────────────────────────────────────
UYARAM_LOGO = """\
██╗   ██╗██╗   ██╗ █████╗ ██████╗  █████╗ ███╗   ███╗
██║   ██║╚██╗ ██╔╝██╔══██╗██╔══██╗██╔══██╗████╗ ████║
██║   ██║ ╚████╔╝ ███████║██████╔╝███████║██╔████╔██║
██║   ██║  ╚██╔╝  ██╔══██║██╔══██╗██╔══██║██║╚██╔╝██║
╚██████╔╝   ██║   ██║  ██║██║  ██║██║  ██║██║ ╚═╝ ██║
 ╚═════╝    ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝
  Point Cloud → Heightmap  ·  Malayalam: Uyaram = Height\
"""

# ── LiDAR classification definitions ─────────────────────────────────────────
# (code, label, default_on, category)
CLASSIFICATIONS = [
    # Core terrain & structure
    ( 1, "Unclassified",         False,  "terrain"),
    ( 2, "Ground",               True,  "terrain"),
    ( 6, "Buildings",            True,  "terrain"),
    (17, "Bridge Deck",          True,  "terrain"),
    # Vegetation
    ( 3, "Low Vegetation",       True,  "vegetation"),
    ( 4, "Medium Vegetation",    True,  "vegetation"),
    ( 5, "High Vegetation",      True,  "vegetation"),
    # Noise — off by default
    ( 7, "Low Noise",            False, "noise"),
    (18, "High Noise",           False, "noise"),
    (16, "Overlap",              False, "noise"),
    # Water — off by default
    ( 9, "Water",                False, "water"),
    # Other infrastructure
    ( 8, "Model Key / Reserved", True,  "other"),
    (10, "Rail",                 True,  "other"),
    (11, "Road Surface",         True,  "other"),
    (13, "Wire Guard",           True,  "other"),
    (14, "Wire Conductor",       True,  "other"),
    (15, "Transmission Tower",   True,  "other"),
    (19, "Overhead Structure",   True,  "other"),
    (20, "Ignored Ground",       False, "other"),
]

CATEGORY_ORDER  = ["terrain", "vegetation", "noise", "water", "other"]
CATEGORY_LABELS = {
    "terrain":    "Terrain & Structure",
    "vegetation": "Vegetation",
    "noise":      "Noise",
    "water":      "Water",
    "other":      "Other / Infrastructure",
}
CATEGORY_COLOURS = {
    "terrain":    ACCENT,
    "vegetation": SUCCESS,
    "noise":      ERROR,
    "water":      "#7ab8d4",
    "other":      TEXT_DIM,
}


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _pip_install(package):
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package, "--quiet"],
            capture_output=True, text=True, timeout=120
        )
        ok = result.returncode == 0
        return ok, (f"Installed {package}." if ok else result.stderr.strip())
    except Exception as e:
        return False, str(e)


def _check_python_deps():
    import importlib.util
    required = [{"import": "laspy", "pip": "laspy[lazrs]"}]
    results  = []
    for pkg in required:
        available     = importlib.util.find_spec(pkg["import"]) is not None
        installed_now = False
        error         = None
        if not available:
            ok, msg = _pip_install(pkg["pip"])
            if ok:
                importlib.invalidate_caches()
                available     = importlib.util.find_spec(pkg["import"]) is not None
                installed_now = available
            if not available:
                error = msg
        results.append({
            "name":          pkg["import"],
            "available":     available,
            "installed_now": installed_now,
            "error":         error,
        })
    return results


def _find_qgis_tools():
    """Locate pdal and a GDAL merge tool via PATH then filesystem scan."""
    pdal       = shutil.which("pdal")
    gdal_trans = shutil.which("gdal_translate")
    gdal_merge = shutil.which("gdal_merge.py")

    if pdal and (gdal_trans or gdal_merge):
        return Path(pdal).parent, pdal, gdal_trans or gdal_merge

    roots  = [Path(r"C:\OSGeo4W"), Path(r"C:\OSGeo4W64")]
    roots += [Path(p) for p in glob.glob(r"C:\Program Files\QGIS*")]
    roots += [Path(p) for p in glob.glob(r"C:\Program Files (x86)\QGIS*")]

    for root in roots:
        if not root.exists():
            continue
        bin_dir = root / "bin"
        if not bin_dir.exists():
            continue

        pdal_exe  = bin_dir / "pdal.exe"
        trans_exe = bin_dir / "gdal_translate.exe"
        merge_py  = bin_dir / "gdal_merge.py"

        scripts_merge = None
        for py_ver in ["Python312", "Python311", "Python310", "Python39", "Python38"]:
            cand = root / "apps" / py_ver / "Scripts" / "gdal_merge.py"
            if cand.exists():
                scripts_merge = str(cand)
                break

        if pdal_exe.exists():
            if trans_exe.exists():
                return bin_dir, str(pdal_exe), str(trans_exe)
            if merge_py.exists():
                return bin_dir, str(pdal_exe), str(merge_py)
            if scripts_merge:
                return bin_dir, str(pdal_exe), scripts_merge

    # Last resort deep scan
    try:
        for pf in Path("C:\\").rglob("pdal.exe"):
            bc   = pf.parent
            root = bc.parent
            if (bc / "gdal_translate.exe").exists():
                return bc, str(pf), str(bc / "gdal_translate.exe")
            for py_ver in ["Python312", "Python311", "Python310", "Python39", "Python38"]:
                sc = root / "apps" / py_ver / "Scripts" / "gdal_merge.py"
                if sc.exists():
                    return bc, str(pf), str(sc)
    except PermissionError:
        pass

    return None, None, None


def _build_pdal_range_filter(selected_codes: list) -> str | None:
    """
    Collapse a list of selected class codes into a compact PDAL
    filters.range limits string.
    e.g. [1,2,3,5,6] → 'Classification[1:3],Classification[5:6]'
    Returns None if selected_codes is empty.
    """
    if not selected_codes:
        return None

    codes  = sorted(selected_codes)
    ranges = []
    start  = codes[0]
    end    = codes[0]

    for code in codes[1:]:
        if code == end + 1:
            end = code
        else:
            ranges.append((start, end))
            start = end = code
    ranges.append((start, end))

    return ",".join(f"Classification[{s}:{e}]" for s, e in ranges)


def _sanitize_filename(label: str) -> str:
    """'Low Vegetation' → 'low-vegetation'"""
    return label.lower().replace(" ", "-").replace("/", "-")


# ══════════════════════════════════════════════════════════════════════════════
#  STARTUP CHECKER
# ══════════════════════════════════════════════════════════════════════════════

class StartupChecker(tk.Toplevel):
    def __init__(self, parent, on_ready):
        super().__init__(parent)
        self.on_ready = on_ready
        self.title("Uyaram - Checking dependencies")
        self.configure(bg=BG)
        self.resizable(False, False)
        self._center(520, 430)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build()
        self.after(200, self._run_checks)

    def _build(self):
        tk.Label(
            self, text="UYARAM",
            font=("Courier New", 15, "bold"), fg=ACCENT, bg=BG
        ).pack(pady=(20, 2))
        tk.Label(
            self, text="Checking dependencies…",
            font=FONT_LABEL, fg=TEXT_DIM, bg=BG
        ).pack(pady=(0, 12))
        self._log = tk.Text(
            self, font=("Courier New", 8), bg=SURFACE, fg=TEXT,
            relief="flat", highlightthickness=1,
            highlightbackground=BORDER,
            state="disabled", height=15, width=62
        )
        self._log.pack(padx=20, fill="x")
        for tag, col in [
            ("ok", SUCCESS), ("warn", WARN),
            ("err", ERROR),  ("dim",  TEXT_DIM),
            ("acc", ACCENT),
        ]:
            self._log.tag_config(tag, foreground=col)
        self._btn_frame = tk.Frame(self, bg=BG)
        self._btn_frame.pack(pady=14)

    def _write(self, text, tag=""):
        self._log.config(state="normal")
        self._log.insert("end", text + "\n", tag if tag else ())
        self._log.see("end")
        self._log.config(state="disabled")
        self.update()

    def _run_checks(self):
        self._write("── Python packages ──────────────────────────────", "dim")
        import threading
        threading.Thread(target=self._check_thread, daemon=True).start()

    def _check_thread(self):
        results = _check_python_deps()
        all_ok  = True
        for r in results:
            if r["available"]:
                note = "  (just installed)" if r["installed_now"] else ""
                tag  = "warn" if r["installed_now"] else "ok"
                self._write(f"  ✔ {r['name']}{note}", tag)
            else:
                self._write(f"  ✗ {r['name']}  - {r['error']}", "err")
                all_ok = False

        self._write("\n── QGIS / OSGeo4W tools ─────────────────────────", "dim")
        bin_dir, pdal, gdal_tool = _find_qgis_tools()

        if bin_dir:
            self._write(f"  ✔ Found in: {bin_dir}", "ok")
            self._write("    • pdal", "dim")
            self._write(
                f"    • {Path(gdal_tool).name if gdal_tool else 'gdal tool not found'}",
                "dim"
            )
        else:
            self._write("  ✗ QGIS / OSGeo4W not found", "err")
            self._write(
                "\n    Install QGIS from https://qgis.org/download/\n"
                "    It bundles PDAL and all GDAL tools automatically.",
                "warn"
            )
            all_ok = False

        self.after(0, lambda: self._show_result(all_ok, bin_dir, pdal, gdal_tool))

    def _show_result(self, py_ok, bin_dir, pdal, gdal_tool):
        if py_ok and bin_dir:
            self._write("\n  All dependencies satisfied. Launching Uyaram…", "ok")
            self.after(700, lambda: self._launch(bin_dir, pdal, gdal_tool))
        else:
            if not bin_dir:
                self._add_btn(
                    "Download QGIS", WARN, BG,
                    lambda: self._open_url("https://qgis.org/download/")
                )
            if not py_ok:
                self._write(
                    "\n  Try manually:  pip install laspy[lazrs]", "err"
                )
                self._add_btn("Close", SURFACE2, ERROR, self._on_close)
            self._add_btn("Retry", SURFACE2, TEXT, self._retry)

    def _add_btn(self, label, bg, fg, command):
        tk.Button(
            self._btn_frame, text=label, font=("Segoe UI", 9),
            fg=fg, bg=bg, activeforeground=fg, activebackground=SURFACE,
            relief="flat", cursor="hand2", padx=12, pady=6,
            command=command
        ).pack(side="left", padx=4)

    def _launch(self, bin_dir, pdal, gdal_tool):
        self.grab_release()
        self.destroy()
        self.on_ready(bin_dir, pdal, gdal_tool)

    def _retry(self):
        for w in self._btn_frame.winfo_children():
            w.destroy()
        self._write("\n── Retrying… ────────────────────────────────────", "dim")
        self.after(100, self._run_checks)

    def _open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    def _on_close(self):
        self.grab_release()
        self.master.destroy()

    def _center(self, w, h):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")


# ══════════════════════════════════════════════════════════════════════════════
#  CLASSIFICATION FILTER PANEL
# ══════════════════════════════════════════════════════════════════════════════

class ClassificationPanel(tk.Frame):
    """
    Collapsible panel with per-class LiDAR classification toggles.

    Collapsed by default — header shows a live summary of what is filtered.
    Expanded — checkboxes grouped by category, each with all/none buttons.
    Global all-on / all-off always visible in the header.

    Public API:
        get_selected_codes() → list[int] | None
        get_filter_summary() → str
        get_split_mode()     → bool
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG, **kwargs)
        self._vars: dict[int, tk.BooleanVar] = {
            code: tk.BooleanVar(value=default)
            for code, _, default, _ in CLASSIFICATIONS
        }
        self._expanded  = False
        self._split_var = tk.BooleanVar(value=False)
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────
    def _build(self):
        self._header = tk.Frame(self, bg=SURFACE2)
        self._header.pack(fill="x")

        self._toggle_btn = tk.Button(
            self._header,
            text=self._header_text(),
            font=("Courier New", 8),
            fg=TEXT_DIM, bg=SURFACE2,
            activeforeground=ACCENT, activebackground=SURFACE2,
            relief="flat", cursor="hand2",
            anchor="w", padx=8, pady=6,
            command=self._toggle
        )
        self._toggle_btn.pack(side="left", fill="x", expand=True)

        for label, fn in [("All on", self._all_on), ("All off", self._all_off)]:
            tk.Button(
                self._header, text=label, font=FONT_SMALL,
                fg=TEXT_DIM, bg=SURFACE2,
                activeforeground=TEXT, activebackground=SURFACE,
                relief="flat", cursor="hand2",
                padx=8, pady=6,
                command=fn
            ).pack(side="right")

        self._body = tk.Frame(self, bg=BG)
        self._build_body()

    def _build_body(self):
        groups: dict[str, list] = {cat: [] for cat in CATEGORY_ORDER}
        for code, label, _, cat in CLASSIFICATIONS:
            groups[cat].append((code, label))

        for cat in CATEGORY_ORDER:
            items = groups[cat]
            if not items:
                continue

            cat_row = tk.Frame(self._body, bg=BG)
            cat_row.pack(fill="x", pady=(8, 2))
            cat_colour = CATEGORY_COLOURS.get(cat, TEXT_DIM)

            tk.Label(
                cat_row,
                text=CATEGORY_LABELS[cat],
                font=("Segoe UI", 8, "bold"),
                fg=cat_colour, bg=BG
            ).pack(side="left", padx=(4, 12))

            for btn_label, state in [("all", True), ("none", False)]:
                tk.Button(
                    cat_row, text=btn_label, font=FONT_SMALL,
                    fg=TEXT_DIM, bg=BG,
                    activeforeground=TEXT, activebackground=BG,
                    relief="flat", cursor="hand2", padx=4,
                    command=lambda c=cat, s=state: self._cat_all(c, s)
                ).pack(side="right")

            grid = tk.Frame(self._body, bg=BG)
            grid.pack(fill="x", padx=4)

            for idx, (code, label) in enumerate(items):
                tk.Checkbutton(
                    grid,
                    text=f"[{code:2d}] {label}",
                    variable=self._vars[code],
                    font=("Courier New", 8),
                    fg=TEXT, bg=BG,
                    selectcolor=SURFACE2,
                    activebackground=BG,
                    activeforeground=TEXT_BRT,
                    command=self._on_change
                ).grid(
                    row=idx // 3, column=idx % 3,
                    sticky="w", padx=(0, 16), pady=1
                )

        # Split mode toggle
        tk.Frame(self._body, bg=BORDER, height=1).pack(fill="x", pady=(12, 8))
        split_row = tk.Frame(self._body, bg=BG)
        split_row.pack(fill="x")
        tk.Checkbutton(
            split_row,
            text="Export separate heightmap per selected class  (split mode)",
            variable=self._split_var,
            font=FONT_LABEL, fg=ACCENT, bg=BG,
            selectcolor=SURFACE2,
            activebackground=BG, activeforeground=TEXT,
            command=self._on_change
        ).pack(anchor="w")
        tk.Label(
            split_row,
            text="  Split mode: empty cells = 0.0 so layers stack cleanly in Blender.",
            font=FONT_SMALL, fg=TEXT_DIM, bg=BG
        ).pack(anchor="w", padx=20)
        tk.Label(
            split_row,
            text="  Warning: N selected classes = ~N× processing time.",
            font=FONT_SMALL, fg=WARN, bg=BG
        ).pack(anchor="w", padx=20)

        tk.Label(
            self._body,
            text="  Tip: if data has no classifications, leave all on — "
                 "no filter step is added to the pipeline.",
            font=FONT_SMALL, fg=TEXT_DIM, bg=BG, anchor="w"
        ).pack(fill="x", pady=(10, 6), padx=4)

    # ── Toggle ────────────────────────────────────────────────────────────
    def _toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            self._body.pack(fill="x", pady=(4, 0))
        else:
            self._body.pack_forget()
        self._update_header()

    def _update_header(self):
        self._toggle_btn.config(text=self._header_text())

    def _header_text(self) -> str:
        all_codes      = {code for code, _, _, _ in CLASSIFICATIONS}
        selected_codes = {code for code, var in self._vars.items() if var.get()}
        n_on    = len(selected_codes)
        n_total = len(all_codes)
        arrow   = "▴" if self._expanded else "▾"

        if n_on == n_total:
            summary = "all classes  ·  no filter applied"
        elif n_on == 0:
            summary = "⚠  none selected — no points will pass filter"
        else:
            off_labels = [
                label
                for code, label, _, _ in CLASSIFICATIONS
                if not self._vars[code].get()
            ]
            shown = off_labels[:4]
            rest  = len(off_labels) - len(shown)
            omit  = ", ".join(shown)
            if rest > 0:
                omit += f"  +{rest} more"
            summary = f"{n_on}/{n_total} classes  ·  filtering out: {omit}"

        if self._split_var.get():
            summary += "  ·  SPLIT MODE"

        return f"  Classification filter  ·  {summary}  {arrow}"

    def _on_change(self):
        self._update_header()

    # ── Presets ───────────────────────────────────────────────────────────
    def _all_on(self):
        for var in self._vars.values():
            var.set(True)
        self._update_header()

    def _all_off(self):
        for var in self._vars.values():
            var.set(False)
        self._update_header()

    def _cat_all(self, category: str, state: bool):
        for code, _, _, cat in CLASSIFICATIONS:
            if cat == category:
                self._vars[code].set(state)
        self._update_header()

    # ── Public API ────────────────────────────────────────────────────────
    def get_selected_codes(self) -> list | None:
        all_codes      = {code for code, _, _, _ in CLASSIFICATIONS}
        selected_codes = {code for code, var in self._vars.items() if var.get()}
        if selected_codes == all_codes:
            return None
        return sorted(selected_codes)

    def get_filter_summary(self) -> str:
        codes = self.get_selected_codes()
        if codes is None:
            return "none (all classes pass)"
        off = [
            f"[{code}] {label}"
            for code, label, _, _ in CLASSIFICATIONS
            if not self._vars[code].get()
        ]
        return f"removing: {', '.join(off)}"

    def get_split_mode(self) -> bool:
        return self._split_var.get()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ══════════════════════════════════════════════════════════════════════════════

class UyaramApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self.title("Uyaram - Point Cloud to Heightmap")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(700, 640)

        self._source_var   = tk.StringVar()
        self._output_var   = tk.StringVar()
        self._res_var      = tk.StringVar(value="0.5")
        self._mosaic_var   = tk.BooleanVar(value=False)
        self._processing   = False
        self._bin_dir      = None
        self._pdal_exe     = None
        self._gdal_tool    = None

        # Entry widget references — set during _path_row, used by browse
        self._source_entry = None
        self._output_entry = None

        self._build_ui()
        self._center_window(780, 760)
        StartupChecker(self, on_ready=self._on_deps_ok)

    def _on_deps_ok(self, bin_dir, pdal, gdal_tool):
        self._bin_dir   = bin_dir
        self._pdal_exe  = pdal
        self._gdal_tool = gdal_tool
        self.deiconify()
        self._print_logo()
        self._log_line(f"  Tools    : {bin_dir}", "dim")
        self._log_line(f"  Python   : {sys.executable}", "dim")
        self._log_line( "  Status   : Ready\n", "success")

    def _print_logo(self):
        self._log.config(state="normal")
        for line in UYARAM_LOGO.split("\n"):
            self._log.insert("end", line + "\n", "logo")
        self._log.insert("end", "\n")
        self._log.see("1.0")
        self._log.config(state="disabled")

    # ── UI Build ──────────────────────────────────────────────────────────
    def _build_ui(self):
        title = tk.Frame(self, bg=SURFACE, height=50)
        title.pack(fill="x")
        title.pack_propagate(False)
        tk.Label(
            title, text="UYARAM",
            font=("Courier New", 13, "bold"), fg=ACCENT, bg=SURFACE
        ).pack(side="left", padx=18, pady=12)
        tk.Label(
            title, text="Point Cloud → Heightmap",
            font=FONT_HEAD, fg=TEXT_DIM, bg=SURFACE
        ).pack(side="left", pady=12)
        tk.Label(
            title, text="ഉയരം  [Malayalam]",
            font=FONT_SMALL, fg=BORDER, bg=SURFACE
        ).pack(side="right", padx=18)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        content = tk.Frame(self, bg=BG)
        content.pack(fill="both", expand=True, padx=20, pady=16)

        # ── Path rows — store entry refs ──────────────────────────────────
        self._source_entry = self._path_row(
            content, "Source Folder",
            PLACEHOLDER_SOURCE,
            self._source_var, self._browse_source
        )
        self._output_entry = self._path_row(
            content, "Output Folder",
            PLACEHOLDER_OUTPUT,
            self._output_var, self._browse_output
        )

        # Options row
        opts = tk.Frame(content, bg=BG)
        opts.pack(fill="x", pady=(4, 0))
        tk.Label(
            opts, text="Resolution (m/px):",
            font=FONT_LABEL, fg=TEXT_DIM, bg=BG
        ).pack(side="left")
        tk.Entry(
            opts, textvariable=self._res_var, width=6,
            font=FONT_MONO, bg=SURFACE2, fg=ACCENT,
            insertbackground=ACCENT, relief="flat",
            highlightthickness=1, highlightbackground=BORDER
        ).pack(side="left", padx=(8, 0), ipady=4)
        tk.Label(
            opts, text="  ·  lower = more detail",
            font=FONT_SMALL, fg=TEXT_DIM, bg=BG
        ).pack(side="left")
        tk.Checkbutton(
            opts, text="Mosaic output tiles",
            variable=self._mosaic_var,
            font=FONT_LABEL, fg=TEXT, bg=BG,
            selectcolor=SURFACE2,
            activebackground=BG, activeforeground=TEXT
        ).pack(side="right")

        # Classification filter panel
        tk.Frame(content, bg=BORDER, height=1).pack(fill="x", pady=(12, 6))
        self._clf_panel = ClassificationPanel(content)
        self._clf_panel.pack(fill="x")
        tk.Frame(content, bg=BORDER, height=1).pack(fill="x", pady=(6, 0))

        # Blender info strip
        info = tk.Frame(content, bg=SURFACE2)
        info.pack(fill="x", pady=(10, 0))
        tk.Label(
            info,
            text="  Blender: Plane → Subdivide (1999 cuts) → "
                 "Displace | Non-Color | Midlevel: see log",
            font=("Courier New", 8), fg=TEXT_DIM, bg=SURFACE2, anchor="w"
        ).pack(fill="x", padx=8, pady=6)

        # Run button
        btn_row = tk.Frame(content, bg=BG)
        btn_row.pack(fill="x", pady=(10, 0))
        self._run_btn = tk.Button(
            btn_row, text="▶  Process Files",
            font=FONT_HEAD, fg=BG, bg=ACCENT,
            activeforeground=BG, activebackground="#9ecfe8",
            relief="flat", cursor="hand2",
            padx=20, pady=8,
            command=self._start_processing
        )
        self._run_btn.pack(side="left")
        self._status_lbl = tk.Label(
            btn_row, text="",
            font=("Segoe UI", 9), fg=TEXT_DIM, bg=BG
        )
        self._status_lbl.pack(side="left", padx=14)

        # Log
        tk.Frame(content, bg=BORDER, height=1).pack(fill="x", pady=(12, 8))
        log_hdr = tk.Frame(content, bg=BG)
        log_hdr.pack(fill="x", pady=(0, 6))
        tk.Label(
            log_hdr, text="LOG",
            font=("Courier New", 9, "bold"), fg=TEXT_DIM, bg=BG
        ).pack(side="left")
        tk.Button(
            log_hdr, text="clear",
            font=FONT_SMALL, fg=TEXT_DIM, bg=BG,
            activeforeground=TEXT, activebackground=BG,
            relief="flat", cursor="hand2",
            command=self._clear_log
        ).pack(side="right")

        self._log = scrolledtext.ScrolledText(
            content,
            font=("Courier New", 8),
            bg=SURFACE, fg=TEXT,
            insertbackground=ACCENT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            state="disabled",
            wrap="none"
        )
        self._log.pack(fill="both", expand=True)

        for tag, col in [
            ("logo",    ACCENT),  ("accent",  ACCENT),
            ("success", SUCCESS), ("warn",    WARN),
            ("error",   ERROR),   ("dim",     TEXT_DIM),
            ("bright",  TEXT_BRT),
        ]:
            self._log.tag_config(tag, foreground=col)

    def _path_row(self, parent, label, hint, var, command) -> tk.Entry:
        """Build a labelled path input row. Returns the Entry widget."""
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", pady=(0, 10))

        tk.Label(
            frame, text=label, font=FONT_HEAD,
            fg=TEXT_BRT, bg=BG, width=14, anchor="w"
        ).pack(side="left")

        entry = tk.Entry(
            frame, textvariable=var, font=FONT_MONO,
            bg=SURFACE2, fg=TEXT_DIM,
            insertbackground=ACCENT, relief="flat",
            highlightthickness=1, highlightbackground=BORDER
        )
        entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 8))
        entry.insert(0, hint)

        def on_in(e, en=entry, h=hint):
            if en.get() == h:
                en.delete(0, "end")
                en.config(fg=TEXT)

        def on_out(e, en=entry, h=hint, v=var):
            val = en.get().strip()
            if not val or val == h:
                en.delete(0, "end")
                en.insert(0, h)
                en.config(fg=TEXT_DIM)
                v.set("")

        entry.bind("<FocusIn>",  on_in)
        entry.bind("<FocusOut>", on_out)

        tk.Button(
            frame, text="Browse…", font=FONT_SMALL,
            fg=ACCENT, bg=SURFACE2,
            activeforeground=TEXT_BRT, activebackground=SURFACE,
            relief="flat", cursor="hand2",
            padx=10, pady=5, command=command
        ).pack(side="left")

        return entry   # caller stores this reference

    # ── Browse — write directly to entry to avoid FocusOut race ──────────
    def _browse_source(self):
        folder = filedialog.askdirectory(
            title="Select folder containing .las/.laz files"
        )
        if folder:
            self._source_var.set(folder)
            self._source_entry.config(fg=TEXT)
            self._source_entry.delete(0, "end")
            self._source_entry.insert(0, folder)

    def _browse_output(self):
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self._output_var.set(folder)
            self._output_entry.config(fg=TEXT)
            self._output_entry.delete(0, "end")
            self._output_entry.insert(0, folder)

    # ── Processing ────────────────────────────────────────────────────────
    def _start_processing(self):
        if self._processing:
            return

        # Read directly from entry widget — the ground truth for what's shown
        source = self._source_entry.get().strip()

        # Exact match against placeholder — never a substring check
        if not source or source == PLACEHOLDER_SOURCE:
            self._log_line("⚠  Select a source folder first.", "warn")
            return

        source_path = Path(source)
        if not source_path.is_dir():
            self._log_line(f"✗  Not a valid directory: {source}", "error")
            return

        # Read output from entry widget too
        raw_out = self._output_entry.get().strip()
        output_path = (
            source_path
            if (not raw_out or raw_out == PLACEHOLDER_OUTPUT)
            else Path(raw_out)
        )
        output_path.mkdir(parents=True, exist_ok=True)

        try:
            resolution = float(self._res_var.get())
            if resolution <= 0:
                raise ValueError
        except ValueError:
            self._log_line("⚠  Resolution must be a positive number.", "warn")
            return

        # Snapshot classification state before handing to thread
        selected_codes = self._clf_panel.get_selected_codes()
        filter_summary = self._clf_panel.get_filter_summary()
        split_mode     = self._clf_panel.get_split_mode()

        if split_mode and selected_codes and len(selected_codes) > 3:
            self._log_line(
                f"⚠  Split mode: {len(selected_codes)} classes "
                f"→ ~{len(selected_codes)}× processing time",
                "warn"
            )

        self._processing = True
        self._run_btn.config(state="disabled", bg=BORDER, fg=TEXT_DIM)
        self._status_lbl.config(text="Processing…", fg=ACCENT)

        import threading
        threading.Thread(
            target=self._pipeline_thread,
            args=(source_path, output_path, resolution,
                  selected_codes, filter_summary, split_mode),
            daemon=True
        ).start()

    # ── Pipeline thread ───────────────────────────────────────────────────
    def _pipeline_thread(
        self,
        source_path:    Path,
        output_path:    Path,
        resolution:     float,
        selected_codes: list | None,
        filter_summary: str,
        split_mode:     bool,
    ):
        try:
            import laspy
        except ImportError:
            self._log_line(
                "✗  laspy not available. Restart to reinstall.", "error"
            )
            self._done()
            return

        self._log_line(
            "── Batch start ─────────────────────────────────", "dim"
        )
        self._log_line(f"  Source     : {source_path}", "dim")
        self._log_line(f"  Output     : {output_path}", "dim")
        self._log_line(f"  Resolution : {resolution}m/px", "dim")
        self._log_line(f"  Filter     : {filter_summary}", "dim")
        if split_mode:
            self._log_line(
                "  Split mode : ON — separate heightmap per class\n", "accent"
            )
        else:
            self._log_line("", "dim")

        files = (
            list(source_path.glob("*.las")) +
            list(source_path.glob("*.laz"))
        )
        if not files:
            self._log_line("✗  No .las/.laz files found.", "error")
            self._done()
            return

        self._log_line(f"  {len(files)} file(s) found\n", "accent")

        # ── Phase 1: global offsets ───────────────────────────────────────
        self._log_line("Phase 1 — Global offsets…", "bright")
        tx = ty = 0.0
        min_z = float("inf")
        valid = []

        for f in files:
            try:
                with laspy.open(f) as fh:
                    tx    += (fh.header.mins[0] + fh.header.maxs[0]) / 2
                    ty    += (fh.header.mins[1] + fh.header.maxs[1]) / 2
                    min_z  = min(min_z, fh.header.mins[2])
                    valid.append(f)
            except Exception as e:
                self._log_line(
                    f"  ⚠  Header failed - {f.name}: {e}", "warn"
                )

        if not valid:
            self._log_line("✗  No valid files. Aborting.", "error")
            self._done()
            return

        gx, gy, gz = tx / len(valid), ty / len(valid), min_z
        self._log_line(f"  X offset   : {gx:.4f}", "dim")
        self._log_line(f"  Y offset   : {gy:.4f}", "dim")
        self._log_line(f"  Z ground   : {gz:.4f}m → 0.0\n", "dim")

        # ── Phase 2: process tiles ────────────────────────────────────────
        self._log_line("Phase 2 — Processing tiles…", "bright")
        ok = fail = 0

        for laz in valid:
            self._log_line(f"\n  ▶ {laz.name}", "accent")
            try:
                # Determine what passes to run for this tile
                if split_mode and selected_codes is not None:
                    # One pass per selected class
                    passes = [
                        (code, next(
                            lbl for c, lbl, _, _ in CLASSIFICATIONS
                            if c == code
                        ))
                        for code in selected_codes
                    ]
                else:
                    # Single combined pass
                    passes = [(None, "combined")]

                for code, class_label in passes:
                    # Build output filename
                    if code is None:
                        out_tif = output_path / f"{laz.stem}_heightmap.tif"
                    else:
                        safe    = _sanitize_filename(class_label)
                        out_tif = output_path / f"{laz.stem}_{safe}.tif"

                    safe_label = class_label.replace(" ", "_").replace("/", "-")
                    jf = output_path / f"{laz.stem}_{safe_label}_pipeline.json"

                    # Build PDAL pipeline
                    steps = [str(laz.resolve())]

                    if code is not None:
                        # Single class filter (split mode)
                        steps.append({
                            "type":   "filters.range",
                            "limits": f"Classification[{code}:{code}]"
                        })
                        self._log_line(
                            f"    · [{code}] {class_label}", "dim"
                        )
                    elif selected_codes is not None:
                        # Combined multi-class filter
                        limits = _build_pdal_range_filter(selected_codes)
                        if limits:
                            steps.append({
                                "type":   "filters.range",
                                "limits": limits
                            })
                            self._log_line(
                                f"    · Filter : {limits}", "dim"
                            )
                    else:
                        self._log_line(
                            "    · Filter : none (all classes)", "dim"
                        )

                    # XY + Z shift
                    steps.append({
                        "type":   "filters.transformation",
                        "matrix": (
                            f"1 0 0 -{gx} "
                            f"0 1 0 -{gy} "
                            f"0 0 1 -{gz} "
                            f"0 0 0 1"
                        )
                    })

                    # GDAL writer
                    # Split mode uses nodata=0 so empty cells sit at ground
                    # level and planes stack cleanly in Blender without
                    # negative displacement artefacts from unused regions.
                    nodata_val = -1 if (split_mode and code is not None) else -2

                    steps.append({
                        "type":        "writers.gdal",
                        "filename":    str(out_tif.resolve()),
                        "resolution":  resolution,
                        "output_type": "max",
                        "data_type":   "float",
                        "nodata":      nodata_val,
                        "gdalopts":    "COMPRESS=DEFLATE,PREDICTOR=3"
                    })

                    with open(jf, "w") as f:
                        json.dump({"pipeline": steps}, f, indent=2)

                    # Stream PDAL live
                    process = subprocess.Popen(
                        [self._pdal_exe, "pipeline", str(jf)],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True, bufsize=1, errors="replace"
                    )
                    for line in process.stdout:
                        line = line.strip()
                        if line:
                            self._log_line(f"    pdal: {line}", "dim")
                    process.wait()
                    jf.unlink(missing_ok=True)

                    if process.returncode != 0:
                        self._log_line(
                            f"    ✗ PDAL error (code {process.returncode})",
                            "error"
                        )
                        fail += 1
                        continue

                    self._log_line(
                        f"    ✔ {out_tif.name}", "success"
                    )

                # Blender values — based on full tile header
                with laspy.open(laz) as fh:
                    raw_min = fh.header.mins[2] - gz
                    raw_max = fh.header.maxs[2] - gz

                rng = raw_max - raw_min
                mid = (
                    abs(raw_min) / rng
                    if (raw_min < 0 and rng > 0)
                    else 0.0
                )
                mid_note = (
                    f"{mid:.4f}  ({abs(raw_min):.1f}m below-ground terrain)"
                    if mid > 0 else "0.0"
                )

                if raw_min < 0:
                    self._log_line(
                        f"    · Depressions : {abs(raw_min):.2f}m preserved",
                        "accent"
                    )

                self._log_line(
                    "    ┌─ Blender Displace modifier ───────────────",
                    "warn"
                )
                self._log_line(f"    │  Midlevel : {mid_note}", "warn")
                self._log_line(
                    f"    │  Strength : "
                    f"{rng:.1f} (1×)  {rng*2:.1f} (2×)  {rng*3:.1f} (3×)",
                    "warn"
                )
                self._log_line(
                    "    └──────────────────────────────────────────",
                    "warn"
                )
                ok += 1

            except Exception as e:
                self._log_line(f"    ✗ Error: {e}", "error")
                fail += 1

        # ── Mosaic (combined mode only) ───────────────────────────────────
        if self._mosaic_var.get() and ok > 0 and not split_mode:
            self._log_line(
                "\n── Mosaic ──────────────────────────────────────", "dim"
            )
            tifs   = list(output_path.glob("*_heightmap.tif"))
            merged = output_path / "merged_heightmap.tif"

            if (
                tifs and self._gdal_tool and
                self._gdal_tool.endswith("gdal_merge.py")
            ):
                cmd = (
                    [sys.executable, self._gdal_tool,
                     "-o", str(merged), "-of", "GTiff",
                     "-n", "-2", "-a_nodata", "-2",
                     "-ot", "Float32",
                     "-co", "COMPRESS=DEFLATE",
                     "-co", "PREDICTOR=3"] +
                    [str(t) for t in tifs]
                )
                try:
                    subprocess.run(
                        cmd, check=True, capture_output=True, text=True
                    )
                    self._log_line(f"  ✔ {merged.name}", "success")
                except Exception as e:
                    self._log_line(f"  ✗ Mosaic failed: {e}", "error")
            else:
                self._log_line(
                    "  ⚠  gdal_merge.py not found — mosaic skipped", "warn"
                )
                self._log_line(
                    "     Merge manually: QGIS → Raster → Miscellaneous → Merge",
                    "dim"
                )

        # ── Summary ───────────────────────────────────────────────────────
        self._log_line(
            "\n── Batch complete ──────────────────────────────", "dim"
        )
        self._log_line(
            f"  ✔ {ok} succeeded   ✗ {fail} failed",
            "success" if fail == 0 else "warn"
        )
        self._log_line(f"  Output : {output_path}", "dim")

        self._log_line(
            "\n── Blender import ──────────────────────────────", "accent"
        )
        self._log_line(
            "  1. Add Plane → Scale to real-world size (S → metres)", "dim"
        )
        self._log_line(
            "  2. Edit Mode → Select All → Right Click → Subdivide → Cuts: 1999",
            "dim"
        )
        self._log_line(
            "  3. Object Mode → Add Modifier → Displace → New Texture", "dim"
        )
        self._log_line(
            "  4. Open heightmap.tif → Color Space: Non-Color", "dim"
        )
        self._log_line(
            "  5. Midlevel and Strength: use values printed per tile above",
            "dim"
        )
        self._log_line("  6. Shade Flat (not Shade Smooth)", "dim")

        if split_mode:
            self._log_line(
                "\n── Split mode stacking in Blender ──────────────",
                "accent"
            )
            self._log_line(
                "  · Each class is a separate plane at Z=0", "dim"
            )
            self._log_line(
                "  · Empty cells = 0.0 → flat ground, no downward spikes", "dim"
            )
            self._log_line(
                "  · Stack all planes at the same XY position", "dim"
            )
            self._log_line(
                "  · Assign different materials per plane", "dim"
            )
            self._log_line(
                "  · e.g. buildings=white clay · trees=green · ground=beige\n",
                "dim"
            )
        else:
            self._log_line("", "dim")

        self._done(ok, fail)

    # ── Done ──────────────────────────────────────────────────────────────
    def _done(self, success=0, fail=0):
        def _u():
            self._processing = False
            self._run_btn.config(state="normal", bg=ACCENT, fg=BG)
            self._status_lbl.config(
                text=f"Done — {success} ok, {fail} failed",
                fg=SUCCESS if fail == 0 else WARN
            )
        self.after(0, _u)

    # ── Log ───────────────────────────────────────────────────────────────
    def _log_line(self, text, tag=""):
        def _w():
            self._log.config(state="normal")
            self._log.insert("end", text + "\n", tag if tag else ())
            self._log.see("end")
            self._log.config(state="disabled")
        self.after(0, _w)

    def _clear_log(self):
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")
        self._print_logo()

    def _center_window(self, w, h):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")


# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        app = UyaramApp()
        app.mainloop()
    except Exception as e:
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Uyaram - Fatal Error",
                f"Uyaram could not start:\n\n{e}\n\n"
                "Make sure Python 3.8+ is installed.\n"
                "Then try:  pip install laspy[lazrs]"
            )
        except Exception:
            print(f"Fatal: {e}", file=sys.stderr)
