#!/usr/bin/env python3
"""Uyaram v1.2.7 - Point Cloud → Heightmap. Malayalam: Uyaram = height."""
__version__ = "1.2.7"

import sys, os, json, subprocess, shutil, glob, tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext
from pathlib import Path

BG, SURFACE, SURFACE2, BORDER = "#0f0f10", "#161618", "#1e1e21", "#2a2a2e"
ACCENT, TEXT, TEXT_DIM, TEXT_BRT = "#7eb8d4", "#d8d8dc", "#7a7a82", "#f0f0f4"
SUCCESS, ERROR, WARN = "#6dbb8a", "#d47e7e", "#d4b896"
FONT_MONO, FONT_LABEL, FONT_HEAD, FONT_SMALL = ("Courier New", 9), ("Segoe UI", 9), ("Segoe UI", 10, "bold"), ("Segoe UI", 8)
PLACEHOLDER_SOURCE, PLACEHOLDER_OUTPUT = "Folder with .las / .laz files", "Leave blank — outputs alongside source files"

UYARAM_LOGO = f"""
  ▄▄▄  ▄▄                                 
 █▀██  ██                                 
   ██  ██              ▄          ▄       
   ██  ██  ██ ██ ▄▀▀█▄ ████▄▄▀▀█▄ ███▄███▄
   ██  ██  ██▄██ ▄█▀██ ██   ▄█▀██ ██ ██ ██
   ▀█████▄▄▄▀██▀▄▀█▄██▄█▀  ▄▀█▄██▄██ ██ ▀█
             ██                           
           ▀▀▀                            
  Point Cloud → Heightmap  ·  Malayalam: Uyaram = Height  ·  v{__version__}
"""

CLASSIFICATIONS = [
    (1, "Unclassified", False, "terrain"), (2, "Ground", True, "terrain"), (6, "Buildings", True, "terrain"),
    (17, "Bridge Deck", True, "terrain"), (3, "Low Vegetation", True, "vegetation"), (4, "Medium Vegetation", True, "vegetation"),
    (5, "High Vegetation", True, "vegetation"), (7, "Low Noise", False, "noise"), (18, "High Noise", False, "noise"),
    (16, "Overlap", False, "noise"), (9, "Water", False, "water"), (8, "Model Key / Reserved", False, "other"),
    (10, "Rail", True, "other"), (11, "Road Surface", True, "other"), (13, "Wire Guard", False, "other"),
    (14, "Wire Conductor", False, "other"), (15, "Transmission Tower", False, "other"), (19, "Overhead Structure", False, "other"),
    (20, "Ignored Ground", False, "other"),
]
CATEGORY_ORDER = ["terrain", "vegetation", "noise", "water", "other"]
CATEGORY_LABELS = dict(zip(CATEGORY_ORDER, ["Terrain & Structure", "Vegetation", "Noise", "Water", "Other / Infrastructure"]))
CATEGORY_COLOURS = {"terrain": ACCENT, "vegetation": SUCCESS, "noise": ERROR, "water": "#7ab8d4", "other": TEXT_DIM}

def _pip_install(pkg):
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", pkg, "--quiet"], capture_output=True, text=True, timeout=120)
        return r.returncode == 0, (f"Installed {pkg}." if r.returncode == 0 else r.stderr.strip())
    except Exception as e: return False, str(e)

def _check_python_deps():
    import importlib.util
    results = []
    for p in [{"import": "laspy", "pip": "laspy[lazrs]"}]:
        a = importlib.util.find_spec(p["import"]) is not None
        i, e = False, None
        if not a:
            ok, msg = _pip_install(p["pip"])
            if ok: importlib.invalidate_caches(); a = importlib.util.find_spec(p["import"]) is not None; i = a
            else: e = msg
        results.append({"name": p["import"], "available": a, "installed_now": i, "error": e})
    return results

