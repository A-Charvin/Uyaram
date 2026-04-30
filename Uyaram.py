#!/usr/bin/env python3
"""
Uyaram - Point Cloud to Heightmap
Malayalam: Uyaram = height
Version: 1.2.6

Standalone GUI.
Requires : Python 3.8+, tkinter, laspy[lazrs]
Detects  : QGIS/OSGeo4W via PATH + filesystem scan

Features:
  - Global XY + Z ground shift (ground = 0.0 across all tiles)
  - Optional per-class classification filter (collapsed by default)
  - Optional per-class heightmap export (split mode)
  - Split mode uses nodata=-1 so layers stack cleanly in Blender
  - Per-class mosaic: merges all tile outputs of the same class into one file
  - Real-time PDAL output streaming
  - Graceful handling of empty classes (no points for a class)
  - Per-tile Blender Displace Strength values printed in log
  - Mosaic uses QGIS's exact Python & environment (bypasses system Python conflicts)
"""

__version__ = "1.2.6"

import sys
import os
import json
import subprocess
import shutil
import glob
import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext
from pathlib import Path

# ── UI Theme ─────────────────────────────────────────────────────────────────
BG, SURFACE, SURFACE2, BORDER = "#0f0f10", "#161618", "#1e1e21", "#2a2a2e"
ACCENT, TEXT, TEXT_DIM, TEXT_BRT = "#7eb8d4", "#d8d8dc", "#7a7a82", "#f0f0f4"
SUCCESS, ERROR, WARN = "#6dbb8a", "#d47e7e", "#d4b896"
FONT_MONO, FONT_LABEL, FONT_HEAD, FONT_SMALL = ("Courier New", 9), ("Segoe UI", 9), ("Segoe UI", 10, "bold"), ("Segoe UI", 8)

PLACEHOLDER_SOURCE = "Folder with .las / .laz files"
PLACEHOLDER_OUTPUT = "Leave blank — outputs alongside source files"

UYARAM_LOGO = f"""\
██╗   ██╗██╗   ██╗ █████╗ ██████╗  █████╗ ███╗   ███╗
██║   ██║╚██╗ ██╔╝██╔══██╗██╔══██╗██╔══██╗████╗ ████║
██║   ██║ ╚████╔╝ ███████║██████╔╝███████║██╔████╔██║
██║   ██║  ╚██╔╝  ██╔══██║██╔══██╗██╔══██║██║╚██╔╝██║
╚██████╔╝   ██║   ██║  ██║██║  ██║██║  ██║██║ ╚═╝ ██║
 ╚═════╝    ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝
  Point Cloud → Heightmap  ·  Malayalam: Uyaram = Height  ·  v{__version__}\
"""

# ── LiDAR Classes ────────────────────────────────────────────────────────────
CLASSIFICATIONS = [
    ( 1, "Unclassified", False, "terrain"), ( 2, "Ground", True, "terrain"),
    ( 6, "Buildings", True, "terrain"), (17, "Bridge Deck", True, "terrain"),
    ( 3, "Low Vegetation", True, "vegetation"), ( 4, "Medium Vegetation", True, "vegetation"),
    ( 5, "High Vegetation", True, "vegetation"),
    ( 7, "Low Noise", False, "noise"), (18, "High Noise", False, "noise"), (16, "Overlap", False, "noise"),
    ( 9, "Water", False, "water"),
    ( 8, "Model Key / Reserved", True, "other"), (10, "Rail", True, "other"),
    (11, "Road Surface", True, "other"), (13, "Wire Guard", True, "other"),
    (14, "Wire Conductor", True, "other"), (15, "Transmission Tower", True, "other"),
    (19, "Overhead Structure", True, "other"), (20, "Ignored Ground", False, "other"),
]

CATEGORY_ORDER = ["terrain", "vegetation", "noise", "water", "other"]
CATEGORY_LABELS = {k: v for k, v in zip(CATEGORY_ORDER, ["Terrain & Structure", "Vegetation", "Noise", "Water", "Other / Infrastructure"])}
CATEGORY_COLOURS = {"terrain": ACCENT, "vegetation": SUCCESS, "noise": ERROR, "water": "#7ab8d4", "other": TEXT_DIM}


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _pip_install(package):
    try:
        res = subprocess.run([sys.executable, "-m", "pip", "install", package, "--quiet"], capture_output=True, text=True, timeout=120)
        return res.returncode == 0, (f"Installed {package}." if res.returncode == 0 else res.stderr.strip())
    except Exception as e: return False, str(e)

