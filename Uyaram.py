"""
Uyaram - Point Cloud to Heightmap
Malayalam: Uyaram = height

Standalone-friendly launcher with dependency checking and auto-install.
Requires : Python 3.8+, tkinter (ships with Python)
Auto-installs : laspy, numpy
Detects : PDAL (system binary - must be installed separately via QGIS or standalone)
"""

import sys
import subprocess
import importlib.util
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

# ── Colour palette ──────────────────────────────────────────────────────────
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

# ── ASCII logo (printed into log on startup) ────────────────────────────────
Uyaram_LOGO = """\
██╗   ██╗██╗   ██╗ █████╗ ██████╗  █████╗ ███╗   ███╗
██║   ██║╚██╗ ██╔╝██╔══██╗██╔══██╗██╔══██╗████╗ ████║
██║   ██║ ╚████╔╝ ███████║██████╔╝███████║██╔████╔██║
██║   ██║  ╚██╔╝  ██╔══██║██╔══██╗██╔══██║██║╚██╔╝██║
╚██████╔╝   ██║   ██║  ██║██║  ██║██║  ██║██║ ╚═╝ ██║
 ╚═════╝    ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝                                                  
  Point Cloud → Heightmap  ·  Malayalam: Uyaram = Height\
"""

# ── Known PDAL locations to probe ───────────────────────────────────────────
PDAL_SEARCH_PATHS = [
    r"C:\Program Files\QGIS 3.34\bin\pdal.exe",
    r"C:\Program Files\QGIS 3.36\bin\pdal.exe",
    r"C:\Program Files\QGIS 3.38\bin\pdal.exe",
    r"C:\Program Files\QGIS 4.0\bin\pdal.exe",
    r"C:\Program Files\QGIS 4.0.1\bin\pdal.exe",
    r"C:\Program Files\QGIS 4.2\bin\pdal.exe",
    r"C:\OSGeo4W\bin\pdal.exe",
    r"C:\OSGeo4W64\bin\pdal.exe",
    r"C:\ProgramData\miniconda3\bin\pdal.exe",
    r"C:\ProgramData\miniconda3\Scripts\pdal.exe",
    r"C:\ProgramData\anaconda3\bin\pdal.exe",
    "/usr/bin/pdal",
    "/usr/local/bin/pdal",
    "/opt/conda/bin/pdal",
    "/opt/homebrew/bin/pdal",
]

PDAL_DOWNLOAD_URL = "https://pdal.io/en/latest/download.html"
QGIS_DOWNLOAD_URL = "https://qgis.org/download/"


# ══════════════════════════════════════════════════════════════════════════════
#  DEPENDENCY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _pip_install(package):
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package, "--quiet"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            return True, f"Installed {package} successfully."
        return False, result.stderr.strip()
    except Exception as e:
        return False, str(e)


def _check_python_deps():
    required = [
        {"import": "laspy",  "pip": "laspy[lazrs]"},
        {"import": "numpy",  "pip": "numpy"},
    ]
    results = []
    for pkg in required:
        available = importlib.util.find_spec(pkg["import"]) is not None
        installed_now = False
        error = None
        if not available:
            ok, msg = _pip_install(pkg["pip"])
            if ok:
                importlib.invalidate_caches()
                available = importlib.util.find_spec(pkg["import"]) is not None
                installed_now = available
            if not available:
                error = msg
        results.append({
            "name": pkg["import"],
            "available": available,
            "installed_now": installed_now,
            "error": error,
        })
    return results


def _find_pdal():
    import shutil
    found = shutil.which("pdal")
    if found:
        return found, f"Found on PATH: {found}"
    for path_str in PDAL_SEARCH_PATHS:
        p = Path(path_str)
        if p.exists():
            return str(p), f"Found at: {p}"
    try:
        r = subprocess.run(["pdal", "--version"], capture_output=True, timeout=5)
        if r.returncode == 0:
            return "pdal", "Responding on PATH"
    except Exception:
        pass
    return None, "PDAL not found on this system."