def _find_qgis_tools():
    pdal, merge = shutil.which("pdal"), shutil.which("gdal_merge.py")
    if pdal and merge: return Path(pdal).parent, pdal, merge if Path(pdal).parent == Path(merge).parent else (Path(pdal).parent, pdal, merge)
    cands = []
    for r in [Path(p) for p in [r"C:\OSGeo4W", r"C:\OSGeo4W64"] + glob.glob(r"C:\Program Files\QGIS*") + glob.glob(r"C:\Program Files (x86)\QGIS*")]:
        if not r.exists(): continue
        bd = r / "bin"
        if not bd.exists() or not (bd / "pdal.exe").exists(): continue
        me = bd / "gdal_merge.py"
        sm = next((str(r / "apps" / v / "Scripts" / "gdal_merge.py") for v in ["Python312","Python311","Python310","Python39","Python38"] if (r / "apps" / v / "Scripts" / "gdal_merge.py").exists()), None)
        cands.append((bd, str(bd/"pdal.exe"), str(me) if me.exists() else sm, me.exists() or sm is not None))
    for b, p, m, h in cands:
        if h: return b, p, m
    return (cands[0][0], cands[0][1], cands[0][2] if cands[0][3] else None) if cands else (None, None, None)

def _get_python_for_gdal_merge(gmp):
    p = Path(gmp)
    if "apps" in p.parts and "Python" in p.parts:
        try:
            qr = Path(*p.parts[:p.parts.index("apps")])
            pe = qr / "bin" / "python.exe"
            if pe.exists(): return str(pe)
        except: pass
    return sys.executable

def _build_pdal_range_filter(codes):
    if not codes: return None
    codes, ranges, s, e = sorted(codes), [], codes[0], codes[0]
    for c in codes[1:]:
        if c == e + 1: e = c
        else: ranges.append((s, e)); s = e = c
    ranges.append((s, e))
    return ",".join(f"Classification[{x}:{y}]" for x, y in ranges)

def _sanitize_filename(l): return l.lower().replace(" ", "-").replace("/", "-")

class StartupChecker(tk.Toplevel):
    def __init__(s, parent, on_ready):
        super().__init__(parent); s.on_ready = on_ready; s.title(f"Uyaram v{__version__} - Checking dependencies")
        s.configure(bg=BG); s.resizable(False, False); s._center(520, 430); s.grab_set(); s.protocol("WM_DELETE_WINDOW", s._on_close); s._build(); s.after(200, s._run_checks)
    def _build(s):
        tk.Label(s, text="UYARAM", font=("Courier New", 15, "bold"), fg=ACCENT, bg=BG).pack(pady=(20, 2))
        tk.Label(s, text="Checking dependencies…", font=FONT_LABEL, fg=TEXT_DIM, bg=BG).pack(pady=(0, 12))
        s._log = tk.Text(s, font=("Courier New", 8), bg=SURFACE, fg=TEXT, relief="flat", highlightthickness=1, highlightbackground=BORDER, state="disabled", height=15, width=62)
        s._log.pack(padx=20, fill="x")
        for t, c in [("ok", SUCCESS), ("warn", WARN), ("err", ERROR), ("dim", TEXT_DIM), ("acc", ACCENT)]: s._log.tag_config(t, foreground=c)
        s._btn_frame = tk.Frame(s, bg=BG); s._btn_frame.pack(pady=14)
    def _write(s, text, tag=""): s._log.config(state="normal"); s._log.insert("end", text + "\n", tag if tag else ()); s._log.see("end"); s._log.config(state="disabled"); s.update()
    def _run_checks(s): s._write("── Python packages ──────────────────────────────", "dim"); import threading; threading.Thread(target=s._check_thread, daemon=True).start()
    def _check_thread(s):
        for r in _check_python_deps():
            if r["available"]: s._write(f"  ✔ {r['name']}{' (just installed)' if r['installed_now'] else ''}", "warn" if r["installed_now"] else "ok")
            else: s._write(f"  ✗ {r['name']}  - {r['error']}", "err")
        s._write("\n── QGIS / OSGeo4W tools ─────────────────────────", "dim")
        b, p, g = _find_qgis_tools()
        if b: s._write(f"  ✔ Found in: {b}", "ok"); s._write("    • pdal", "dim"); s._write(f"    • {Path(g).name if g else 'gdal_merge.py not found (mosaic skipped)'}", "dim")
        else: s._write("  ✗ QGIS / OSGeo4W not found", "err"); s._write("\n    Install QGIS from https://qgis.org/download/\n    It bundles PDAL and all GDAL tools automatically.", "warn")
        s.after(0, lambda: s._show_result(all(r["available"] for r in _check_python_deps()), b, p, g))
    def _show_result(s, py_ok, b, p, g):
        if py_ok and b: s._write("\n  All dependencies satisfied. Launching Uyaram…", "ok"); s.after(700, lambda: s._launch(b, p, g))
        else:
            if not b: s._add_btn("Download QGIS", WARN, BG, lambda: s._open_url("https://qgis.org/download/"))
            if not py_ok: s._write("\n  Try manually:  pip install laspy[lazrs]", "err"); s._add_btn("Close", SURFACE2, ERROR, s._on_close)
            s._add_btn("Retry", SURFACE2, TEXT, s._retry)
    def _add_btn(s, label, bg, fg, command): tk.Button(s._btn_frame, text=label, font=("Segoe UI", 9), fg=fg, bg=bg, activeforeground=fg, activebackground=SURFACE, relief="flat", cursor="hand2", padx=12, pady=6, command=command).pack(side="left", padx=4)
    def _launch(s, b, p, g): s.grab_release(); s.destroy(); s.on_ready(b, p, g)
    def _retry(s): [w.destroy() for w in s._btn_frame.winfo_children()]; s._write("\n── Retrying… ────────────────────────────────────", "dim"); s.after(100, s._run_checks)
    def _open_url(s, url): import webbrowser; webbrowser.open(url)
    def _on_close(s): s.grab_release(); s.master.destroy()
    def _center(s, w, h): s.update_idletasks(); sw, sh = s.winfo_screenwidth(), s.winfo_screenheight(); s.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