def _check_python_deps():
    import importlib.util
    results = []
    for pkg in [{"import": "laspy", "pip": "laspy[lazrs]"}]:
        avail = importlib.util.find_spec(pkg["import"]) is not None
        installed_now, err = False, None
        if not avail:
            ok, msg = _pip_install(pkg["pip"])
            if ok:
                importlib.invalidate_caches()
                avail = importlib.util.find_spec(pkg["import"]) is not None
                installed_now = avail
            else: err = msg
        results.append({"name": pkg["import"], "available": avail, "installed_now": installed_now, "error": err})
    return results

def _find_qgis_tools():
    """Locate pdal.exe and gdal_merge.py. Prefers locations with both."""
    pdal, merge = shutil.which("pdal"), shutil.which("gdal_merge.py")
    if pdal and merge:
        return Path(pdal).parent, pdal, merge if Path(pdal).parent == Path(merge).parent else (Path(pdal).parent, pdal, merge)

    candidates = []
    for root in [Path(p) for p in [r"C:\OSGeo4W", r"C:\OSGeo4W64"] + glob.glob(r"C:\Program Files\QGIS*") + glob.glob(r"C:\Program Files (x86)\QGIS*")]:
        if not root.exists(): continue
        bin_dir = root / "bin"
        if not bin_dir.exists() or not (bin_dir / "pdal.exe").exists(): continue
        
        merge_exe = bin_dir / "gdal_merge.py"
        scripts_merge = next((str(root / "apps" / v / "Scripts" / "gdal_merge.py") for v in ["Python312","Python311","Python310","Python39","Python38"] if (root / "apps" / v / "Scripts" / "gdal_merge.py").exists()), None)
        has_merge = merge_exe.exists() or scripts_merge is not None
        candidates.append((bin_dir, str(bin_dir/"pdal.exe"), str(merge_exe) if merge_exe.exists() else scripts_merge, has_merge))

    for b, p, m, h in candidates:
        if h: return b, p, m
    return (candidates[0][0], candidates[0][1], candidates[0][2] if candidates[0][3] else None) if candidates else (None, None, None)

def _get_qgis_python(gdal_merge_path: str) -> str:
    path = Path(gdal_merge_path)
    if "apps" in path.parts and "Python" in path.parts:
        try:
            qgis_root = Path(*path.parts[:path.parts.index("apps")])
            python_exe = qgis_root / "bin" / "python.exe"
            if python_exe.exists(): return str(python_exe)
        except (ValueError, IndexError): pass
    return sys.executable

def _build_qgis_env(gdal_merge_path: str) -> dict:
    env = os.environ.copy()
    path = Path(gdal_merge_path)
    if "apps" in path.parts:
        try:
            qgis_root = Path(*path.parts[:path.parts.index("apps")])
            bin_dir = qgis_root / "bin"
            if bin_dir.exists(): env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            for env_var, sub in [("GDAL_DATA", "share/gdal"), ("PROJ_LIB", "share/proj")]:
                if (p := qgis_root / sub).exists() and env_var not in env: env[env_var] = str(p)
        except (ValueError, IndexError): pass
    return env

def _build_pdal_range_filter(codes: list) -> str | None:
    if not codes: return None
    codes, ranges, s, e = sorted(codes), [], codes[0], codes[0]
    for c in codes[1:]:
        if c == e + 1: e = c
        else: ranges.append((s, e)); s = e = c
    ranges.append((s, e))
    return ",".join(f"Classification[{x}:{y}]" for x, y in ranges)

def _sanitize_filename(label: str) -> str:
    return label.lower().replace(" ", "-").replace("/", "-")


# ══════════════════════════════════════════════════════════════════════════════
#  UI COMPONENTS
# ══════════════════════════════════════════════════════════════════════════════