# ══════════════════════════════════════════════════════════════════════════════
#  STARTUP CHECKER
# ══════════════════════════════════════════════════════════════════════════════

class StartupChecker(tk.Toplevel):
    def __init__(self, parent, on_ready):
        super().__init__(parent)
        self.on_ready  = on_ready
        self.pdal_path = None

        self.title("Uyaram - Checking dependencies")
        self.configure(bg=BG)
        self.resizable(False, False)
        self._center(520, 400)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build()
        self.after(200, self._run_checks)

    def _build(self):
        tk.Label(self, text="Uyaram", font=("Courier New", 15, "bold"),
                 fg=ACCENT, bg=BG).pack(pady=(20, 2))
        tk.Label(self, text="Checking dependencies…",
                 font=FONT_LABEL, fg=TEXT_DIM, bg=BG).pack(pady=(0, 12))

        self._log = tk.Text(
            self, font=("Courier New", 8), bg=SURFACE, fg=TEXT,
            relief="flat", highlightthickness=1,
            highlightbackground=BORDER,
            state="disabled", height=13, width=62
        )
        self._log.pack(padx=20, fill="x")
        self._log.tag_config("ok",   foreground=SUCCESS)
        self._log.tag_config("warn", foreground=WARN)
        self._log.tag_config("err",  foreground=ERROR)
        self._log.tag_config("dim",  foreground=TEXT_DIM)
        self._log.tag_config("acc",  foreground=ACCENT)

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
        results   = _check_python_deps()
        all_py_ok = True

        for r in results:
            if r["available"]:
                note = "  (just installed)" if r["installed_now"] else ""
                tag  = "warn" if r["installed_now"] else "ok"
                self._write(f"  ✔ {r['name']}{note}", tag)
            else:
                self._write(f"  ✗ {r['name']}  - {r['error']}", "err")
                all_py_ok = False

        self._write("\n── PDAL binary ──────────────────────────────────", "dim")
        pdal_path, pdal_msg = _find_pdal()

        if pdal_path:
            self._write(f"  ✔ pdal  {pdal_msg}", "ok")
            self.pdal_path = pdal_path
        else:
            self._write("  ✗ pdal  - not found on this system", "err")
            self._write(
                "\n    PDAL is a system tool and cannot be auto-installed.\n"
                "    Easiest route: install QGIS - it bundles PDAL.\n"
                "    Or download PDAL standalone (see buttons below).",
                "warn"
            )

        self.after(0, lambda: self._show_result(all_py_ok, pdal_path))

    def _show_result(self, py_ok, pdal_path):
        if py_ok and pdal_path:
            self._write("\n  All dependencies satisfied. Launching Uyara…", "ok")
            self.after(700, lambda: self._launch(pdal_path))
        else:
            if not pdal_path:
                self._add_btn("Download QGIS (includes PDAL)", WARN, BG,
                              lambda: self._open_url(QGIS_DOWNLOAD_URL))
                self._add_btn("PDAL standalone", SURFACE2, ACCENT,
                              lambda: self._open_url(PDAL_DOWNLOAD_URL))
                self._add_btn("Installed - retry", SURFACE2, TEXT, self._retry)
            if not py_ok:
                self._write(
                    "\n  Package install failed.\n"
                    "  Try manually:  pip install laspy[lazrs] numpy", "err"
                )
                self._add_btn("Close", SURFACE2, ERROR, self._on_close)

    def _add_btn(self, label, bg, fg, command):
        tk.Button(
            self._btn_frame, text=label, font=("Segoe UI", 9),
            fg=fg, bg=bg, activeforeground=fg, activebackground=SURFACE,
            relief="flat", cursor="hand2", padx=12, pady=6, command=command
        ).pack(side="left", padx=4)

    def _launch(self, pdal_path):
        self.grab_release()
        self.destroy()
        self.on_ready(pdal_path)

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
#  MAIN APPLICATION
# ══════════════════════════════════════════════════════════════════════════════

class UyaramApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self.title("Uyaram - Point Cloud to Heightmap")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(700, 580)

        self._source_var = tk.StringVar()
        self._output_var = tk.StringVar()
        self._res_var    = tk.StringVar(value="0.5")
        self._processing = False
        self._pdal_path  = "pdal"

        self._build_ui()
        self._center_window(740, 660)

        StartupChecker(self, on_ready=self._on_deps_ok)

    def _on_deps_ok(self, pdal_path):
        self._pdal_path = pdal_path
        self.deiconify()
        self._print_logo()
        self._log_line(f"  pdal     : {pdal_path}", "dim")
        self._log_line(f"  python   : {sys.executable}", "dim")
        self._log_line("  Status   : Ready\n", "success")

    def _print_logo(self):
        """Write the ASCII logo into the log in accent colour."""
        self._log.config(state="normal")
        for line in Uyaram_LOGO.split("\n"):
            self._log.insert("end", line + "\n", "logo")
        self._log.insert("end", "\n")
        self._log.see("end")
        self._log.config(state="disabled")

    # ── UI Build ──────────────────────────────────────────────────────────
    def _build_ui(self):
        # Title strip
        title_bar = tk.Frame(self, bg=SURFACE, height=50)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        tk.Label(
            title_bar, text="Uyaram", font=("Courier New", 13, "bold"),
            fg=ACCENT, bg=SURFACE
        ).pack(side="left", padx=18, pady=12)
        tk.Label(
            title_bar, text="Point Cloud → Heightmap",
            font=FONT_HEAD, fg=TEXT_DIM, bg=SURFACE
        ).pack(side="left", pady=12)
        tk.Label(
            title_bar, text="Uyaram - Height  [Malayalam]",
            font=("Segoe UI", 8), fg=BORDER, bg=SURFACE
        ).pack(side="right", padx=18)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        content = tk.Frame(self, bg=BG)
        content.pack(fill="both", expand=True, padx=20, pady=16)

        self._path_row(
            content, "Source Folder",
            "Folder containing .las / .laz files",
            self._source_var, self._browse_source
        )
        self._path_row(
            content, "Output Folder",
            "Leave blank to output alongside source files",
            self._output_var, self._browse_output
        )

        # Options row
        opts = tk.Frame(content, bg=BG)
        opts.pack(fill="x", pady=(4, 0))
        tk.Label(opts, text="Resolution (m/px)", font=FONT_LABEL,
                 fg=TEXT_DIM, bg=BG).pack(side="left")
        tk.Entry(
            opts, textvariable=self._res_var, width=6,
            font=FONT_MONO, bg=SURFACE2, fg=ACCENT,
            insertbackground=ACCENT, relief="flat",
            highlightthickness=1, highlightbackground=BORDER
        ).pack(side="left", padx=(8, 0), ipady=4)
        tk.Label(
            opts, text="  ·  lower = more detail, larger file",
            font=("Segoe UI", 8), fg=TEXT_DIM, bg=BG
        ).pack(side="left")

        # Run button row
        btn_row = tk.Frame(content, bg=BG)
        btn_row.pack(fill="x", pady=(14, 0))
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
            btn_row, text="", font=("Segoe UI", 9), fg=TEXT_DIM, bg=BG
        )
        self._status_lbl.pack(side="left", padx=14)

        # Log area
        tk.Frame(content, bg=BORDER, height=1).pack(fill="x", pady=(14, 8))
        log_hdr = tk.Frame(content, bg=BG)
        log_hdr.pack(fill="x", pady=(0, 6))
        tk.Label(
            log_hdr, text="LOG", font=("Courier New", 9, "bold"),
            fg=TEXT_DIM, bg=BG
        ).pack(side="left")
        tk.Button(
            log_hdr, text="clear", font=("Segoe UI", 8),
            fg=TEXT_DIM, bg=BG, activeforeground=TEXT,
            activebackground=BG, relief="flat", cursor="hand2",
            command=self._clear_log
        ).pack(side="right")

        from tkinter import scrolledtext
        self._log = scrolledtext.ScrolledText(
            content, font=("Courier New", 8), bg=SURFACE, fg=TEXT,
            insertbackground=ACCENT, relief="flat",
            highlightthickness=1, highlightbackground=BORDER,
            state="disabled", wrap="none"
        )
        self._log.pack(fill="both", expand=True)

        # Log tags
        for tag, colour in [
            ("logo",    ACCENT),
            ("accent",  ACCENT),
            ("success", SUCCESS),
            ("warn",    WARN),
            ("error",   ERROR),
            ("dim",     TEXT_DIM),
            ("bright",  TEXT_BRT),
        ]:
            self._log.tag_config(tag, foreground=colour)

    def _path_row(self, parent, label, hint, var, command):
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", pady=(0, 10))
        tk.Label(
            frame, text=label, font=FONT_HEAD,
            fg=TEXT_BRT, bg=BG, width=14, anchor="w"
        ).pack(side="left")

        entry = tk.Entry(
            frame, textvariable=var, font=FONT_MONO,
            bg=SURFACE2, fg=TEXT_DIM, insertbackground=ACCENT,
            relief="flat", highlightthickness=1, highlightbackground=BORDER
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
            frame, text="Browse…", font=("Segoe UI", 8),
            fg=ACCENT, bg=SURFACE2,
            activeforeground=TEXT_BRT, activebackground=SURFACE,
            relief="flat", cursor="hand2",
            padx=10, pady=5, command=command
        ).pack(side="left")

    # ── Browse ────────────────────────────────────────────────────────────
    def _browse_source(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(
            title="Select folder containing .las/.laz files"
        )
        if folder:
            self._source_var.set(folder)

    def _browse_output(self):
        from tkinter import filedialog
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self._output_var.set(folder)

    # ── Processing ────────────────────────────────────────────────────────
    def _start_processing(self):
        if self._processing:
            return

        source = self._source_var.get().strip()
        if not source or source == "Folder containing .las / .laz files":
            self._log_line("⚠  Select a source folder first.", "warn")
            return

        source_path = Path(source)
        if not source_path.is_dir():
            self._log_line(f"✗  Not a valid directory: {source}", "error")
            return

        raw_out         = self._output_var.get().strip()
        placeholder_out = "Leave blank to output alongside source files"
        if not raw_out or raw_out == placeholder_out:
            output_path = source_path
        else:
            output_path = Path(raw_out)
            if not output_path.exists():
                try:
                    output_path.mkdir(parents=True, exist_ok=True)
                    self._log_line(f"✦  Created output folder: {output_path}", "accent")
                except Exception as e:
                    self._log_line(f"✗  Cannot create output folder: {e}", "error")
                    return

        try:
            resolution = float(self._res_var.get())
            if resolution <= 0:
                raise ValueError
        except ValueError:
            self._log_line("⚠  Resolution must be a positive number.", "warn")
            return

        self._processing = True
        self._run_btn.config(state="disabled", bg=BORDER, fg=TEXT_DIM)
        self._status_lbl.config(text="Processing…", fg=ACCENT)

        import threading
        threading.Thread(
            target=self._pipeline_thread,
            args=(source_path, output_path, resolution),
            daemon=True
        ).start()

    def _pipeline_thread(self, source_path, output_path, resolution):
        import json
        try:
            import laspy
        except ImportError:
            self._log_line(
                "✗  laspy not available - restart Uyaram to re-run install.",
                "error"
            )
            self._done()
            return

        self._log_line("── Batch start ─────────────────────────────────", "dim")
        self._log_line(f"  Source     : {source_path}", "dim")
        self._log_line(f"  Output     : {output_path}", "dim")
        self._log_line(f"  Resolution : {resolution}m/px\n", "dim")

        files = list(source_path.glob("*.las")) + list(source_path.glob("*.laz"))
        if not files:
            self._log_line("✗  No .las/.laz files found in source folder.", "error")
            self._done()
            return

        self._log_line(f"  {len(files)} file(s) found\n", "accent")

        # Phase 1 - global offset
        self._log_line("Phase 1 - Calculating global offset…", "bright")
        total_x, total_y = 0.0, 0.0
        for f in files:
            try:
                with laspy.open(f) as fh:
                    total_x += (fh.header.mins[0] + fh.header.maxs[0]) / 2
                    total_y += (fh.header.mins[1] + fh.header.maxs[1]) / 2
            except Exception as e:
                self._log_line(f"  ⚠  Header read failed - {f.name}: {e}", "warn")

        gx = total_x / len(files)
        gy = total_y / len(files)
        self._log_line(f"  X offset : {gx:.2f}", "dim")
        self._log_line(f"  Y offset : {gy:.2f}\n", "dim")

        # Phase 2 - process files
        self._log_line("Phase 2 - Processing files…", "bright")
        ok_count = fail_count = 0

        for laz_file in files:
            self._log_line(f"\n  ▶ {laz_file.name}", "accent")
            try:
                out_tif   = output_path / f"{laz_file.stem}_heightmap.tif"
                json_path = output_path / f"{laz_file.stem}_pipeline.json"

                pipeline = {
                    "pipeline": [
                        str(laz_file.resolve()),
                        {
                            "type": "filters.transformation",
                            "matrix": f"1 0 0 -{gx} 0 1 0 -{gy} 0 0 1 0 0 0 0 1"
                        },
                        {
                            "type": "writers.gdal",
                            "filename": str(out_tif.resolve()),
                            "resolution": resolution,
                            "output_type": "max",
                            "data_type": "float",
                            "gdalopts": "COMPRESS=DEFLATE,PREDICTOR=3"
                        }
                    ]
                }

                with open(json_path, "w") as jf:
                    json.dump(pipeline, jf, indent=2)

                result = subprocess.run(
                    [self._pdal_path, "pipeline", str(json_path)],
                    capture_output=True, text=True
                )
                json_path.unlink(missing_ok=True)

                if result.returncode != 0:
                    err = result.stderr.strip() or result.stdout.strip()
                    self._log_line(f"    ✗ PDAL error: {err}", "error")
                    fail_count += 1
                    continue

                with laspy.open(laz_file) as fh:
                    min_z      = fh.header.mins[2]
                    max_z      = fh.header.maxs[2]
                    elev_range = max_z - min_z

                mid = min_z / max_z if max_z != 0 else 0.0

                self._log_line(f"    ✔ {out_tif.name}", "success")
                self._log_line(f"    · Min Z      : {min_z:.2f}m", "dim")
                self._log_line(f"    · Max Z      : {max_z:.2f}m", "dim")
                self._log_line(f"    · Range      : {elev_range:.2f}m", "dim")
                self._log_line(
                    f"    · Midlevel   : {mid:.4f}"
                    f"  ← Blender Displace modifier", "warn"
                )
                self._log_line(
                    f"    · Strength   : "
                    f"{elev_range:.1f} (1×)  "
                    f"{elev_range*2:.1f} (2×)  "
                    f"{elev_range*3:.1f} (3×)", "warn"
                )
                ok_count += 1

            except Exception as e:
                self._log_line(f"    ✗ Unexpected error: {e}", "error")
                fail_count += 1

        # Summary
        self._log_line("\n── Batch complete ──────────────────────────────", "dim")
        self._log_line(
            f"  ✔ {ok_count} succeeded   ✗ {fail_count} failed",
            "success" if fail_count == 0 else "warn"
        )
        self._log_line(f"  Output : {output_path}\n", "dim")
        self._done(ok_count, fail_count)

    def _done(self, success=0, fail=0):
        def _u():
            self._processing = False
            self._run_btn.config(state="normal", bg=ACCENT, fg=BG)
            if success or fail:
                self._status_lbl.config(
                    text=f"Done - {success} ok, {fail} failed",
                    fg=SUCCESS if fail == 0 else WARN
                )
        self.after(0, _u)

    # ── Log helpers ───────────────────────────────────────────────────────
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
                "Then try:  pip install laspy[lazrs] numpy"
            )
        except Exception:
            print(f"Fatal: {e}", file=sys.stderr)