class ClassificationPanel(tk.Frame):
    def __init__(s, parent, **kwargs):
        super().__init__(parent, bg=BG, **kwargs)
        s._vars = {c: tk.BooleanVar(value=d) for c, _, d, _ in CLASSIFICATIONS}
        s._expanded, s._split_var = False, tk.BooleanVar(value=False); s._build()
    def _build(s):
        s._header = tk.Frame(s, bg=SURFACE2); s._header.pack(fill="x")
        s._toggle_btn = tk.Button(s._header, text=s._header_text(), font=("Courier New", 8), fg=TEXT_DIM, bg=SURFACE2, activeforeground=ACCENT, activebackground=SURFACE2, relief="flat", cursor="hand2", anchor="w", padx=8, pady=6, command=s._toggle)
        s._toggle_btn.pack(side="left", fill="x", expand=True)
        for l, f in [("All on", s._all_on), ("All off", s._all_off)]: tk.Button(s._header, text=l, font=FONT_SMALL, fg=TEXT_DIM, bg=SURFACE2, activeforeground=TEXT, activebackground=SURFACE, relief="flat", cursor="hand2", padx=8, pady=6, command=f).pack(side="right")
        s._body = tk.Frame(s, bg=BG); s._build_body()
    def _build_body(s):
        for cat in CATEGORY_ORDER:
            items = [(c, l) for c, l, _, t in CLASSIFICATIONS if t == cat]
            if not items: continue
            cr = tk.Frame(s._body, bg=BG); cr.pack(fill="x", pady=(8, 2))
            tk.Label(cr, text=CATEGORY_LABELS[cat], font=("Segoe UI", 8, "bold"), fg=CATEGORY_COLOURS[cat], bg=BG).pack(side="left", padx=(4, 12))
            for bl, st in [("all", True), ("none", False)]: tk.Button(cr, text=bl, font=FONT_SMALL, fg=TEXT_DIM, bg=BG, activeforeground=TEXT, activebackground=BG, relief="flat", cursor="hand2", padx=4, command=lambda c=cat, s=st: s._cat_all(c, s)).pack(side="right")
            gr = tk.Frame(s._body, bg=BG); gr.pack(fill="x", padx=4)
            for i, (c, l) in enumerate(items): tk.Checkbutton(gr, text=f"[{c:2d}] {l}", variable=s._vars[c], font=("Courier New", 8), fg=TEXT, bg=BG, selectcolor=SURFACE2, activebackground=BG, activeforeground=TEXT_BRT, command=s._on_change).grid(row=i//3, column=i%3, sticky="w", padx=(0, 16), pady=1)
        tk.Frame(s._body, bg=BORDER, height=1).pack(fill="x", pady=(12, 8))
        sr = tk.Frame(s._body, bg=BG); sr.pack(fill="x")
        tk.Checkbutton(sr, text="Export separate heightmap per selected class  (split mode)", variable=s._split_var, font=FONT_LABEL, fg=ACCENT, bg=BG, selectcolor=SURFACE2, activebackground=BG, activeforeground=TEXT, command=s._on_change).pack(anchor="w")
        tk.Label(sr, text="  Split mode: empty cells = -1.0 so layers stack cleanly in Blender.", font=FONT_SMALL, fg=TEXT_DIM, bg=BG).pack(anchor="w", padx=20)
        tk.Label(sr, text="  Warning: N selected classes = ~N× processing time.", font=FONT_SMALL, fg=WARN, bg=BG).pack(anchor="w", padx=20)
        tk.Label(s._body, text="  Tip: if data has no classifications, leave all on — no filter step is added.", font=FONT_SMALL, fg=TEXT_DIM, bg=BG, anchor="w").pack(fill="x", pady=(10, 6), padx=4)
    def _toggle(s): s._expanded = not s._expanded; s._body.pack(fill="x", pady=(4, 0)) if s._expanded else s._body.pack_forget(); s._update_header()
    def _update_header(s): s._toggle_btn.config(text=s._header_text())
    def _header_text(s) -> str:
        sel = {c for c, v in s._vars.items() if v.get()}; n_on, n_tot = len(sel), len(CLASSIFICATIONS); arrow = "▴" if s._expanded else "▾"
        if n_on == n_tot: summary = "all classes  ·  no filter applied"
        elif n_on == 0: summary = "⚠  none selected — no points will pass filter"
        else:
            off = [l for c, l, _, _ in CLASSIFICATIONS if c not in sel][:4]; summary = f"{n_on}/{n_tot} classes  ·  filtering out: {', '.join(off)}{'  +more' if len(off)<len(CLASSIFICATIONS)-n_on else ''}"
        if s._split_var.get(): summary += "  ·  SPLIT MODE"
        return f"  Classification filter  ·  {summary}  {arrow}"
    def _on_change(s): s._update_header()
    def _all_on(s): [v.set(True) for v in s._vars.values()]; s._update_header()
    def _all_off(s): [v.set(False) for v in s._vars.values()]; s._update_header()
    def _cat_all(s, cat, state): [s._vars[c].set(state) for c, _, _, t in CLASSIFICATIONS if t == cat]; s._update_header()
    def get_selected_codes(s): sel = {c for c, v in s._vars.items() if v.get()}; return None if len(sel) == len(CLASSIFICATIONS) else sorted(sel)
    def get_filter_summary(s): c = s.get_selected_codes(); return "none (all classes pass)" if c is None else f"removing: {', '.join(f'[{x}] {y}' for x, y, _, _ in CLASSIFICATIONS if not s._vars[x].get())}"
    def get_split_mode(s): return s._split_var.get()

class UyaramApp(tk.Tk):
    def __init__(s):
        super().__init__(); s.withdraw(); s.title(f"Uyaram v{__version__} - Point Cloud to Heightmap"); s.configure(bg=BG); s.resizable(True, True); s.minsize(700, 640)
        s._source_var, s._output_var, s._res_var, s._mosaic_var = tk.StringVar(), tk.StringVar(), tk.StringVar(value="0.5"), tk.BooleanVar(value=False)
        s._processing, s._bin_dir, s._pdal_exe, s._gdal_tool = False, None, None, None; s._source_entry = s._output_entry = None; s._build_ui(); s._center_window(780, 760); StartupChecker(s, on_ready=s._on_deps_ok)
    def _on_deps_ok(s, b, p, g): s._bin_dir, s._pdal_exe, s._gdal_tool = b, p, g; s.deiconify(); s._print_logo(); s._log_line(f"  Tools    : {b}", "dim"); s._log_line(f"  Python   : {sys.executable}", "dim"); s._log_line("  Status   : Ready\n", "success")
    def _print_logo(s): s._log.config(state="normal"); [s._log.insert("end", l + "\n", "logo") for l in UYARAM_LOGO.split("\n")]; s._log.insert("end", "\n"); s._log.see("1.0"); s._log.config(state="disabled")
    def _build_ui(s):
        title = tk.Frame(s, bg=SURFACE, height=50); title.pack(fill="x"); title.pack_propagate(False)
        tk.Label(title, text=f"UYARAM v{__version__}", font=("Courier New", 13, "bold"), fg=ACCENT, bg=SURFACE).pack(side="left", padx=18, pady=12)
        tk.Label(title, text="Point Cloud → Heightmap", font=FONT_HEAD, fg=TEXT_DIM, bg=SURFACE).pack(side="left", pady=12)
        tk.Label(title, text="ഉയരം  [Malayalam]", font=FONT_SMALL, fg=BORDER, bg=SURFACE).pack(side="right", padx=18); tk.Frame(s, bg=BORDER, height=1).pack(fill="x")
        content = tk.Frame(s, bg=BG); content.pack(fill="both", expand=True, padx=20, pady=16)
        s._source_entry = s._path_row(content, "Source Folder", PLACEHOLDER_SOURCE, s._source_var, s._browse_source)
        s._output_entry = s._path_row(content, "Output Folder", PLACEHOLDER_OUTPUT, s._output_var, s._browse_output)
        opts = tk.Frame(content, bg=BG); opts.pack(fill="x", pady=(4, 0))
        tk.Label(opts, text="Resolution (m/px):", font=FONT_LABEL, fg=TEXT_DIM, bg=BG).pack(side="left")
        tk.Entry(opts, textvariable=s._res_var, width=6, font=FONT_MONO, bg=SURFACE2, fg=ACCENT, insertbackground=ACCENT, relief="flat", highlightthickness=1, highlightbackground=BORDER).pack(side="left", padx=(8, 0), ipady=4)
        tk.Label(opts, text="  ·  lower = more detail", font=FONT_SMALL, fg=TEXT_DIM, bg=BG).pack(side="left")
        tk.Checkbutton(opts, text="Mosaic output tiles", variable=s._mosaic_var, font=FONT_LABEL, fg=TEXT, bg=BG, selectcolor=SURFACE2, activebackground=BG, activeforeground=TEXT).pack(side="right")
        tk.Frame(content, bg=BORDER, height=1).pack(fill="x", pady=(12, 6)); s._clf_panel = ClassificationPanel(content); s._clf_panel.pack(fill="x"); tk.Frame(content, bg=BORDER, height=1).pack(fill="x", pady=(6, 0))
        btn_row = tk.Frame(content, bg=BG); btn_row.pack(fill="x", pady=(10, 0))
        s._run_btn = tk.Button(btn_row, text="▶  Process Files", font=FONT_HEAD, fg=BG, bg=ACCENT, activeforeground=BG, activebackground="#9ecfe8", relief="flat", cursor="hand2", padx=20, pady=8, command=s._start_processing); s._run_btn.pack(side="left")
        s._status_lbl = tk.Label(btn_row, text="", font=("Segoe UI", 9), fg=TEXT_DIM, bg=BG); s._status_lbl.pack(side="left", padx=14)
        tk.Frame(content, bg=BORDER, height=1).pack(fill="x", pady=(12, 8)); log_hdr = tk.Frame(content, bg=BG); log_hdr.pack(fill="x", pady=(0, 6))
        tk.Label(log_hdr, text="LOG", font=("Courier New", 9, "bold"), fg=TEXT_DIM, bg=BG).pack(side="left")
        tk.Button(log_hdr, text="clear", font=FONT_SMALL, fg=TEXT_DIM, bg=BG, activeforeground=TEXT, activebackground=BG, relief="flat", cursor="hand2", command=s._clear_log).pack(side="right")
        s._log = scrolledtext.ScrolledText(content, font=("Courier New", 8), bg=SURFACE, fg=TEXT, insertbackground=ACCENT, relief="flat", highlightthickness=1, highlightbackground=BORDER, state="disabled", wrap="none"); s._log.pack(fill="both", expand=True)
        for t, c in [("logo", ACCENT), ("accent", ACCENT), ("success", SUCCESS), ("warn", WARN), ("error", ERROR), ("dim", TEXT_DIM), ("bright", TEXT_BRT)]: s._log.tag_config(t, foreground=c)
    def _path_row(s, parent, label, hint, var, command) -> tk.Entry:
        frame = tk.Frame(parent, bg=BG); frame.pack(fill="x", pady=(0, 10))
        tk.Label(frame, text=label, font=FONT_HEAD, fg=TEXT_BRT, bg=BG, width=14, anchor="w").pack(side="left")
        entry = tk.Entry(frame, textvariable=var, font=FONT_MONO, bg=SURFACE2, fg=TEXT_DIM, insertbackground=ACCENT, relief="flat", highlightthickness=1, highlightbackground=BORDER)
        entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 8)); entry.insert(0, hint)
        def on_in(e, en=entry, h=hint): en.delete(0, "end") if en.get() == h else None; en.config(fg=TEXT)
        def on_out(e, en=entry, h=hint, v=var): val = en.get().strip(); en.delete(0, "end"); en.insert(0, h); en.config(fg=TEXT_DIM); v.set("") if not val or val == h else None
        entry.bind("<FocusIn>", on_in); entry.bind("<FocusOut>", on_out)
        tk.Button(frame, text="Browse…", font=FONT_SMALL, fg=ACCENT, bg=SURFACE2, activeforeground=TEXT_BRT, activebackground=SURFACE, relief="flat", cursor="hand2", padx=10, pady=5, command=command).pack(side="left"); return entry
    def _browse_source(s): f = filedialog.askdirectory(title="Select folder containing .las/.laz files"); s._update_path(s._source_entry, f)
    def _browse_output(s): f = filedialog.askdirectory(title="Select output folder"); s._update_path(s._output_entry, f)
    def _update_path(s, entry, path): 
        if path: (s._source_var if entry is s._source_entry else s._output_var).set(path); entry.config(fg=TEXT); entry.delete(0, "end"); entry.insert(0, path)
    def _start_processing(s):
        if s._processing: return
        src = s._source_entry.get().strip()
        if not src or src == PLACEHOLDER_SOURCE: s._log_line("⚠  Select a source folder first.", "warn"); return
        sp = Path(src)
        if not sp.is_dir(): s._log_line(f"✗  Not a valid directory: {src}", "error"); return
        raw = s._output_entry.get().strip(); op = sp if not raw or raw == PLACEHOLDER_OUTPUT else Path(raw); op.mkdir(parents=True, exist_ok=True)
        try:
            res = float(s._res_var.get())
            if res <= 0: raise ValueError
        except ValueError: s._log_line("⚠  Resolution must be a positive number.", "warn"); return
        sel, summ, split = s._clf_panel.get_selected_codes(), s._clf_panel.get_filter_summary(), s._clf_panel.get_split_mode()
        if split and sel and len(sel) > 3: s._log_line(f"⚠  Split mode: {len(sel)} classes → ~{len(sel)}× processing time", "warn")
        s._processing = True; s._run_btn.config(state="disabled", bg=BORDER, fg=TEXT_DIM); s._status_lbl.config(text="Processing…", fg=ACCENT)
        import threading; threading.Thread(target=s._pipeline_thread, args=(sp, op, res, sel, summ, split), daemon=True).start()
    def _pipeline_thread(s, sp, op, res, sel, summ, split):
        try: import laspy
        except ImportError: s._log_line("✗  laspy not available. Restart to reinstall.", "error"); s._done(); return
        s._log_line("── Batch start ─────────────────────────────────", "dim"); s._log_line(f"  Source     : {sp}", "dim"); s._log_line(f"  Output     : {op}", "dim"); s._log_line(f"  Resolution : {res}m/px", "dim"); s._log_line(f"  Filter     : {summ}", "dim")
        if split: s._log_line("  Split mode : ON — separate heightmap per class\n", "accent")
        else: s._log_line("", "dim")
        files = list(sp.glob("*.las")) + list(sp.glob("*.laz"))
        if not files: s._log_line("✗  No .las/.laz files found.", "error"); s._done(); return
        s._log_line(f"  {len(files)} file(s) found\n", "accent"); s._log_line("Phase 1 — Global offsets…", "bright")
        tx = ty = 0.0; mz = float("inf"); valid = []
        for f in files:
            try:
                with laspy.open(f) as fh: tx += (fh.header.mins[0]+fh.header.maxs[0])/2; ty += (fh.header.mins[1]+fh.header.maxs[1])/2; mz = min(mz, fh.header.mins[2]); valid.append(f)
            except Exception as e: s._log_line(f"  ⚠  Header failed - {f.name}: {e}", "warn")
        if not valid: s._log_line("✗  No valid files. Aborting.", "error"); s._done(); return
        gx, gy, gz = tx/len(valid), ty/len(valid), mz; s._log_line(f"  X offset   : {gx:.4f}", "dim"); s._log_line(f"  Y offset   : {gy:.4f}", "dim"); s._log_line(f"  Z ground   : {gz:.4f}m → 0.0\n", "dim")
        s._log_line("Phase 2 — Processing tiles…", "bright"); ok = fail = 0; co = {} if split else None
        for laz in valid:
            s._log_line(f"\n  ▶ {laz.name}", "accent")
            try:
                passes = [(c, next(l for x, l, _, _ in CLASSIFICATIONS if x==c)) for c in sel] if (split and sel) else [(None, "combined")]; skips = []
                for code, lbl in passes:
                    ot = op / f"{laz.stem}_{'heightmap' if code is None else _sanitize_filename(lbl)}.tif"; sl = lbl.replace(" ", "_").replace("/", "-"); jf = op / f"{laz.stem}_{sl}_pipeline.json"; steps = [str(laz.resolve())]
                    if code is not None: steps.append({"type": "filters.range", "limits": f"Classification[{code}:{code}]"}); s._log_line(f"    · [{code}] {lbl}", "dim")
                    elif sel is not None:
                        lim = _build_pdal_range_filter(sel)
                        if lim: steps.append({"type": "filters.range", "limits": lim}); s._log_line(f"    · Filter : {lim}", "dim")
                    else: s._log_line("    · Filter : none (all classes)", "dim")
                    neg_gx, neg_gy, neg_gz = -gx, -gy, -gz
                    matrix_str = "1 0 0 {:.6f} 0 1 0 {:.6f} 0 0 1 {:.6f} 0 0 0 1".format(neg_gx, neg_gy, neg_gz)
                    steps.append({"type": "filters.transformation", "matrix": matrix_str})
                    steps.append({"type": "writers.gdal", "filename": str(ot.resolve()), "resolution": res, "output_type": "max", "data_type": "float", "nodata": -1 if (split and code is not None) else -2, "gdalopts": "COMPRESS=DEFLATE,PREDICTOR=3"})
                    with open(jf, "w") as f: json.dump({"pipeline": steps}, f, indent=2)
                    proc = subprocess.Popen([s._pdal_exe, "pipeline", str(jf)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, errors="replace")
                    out = [l.strip() for l in proc.stdout if l.strip()]; proc.wait(); jf.unlink(missing_ok=True)
                    if proc.returncode != 0:
                        if any("Unable to write GDAL data with no points" in m for m in out):
                            if code is not None: skips.append(f"[{code}]"); continue
                        s._log_line(f"    ✗ PDAL error (code {proc.returncode})", "error"); fail += 1; continue
                    s._log_line(f"    ✔ {ot.name}", "success")
                    if split and co is not None: co.setdefault(lbl if code is not None else "combined", []).append(ot)
                if skips: s._log_line(f"    ⚠  Skipped empty classes: {', '.join(skips)}", "warn")
                with laspy.open(laz) as fh: rm = fh.header.mins[2]-gz; rx = fh.header.maxs[2]-gz; rng = rx - rm
                s._log_line("    ┌─ Blender Displace modifier ───────────────", "warn"); s._log_line(f"    │  Strength : {rng:.1f} (1×)  {rng*2:.1f} (2×)  {rng*3:.1f} (3×)", "warn"); s._log_line("    └──────────────────────────────────────────", "warn"); ok += 1
            except Exception as e: s._log_line(f"    ✗ Error: {e}", "error"); fail += 1
        if s._mosaic_var.get() and ok > 0 and s._gdal_tool and s._gdal_tool.endswith("gdal_merge.py"):
            s._log_line("\n── Mosaic ──────────────────────────────────────", "dim")
            if split:
                for cn, ts in co.items():
                    if not ts: continue
                    mg = op / f"merged_{_sanitize_filename(cn)}.tif"; na = "-1"
                    cmd = [sys.executable, s._gdal_tool, "-o", str(mg), "-of", "GTiff", "-n", na, "-a_nodata", na, "-ot", "Float32", "-co", "COMPRESS=DEFLATE", "-co", "PREDICTOR=3"] + [str(t) for t in ts]
                    try: subprocess.run(cmd, check=True, capture_output=True, text=True); s._log_line(f"  ✔ {mg.name} ({cn})", "success")
                    except subprocess.CalledProcessError as e: s._log_line(f"  ✗ Mosaic failed for {cn}: {e.stderr.strip() or e.stdout.strip()}", "error")
            else:
                ts = list(op.glob("*_heightmap.tif")); mg = op / "merged_heightmap.tif"; na = "-2"; mp = _get_python_for_gdal_merge(s._gdal_tool)
                cmd = [mp, s._gdal_tool, "-o", str(mg), "-of", "GTiff", "-n", na, "-a_nodata", na, "-ot", "Float32", "-co", "COMPRESS=DEFLATE", "-co", "PREDICTOR=3"] + [str(t) for t in ts]
                try: subprocess.run(cmd, check=True, capture_output=True, text=True); s._log_line(f"  ✔ {mg.name}", "success")
                except subprocess.CalledProcessError as e: s._log_line(f"  ✗ Mosaic failed: {e.stderr.strip() or e.stdout.strip()}", "error")
        elif s._mosaic_var.get(): s._log_line("\n⚠  Mosaic requested but gdal_merge.py not found — skipping", "warn"); s._log_line("   Ensure QGIS is installed and detected, or merge manually in QGIS.", "dim")
        s._log_line("\n── Batch complete ──────────────────────────────", "dim"); s._log_line(f"  ✔ {ok} succeeded   ✗ {fail} failed", "success" if fail == 0 else "warn"); s._log_line(f"  Output : {op}", "dim"); s._done(ok, fail)
    def _done(s, success=0, fail=0):
        def _u(): s._processing = False; s._run_btn.config(state="normal", bg=ACCENT, fg=BG); s._status_lbl.config(text=f"Done — {success} ok, {fail} failed", fg=SUCCESS if fail == 0 else WARN)
        s.after(0, _u)
    def _log_line(s, text, tag=""):
        def _w(): s._log.config(state="normal"); s._log.insert("end", text + "\n", tag if tag else ()); s._log.see("end"); s._log.config(state="disabled")
        s.after(0, _w)
    def _clear_log(s): s._log.config(state="normal"); s._log.delete("1.0", "end"); s._log.config(state="disabled"); s._print_logo()
    def _center_window(s, w, h): s.update_idletasks(); sw, sh = s.winfo_screenwidth(), s.winfo_screenheight(); s.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

if __name__ == "__main__":
    try: app = UyaramApp(); app.mainloop()
    except Exception as e:
        try:
            root = tk.Tk(); root.withdraw()
            messagebox.showerror("Uyaram - Fatal Error", f"Uyaram could not start:\n\n{e}\n\nMake sure Python 3.8+ is installed.\nThen try:  pip install laspy[lazrs]")
        except Exception: print(f"Fatal: {e}", file=sys.stderr)