class StartupChecker(tk.Toplevel):
    def __init__(self, parent, on_ready):
        super().__init__(parent)
        self.on_ready = on_ready
        self.title(f"Uyaram v{__version__} - Checking dependencies")
        self.configure(bg=BG); self.resizable(False, False); self._center(520, 430)
        self.grab_set(); self.protocol("WM_DELETE_WINDOW", self._on_close); self._build()
        self.after(200, self._run_checks)

    def _build(self):
        tk.Label(self, text="UYARAM", font=("Courier New", 15, "bold"), fg=ACCENT, bg=BG).pack(pady=(20, 2))
        tk.Label(self, text="Checking dependencies…", font=FONT_LABEL, fg=TEXT_DIM, bg=BG).pack(pady=(0, 12))
        self._log = tk.Text(self, font=("Courier New", 8), bg=SURFACE, fg=TEXT, relief="flat", highlightthickness=1, highlightbackground=BORDER, state="disabled", height=15, width=62)
        self._log.pack(padx=20, fill="x")
        for t, c in [("ok", SUCCESS), ("warn", WARN), ("err", ERROR), ("dim", TEXT_DIM), ("acc", ACCENT)]: self._log.tag_config(t, foreground=c)
        self._btn_frame = tk.Frame(self, bg=BG); self._btn_frame.pack(pady=14)

    def _write(self, text, tag=""): self._log.config(state="normal"); self._log.insert("end", text + "\n", tag if tag else ()); self._log.see("end"); self._log.config(state="disabled"); self.update()
    def _run_checks(self): self._write("── Python packages ──────────────────────────────", "dim"); import threading; threading.Thread(target=self._check_thread, daemon=True).start()
    def _check_thread(self):
        for r in _check_python_deps():
            if r["available"]: self._write(f"  ✔ {r['name']}{' (just installed)' if r['installed_now'] else ''}", "warn" if r["installed_now"] else "ok")
            else: self._write(f"  ✗ {r['name']}  - {r['error']}", "err")
        self._write("\n── QGIS / OSGeo4W tools ─────────────────────────", "dim")
        b, p, g = _find_qgis_tools()
        if b: self._write(f"  ✔ Found in: {b}", "ok"); self._write("    • pdal", "dim"); self._write(f"    • {Path(g).name if g else 'gdal_merge.py not found (mosaic skipped)'}", "dim")
        else: self._write("  ✗ QGIS / OSGeo4W not found", "err"); self._write("\n    Install QGIS from https://qgis.org/download/\n    It bundles PDAL and all GDAL tools automatically.", "warn")
        self.after(0, lambda: self._show_result(all(r["available"] for r in _check_python_deps()), b, p, g))

    def _show_result(self, py_ok, b, p, g):
        if py_ok and b: self._write("\n  All dependencies satisfied. Launching Uyaram…", "ok"); self.after(700, lambda: self._launch(b, p, g))
        else:
            if not b: self._add_btn("Download QGIS", WARN, BG, lambda: self._open_url("https://qgis.org/download/"))
            if not py_ok: self._write("\n  Try manually:  pip install laspy[lazrs]", "err"); self._add_btn("Close", SURFACE2, ERROR, self._on_close)
            self._add_btn("Retry", SURFACE2, TEXT, self._retry)
    def _add_btn(self, label, bg, fg, command): tk.Button(self._btn_frame, text=label, font=("Segoe UI", 9), fg=fg, bg=bg, activeforeground=fg, activebackground=SURFACE, relief="flat", cursor="hand2", padx=12, pady=6, command=command).pack(side="left", padx=4)
    def _launch(self, b, p, g): self.grab_release(); self.destroy(); self.on_ready(b, p, g)
    def _retry(self): [w.destroy() for w in self._btn_frame.winfo_children()]; self._write("\n── Retrying… ────────────────────────────────────", "dim"); self.after(100, self._run_checks)
    def _open_url(self, url): import webbrowser; webbrowser.open(url)
    def _on_close(self): self.grab_release(); self.master.destroy()
    def _center(self, w, h): self.update_idletasks(); sw, sh = self.winfo_screenwidth(), self.winfo_screenheight(); self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")


class ClassificationPanel(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG, **kwargs)
        # FIX: value= instead of v=
        self._vars = {c: tk.BooleanVar(value=d) for c, _, d, _ in CLASSIFICATIONS}
        self._expanded, self._split_var = False, tk.BooleanVar(value=False)
        self._build()

    def _build(self):
        self._header = tk.Frame(self, bg=SURFACE2); self._header.pack(fill="x")
        self._toggle_btn = tk.Button(self._header, text=self._header_text(), font=("Courier New", 8), fg=TEXT_DIM, bg=SURFACE2, activeforeground=ACCENT, activebackground=SURFACE2, relief="flat", cursor="hand2", anchor="w", padx=8, pady=6, command=self._toggle)
        self._toggle_btn.pack(side="left", fill="x", expand=True)
        for l, f in [("All on", self._all_on), ("All off", self._all_off)]: tk.Button(self._header, text=l, font=FONT_SMALL, fg=TEXT_DIM, bg=SURFACE2, activeforeground=TEXT, activebackground=SURFACE, relief="flat", cursor="hand2", padx=8, pady=6, command=f).pack(side="right")
        self._body = tk.Frame(self, bg=BG); self._build_body()

    def _build_body(self):
        for cat in CATEGORY_ORDER:
            items = [(c, l) for c, l, _, t in CLASSIFICATIONS if t == cat]
            if not items: continue
            cr = tk.Frame(self._body, bg=BG); cr.pack(fill="x", pady=(8, 2))
            tk.Label(cr, text=CATEGORY_LABELS[cat], font=("Segoe UI", 8, "bold"), fg=CATEGORY_COLOURS[cat], bg=BG).pack(side="left", padx=(4, 12))
            for bl, st in [("all", True), ("none", False)]: tk.Button(cr, text=bl, font=FONT_SMALL, fg=TEXT_DIM, bg=BG, activeforeground=TEXT, activebackground=BG, relief="flat", cursor="hand2", padx=4, command=lambda c=cat, s=st: self._cat_all(c, s)).pack(side="right")
            gr = tk.Frame(self._body, bg=BG); gr.pack(fill="x", padx=4)
            for i, (c, l) in enumerate(items): tk.Checkbutton(gr, text=f"[{c:2d}] {l}", variable=self._vars[c], font=("Courier New", 8), fg=TEXT, bg=BG, selectcolor=SURFACE2, activebackground=BG, activeforeground=TEXT_BRT, command=self._on_change).grid(row=i//3, column=i%3, sticky="w", padx=(0, 16), pady=1)
        tk.Frame(self._body, bg=BORDER, height=1).pack(fill="x", pady=(12, 8))
        sr = tk.Frame(self._body, bg=BG); sr.pack(fill="x")
        tk.Checkbutton(sr, text="Export separate heightmap per selected class  (split mode)", variable=self._split_var, font=FONT_LABEL, fg=ACCENT, bg=BG, selectcolor=SURFACE2, activebackground=BG, activeforeground=TEXT, command=self._on_change).pack(anchor="w")
        tk.Label(sr, text="  Split mode: empty cells = -1.0 so layers stack cleanly in Blender.", font=FONT_SMALL, fg=TEXT_DIM, bg=BG).pack(anchor="w", padx=20)
        tk.Label(sr, text="  Warning: N selected classes = ~N× processing time.", font=FONT_SMALL, fg=WARN, bg=BG).pack(anchor="w", padx=20)
        tk.Label(self._body, text="  Tip: if data has no classifications, leave all on — no filter step is added.", font=FONT_SMALL, fg=TEXT_DIM, bg=BG, anchor="w").pack(fill="x", pady=(10, 6), padx=4)

    def _toggle(self): self._expanded = not self._expanded; self._body.pack(fill="x", pady=(4, 0)) if self._expanded else self._body.pack_forget(); self._update_header()
    def _update_header(self): self._toggle_btn.config(text=self._header_text())
    def _header_text(self) -> str:
        sel = {c for c, v in self._vars.items() if v.get()}
        n_on, n_tot = len(sel), len(CLASSIFICATIONS)
        arrow = "▴" if self._expanded else "▾"
        if n_on == n_tot: s = "all classes  ·  no filter applied"
        elif n_on == 0: s = "⚠  none selected — no points will pass filter"
        else:
            off = [l for c, l, _, _ in CLASSIFICATIONS if c not in sel][:4]
            s = f"{n_on}/{n_tot} classes  ·  filtering out: {', '.join(off)}{'  +more' if len(off)<len(CLASSIFICATIONS)-n_on else ''}"
        if self._split_var.get(): s += "  ·  SPLIT MODE"
        return f"  Classification filter  ·  {s}  {arrow}"
    def _on_change(self): self._update_header()
    def _all_on(self): [v.set(True) for v in self._vars.values()]; self._update_header()
    def _all_off(self): [v.set(False) for v in self._vars.values()]; self._update_header()
    def _cat_all(self, cat, state): [self._vars[c].set(state) for c, _, _, t in CLASSIFICATIONS if t == cat]; self._update_header()
    def get_selected_codes(self): sel = {c for c, v in self._vars.items() if v.get()}; return None if len(sel) == len(CLASSIFICATIONS) else sorted(sel)
    def get_filter_summary(self): c = self.get_selected_codes(); return "none (all classes pass)" if c is None else f"removing: {', '.join(f'[{x}] {y}' for x, y, _, _ in CLASSIFICATIONS if not self._vars[x].get())}"
    def get_split_mode(self): return self._split_var.get()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ══════════════════════════════════════════════════════════════════════════════

class UyaramApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw(); self.title(f"Uyaram v{__version__} - Point Cloud to Heightmap"); self.configure(bg=BG)
        self.resizable(True, True); self.minsize(700, 640)
        self._source_var, self._output_var, self._res_var, self._mosaic_var = tk.StringVar(), tk.StringVar(), tk.StringVar(value="0.5"), tk.BooleanVar(value=False)
        self._processing, self._bin_dir, self._pdal_exe, self._gdal_tool = False, None, None, None
        self._source_entry, self._output_entry = None, None
        self._build_ui(); self._center_window(780, 760)
        StartupChecker(self, on_ready=self._on_deps_ok)

    def _on_deps_ok(self, b, p, g): self._bin_dir, self._pdal_exe, self._gdal_tool = b, p, g; self.deiconify(); self._print_logo(); self._log_line(f"  Tools    : {b}", "dim"); self._log_line(f"  Python   : {sys.executable}", "dim"); self._log_line("  Status   : Ready\n", "success")
    def _print_logo(self): self._log.config(state="normal"); [self._log.insert("end", l + "\n", "logo") for l in UYARAM_LOGO.split("\n")]; self._log.insert("end", "\n"); self._log.see("1.0"); self._log.config(state="disabled")

    def _build_ui(self):
        title = tk.Frame(self, bg=SURFACE, height=50); title.pack(fill="x"); title.pack_propagate(False)
        tk.Label(title, text=f"UYARAM v{__version__}", font=("Courier New", 13, "bold"), fg=ACCENT, bg=SURFACE).pack(side="left", padx=18, pady=12)
        tk.Label(title, text="Point Cloud → Heightmap", font=FONT_HEAD, fg=TEXT_DIM, bg=SURFACE).pack(side="left", pady=12)
        tk.Label(title, text="ഉയരം  [Malayalam]", font=FONT_SMALL, fg=BORDER, bg=SURFACE).pack(side="right", padx=18)
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        content = tk.Frame(self, bg=BG); content.pack(fill="both", expand=True, padx=20, pady=16)
        self._source_entry = self._path_row(content, "Source Folder", PLACEHOLDER_SOURCE, self._source_var, self._browse_source)
        self._output_entry = self._path_row(content, "Output Folder", PLACEHOLDER_OUTPUT, self._output_var, self._browse_output)

        opts = tk.Frame(content, bg=BG); opts.pack(fill="x", pady=(4, 0))
        tk.Label(opts, text="Resolution (m/px):", font=FONT_LABEL, fg=TEXT_DIM, bg=BG).pack(side="left")
        tk.Entry(opts, textvariable=self._res_var, width=6, font=FONT_MONO, bg=SURFACE2, fg=ACCENT, insertbackground=ACCENT, relief="flat", highlightthickness=1, highlightbackground=BORDER).pack(side="left", padx=(8, 0), ipady=4)
        tk.Label(opts, text="  ·  lower = more detail", font=FONT_SMALL, fg=TEXT_DIM, bg=BG).pack(side="left")
        tk.Checkbutton(opts, text="Mosaic output tiles", variable=self._mosaic_var, font=FONT_LABEL, fg=TEXT, bg=BG, selectcolor=SURFACE2, activebackground=BG, activeforeground=TEXT).pack(side="right")

        tk.Frame(content, bg=BORDER, height=1).pack(fill="x", pady=(12, 6))
        self._clf_panel = ClassificationPanel(content); self._clf_panel.pack(fill="x")
        tk.Frame(content, bg=BORDER, height=1).pack(fill="x", pady=(6, 0))

        btn_row = tk.Frame(content, bg=BG); btn_row.pack(fill="x", pady=(10, 0))
        self._run_btn = tk.Button(btn_row, text="▶  Process Files", font=FONT_HEAD, fg=BG, bg=ACCENT, activeforeground=BG, activebackground="#9ecfe8", relief="flat", cursor="hand2", padx=20, pady=8, command=self._start_processing)
        self._run_btn.pack(side="left")
        self._status_lbl = tk.Label(btn_row, text="", font=("Segoe UI", 9), fg=TEXT_DIM, bg=BG); self._status_lbl.pack(side="left", padx=14)

        tk.Frame(content, bg=BORDER, height=1).pack(fill="x", pady=(12, 8))
        log_hdr = tk.Frame(content, bg=BG); log_hdr.pack(fill="x", pady=(0, 6))
        tk.Label(log_hdr, text="LOG", font=("Courier New", 9, "bold"), fg=TEXT_DIM, bg=BG).pack(side="left")
        tk.Button(log_hdr, text="clear", font=FONT_SMALL, fg=TEXT_DIM, bg=BG, activeforeground=TEXT, activebackground=BG, relief="flat", cursor="hand2", command=self._clear_log).pack(side="right")
        self._log = scrolledtext.ScrolledText(content, font=("Courier New", 8), bg=SURFACE, fg=TEXT, insertbackground=ACCENT, relief="flat", highlightthickness=1, highlightbackground=BORDER, state="disabled", wrap="none")
        self._log.pack(fill="both", expand=True)
        for t, c in [("logo", ACCENT), ("accent", ACCENT), ("success", SUCCESS), ("warn", WARN), ("error", ERROR), ("dim", TEXT_DIM), ("bright", TEXT_BRT)]: self._log.tag_config(t, foreground=c)

    def _path_row(self, parent, label, hint, var, command) -> tk.Entry:
        frame = tk.Frame(parent, bg=BG); frame.pack(fill="x", pady=(0, 10))
        tk.Label(frame, text=label, font=FONT_HEAD, fg=TEXT_BRT, bg=BG, width=14, anchor="w").pack(side="left")
        entry = tk.Entry(frame, textvariable=var, font=FONT_MONO, bg=SURFACE2, fg=TEXT_DIM, insertbackground=ACCENT, relief="flat", highlightthickness=1, highlightbackground=BORDER)
        entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 8)); entry.insert(0, hint)
        def on_in(e, en=entry, h=hint):
            if en.get() == h: en.delete(0, "end"); en.config(fg=TEXT)
        def on_out(e, en=entry, h=hint, v=var):
            val = en.get().strip()
            if not val or val == h: en.delete(0, "end"); en.insert(0, h); en.config(fg=TEXT_DIM); v.set("")
        entry.bind("<FocusIn>", on_in); entry.bind("<FocusOut>", on_out)
        tk.Button(frame, text="Browse…", font=FONT_SMALL, fg=ACCENT, bg=SURFACE2, activeforeground=TEXT_BRT, activebackground=SURFACE, relief="flat", cursor="hand2", padx=10, pady=5, command=command).pack(side="left")
        return entry

    def _browse_source(self): f = filedialog.askdirectory(title="Select folder containing .las/.laz files"); self._update_path(self._source_entry, f)
    def _browse_output(self): f = filedialog.askdirectory(title="Select output folder"); self._update_path(self._output_entry, f)
    def _update_path(self, entry, path): 
        if path: 
            (self._source_var if entry is self._source_entry else self._output_var).set(path)
            entry.config(fg=TEXT); entry.delete(0, "end"); entry.insert(0, path)

    def _start_processing(self):
        if self._processing: return
        src = self._source_entry.get().strip()
        if not src or src == PLACEHOLDER_SOURCE: self._log_line("⚠  Select a source folder first.", "warn"); return
        sp = Path(src)
        if not sp.is_dir(): self._log_line(f"✗  Not a valid directory: {src}", "error"); return
        raw = self._output_entry.get().strip()
        op = sp if not raw or raw == PLACEHOLDER_OUTPUT else Path(raw)
        op.mkdir(parents=True, exist_ok=True)
        try:
            res = float(self._res_var.get())
            if res <= 0: raise ValueError
        except ValueError: self._log_line("⚠  Resolution must be a positive number.", "warn"); return

        sel, summ, split = self._clf_panel.get_selected_codes(), self._clf_panel.get_filter_summary(), self._clf_panel.get_split_mode()
        if split and sel and len(sel) > 3: self._log_line(f"⚠  Split mode: {len(sel)} classes → ~{len(sel)}× processing time", "warn")
        self._processing = True; self._run_btn.config(state="disabled", bg=BORDER, fg=TEXT_DIM); self._status_lbl.config(text="Processing…", fg=ACCENT)
        import threading; threading.Thread(target=self._pipeline_thread, args=(sp, op, res, sel, summ, split), daemon=True).start()

    def _pipeline_thread(self, sp, op, res, sel, summ, split):
        try: import laspy
        except ImportError: self._log_line("✗  laspy not available. Restart to reinstall.", "error"); self._done(); return

        self._log_line("── Batch start ─────────────────────────────────", "dim")
        self._log_line(f"  Source     : {sp}", "dim"); self._log_line(f"  Output     : {op}", "dim"); self._log_line(f"  Resolution : {res}m/px", "dim"); self._log_line(f"  Filter     : {summ}", "dim")
        if split: self._log_line("  Split mode : ON — separate heightmap per class\n", "accent")
        else: self._log_line("", "dim")

        files = list(sp.glob("*.las")) + list(sp.glob("*.laz"))
        if not files: self._log_line("✗  No .las/.laz files found.", "error"); self._done(); return
        self._log_line(f"  {len(files)} file(s) found\n", "accent")

        self._log_line("Phase 1 — Global offsets…", "bright")
        tx = ty = 0.0; mz = float("inf"); valid = []
        for f in files:
            try:
                with laspy.open(f) as fh: tx += (fh.header.mins[0]+fh.header.maxs[0])/2; ty += (fh.header.mins[1]+fh.header.maxs[1])/2; mz = min(mz, fh.header.mins[2]); valid.append(f)
            except Exception as e: self._log_line(f"  ⚠  Header failed - {f.name}: {e}", "warn")
        if not valid: self._log_line("✗  No valid files. Aborting.", "error"); self._done(); return
        gx, gy, gz = tx/len(valid), ty/len(valid), mz
        self._log_line(f"  X offset   : {gx:.4f}", "dim"); self._log_line(f"  Y offset   : {gy:.4f}", "dim"); self._log_line(f"  Z ground   : {gz:.4f}m → 0.0\n", "dim")

        self._log_line("Phase 2 — Processing tiles…", "bright")
        ok = fail = 0; co = {} if split else None

        for laz in valid:
            self._log_line(f"\n  ▶ {laz.name}", "accent")
            try:
                passes = [(c, next(l for x, l, _, _ in CLASSIFICATIONS if x==c)) for c in sel] if (split and sel) else [(None, "combined")]
                skips = []
                for code, lbl in passes:
                    ot = op / f"{laz.stem}_{'heightmap' if code is None else _sanitize_filename(lbl)}.tif"
                    sl = lbl.replace(" ", "_").replace("/", "-")
                    jf = op / f"{laz.stem}_{sl}_pipeline.json"
                    steps = [str(laz.resolve())]
                    if code is not None: steps.append({"type": "filters.range", "limits": f"Classification[{code}:{code}]"})
                    elif sel is not None:
                        lim = _build_pdal_range_filter(sel)
                        if lim: steps.append({"type": "filters.range", "limits": lim})
                    steps.append({"type": "filters.transformation", "matrix": f"1 0 0 -{gx} 0 1 0 -{gy} 0 0 1 -{gz} 0 0 0 1"})
                    steps.append({"type": "writers.gdal", "filename": str(ot.resolve()), "resolution": res, "output_type": "max", "data_type": "float", "nodata": -1 if (split and code is not None) else -2, "gdalopts": "COMPRESS=DEFLATE,PREDICTOR=3"})
                    with open(jf, "w") as f: json.dump({"pipeline": steps}, f, indent=2)

                    proc = subprocess.Popen([self._pdal_exe, "pipeline", str(jf)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, errors="replace")
                    out = [l.strip() for l in proc.stdout if l.strip()]
                    proc.wait(); jf.unlink(missing_ok=True)
                    if proc.returncode != 0:
                        if any("Unable to write GDAL data with no points" in m for m in out):
                            if code is not None: skips.append(f"[{code}]")
                            continue
                        self._log_line(f"    ✗ PDAL error (code {proc.returncode})", "error"); fail += 1; continue
                    self._log_line(f"    ✔ {ot.name}", "success")
                    if split and co is not None: co.setdefault(lbl if code is not None else "combined", []).append(ot)
                if skips: self._log_line(f"    ⚠  Skipped empty classes: {', '.join(skips)}", "warn")

                with laspy.open(laz) as fh: rm = fh.header.mins[2]-gz; rx = fh.header.maxs[2]-gz
                rng = rx - rm
                self._log_line("    ┌─ Blender Displace modifier ───────────────", "warn")
                self._log_line(f"    │  Strength : {rng:.1f} (1×)  {rng*2:.1f} (2×)  {rng*3:.1f} (3×)", "warn")
                self._log_line("    └──────────────────────────────────────────", "warn")
                ok += 1
            except Exception as e: self._log_line(f"    ✗ Error: {e}", "error"); fail += 1

        # ── Mosaic ─────────────────────────────────────────────────────────
        if self._mosaic_var.get() and ok > 0 and self._gdal_tool and self._gdal_tool.endswith("gdal_merge.py"):
            self._log_line("\n── Mosaic ──────────────────────────────────────", "dim")
            mp = _get_qgis_python(self._gdal_tool); me = _build_qgis_env(self._gdal_tool)
            if mp != sys.executable: self._log_line(f"  Using QGIS Python: {mp}", "dim")
            if split:
                for cn, ts in co.items():
                    if not ts: continue
                    mg = op / f"merged_{_sanitize_filename(cn)}.tif"
                    cmd = [mp, self._gdal_tool, "-o", str(mg), "-of", "GTiff", "-n", "-1", "-a_nodata", "-1", "-ot", "Float32", "-co", "COMPRESS=DEFLATE", "-co", "PREDICTOR=3"] + [str(t) for t in ts]
                    try: subprocess.run(cmd, check=True, capture_output=True, text=True, env=me); self._log_line(f"  ✔ {mg.name} ({cn})", "success")
                    except subprocess.CalledProcessError as e: self._log_line(f"  ✗ Mosaic failed for {cn}: {e.stderr.strip() or e.stdout.strip()}", "error")
            else:
                ts = list(op.glob("*_heightmap.tif")); mg = op / "merged_heightmap.tif"
                cmd = [mp, self._gdal_tool, "-o", str(mg), "-of", "GTiff", "-n", "-2", "-a_nodata", "-2", "-ot", "Float32", "-co", "COMPRESS=DEFLATE", "-co", "PREDICTOR=3"] + [str(t) for t in ts]
                try: subprocess.run(cmd, check=True, capture_output=True, text=True, env=me); self._log_line(f"  ✔ {mg.name}", "success")
                except subprocess.CalledProcessError as e: self._log_line(f"  ✗ Mosaic failed: {e.stderr.strip() or e.stdout.strip()}", "error")
        elif self._mosaic_var.get():
            self._log_line("\n⚠  Mosaic requested but gdal_merge.py not found — skipping", "warn")
            self._log_line("   Ensure QGIS is installed and detected, or merge manually in QGIS.", "dim")

        self._log_line("\n── Batch complete ──────────────────────────────", "dim")
        self._log_line(f"  ✔ {ok} succeeded   ✗ {fail} failed", "success" if fail == 0 else "warn")
        self._log_line(f"  Output : {op}", "dim"); self._done(ok, fail)

    def _done(self, s=0, f=0):
        def _u(): self._processing = False; self._run_btn.config(state="normal", bg=ACCENT, fg=BG); self._status_lbl.config(text=f"Done — {s} ok, {f} failed", fg=SUCCESS if f == 0 else WARN)
        self.after(0, _u)
    def _log_line(self, text, tag=""):
        def _w(): self._log.config(state="normal"); self._log.insert("end", text + "\n", tag if tag else ()); self._log.see("end"); self._log.config(state="disabled")
        self.after(0, _w)
    def _clear_log(self): self._log.config(state="normal"); self._log.delete("1.0", "end"); self._log.config(state="disabled"); self._print_logo()
    def _center_window(self, w, h): self.update_idletasks(); sw, sh = self.winfo_screenwidth(), self.winfo_screenheight(); self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

if __name__ == "__main__":
    try: app = UyaramApp(); app.mainloop()
    except Exception as e:
        try:
            root = tk.Tk(); root.withdraw()
            messagebox.showerror("Uyaram - Fatal Error", f"Uyaram could not start:\n\n{e}\n\nMake sure Python 3.8+ is installed.\nThen try:  pip install laspy[lazrs]")
        except Exception: print(f"Fatal: {e}", file=sys.stderr)
