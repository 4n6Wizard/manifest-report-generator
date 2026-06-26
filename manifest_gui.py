#!/usr/bin/env python3
"""
manifest_gui.py  --  Simple Tkinter front-end for manifest_report.generate().

Pick a binary (or already-decoded) AndroidManifest.xml, choose where to save the
HTML report, and click Generate. A decoded AndroidManifest_decoded.xml is also
written next to the report.

Run:  python manifest_gui.py     (or double-click manifest_gui.pyw)
"""
import os
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog

from manifest_report import generate

PAD = 8


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AndroidManifest Report Generator")
        self.resizable(False, False)
        self.last_report = None

        frm = ttk.Frame(self, padding=14)
        frm.grid(sticky="nsew")

        ttk.Label(frm, text="AndroidManifest Report Generator",
                  font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=3,
                                                      sticky="w", pady=(0, 12))

        # --- Manifest file row ---
        ttk.Label(frm, text="Manifest file:").grid(row=1, column=0, sticky="w", pady=PAD)
        self.in_var = tk.StringVar()
        self.in_var.trace_add("write", self._autofill_output)
        in_entry = ttk.Entry(frm, textvariable=self.in_var, width=52)
        in_entry.grid(row=1, column=1, sticky="we", padx=(6, 6), pady=PAD)
        ttk.Button(frm, text="Browse...", command=self._browse_in).grid(row=1, column=2, pady=PAD)

        # --- Save report row ---
        ttk.Label(frm, text="Save report to:").grid(row=2, column=0, sticky="w", pady=PAD)
        self.out_var = tk.StringVar()
        out_entry = ttk.Entry(frm, textvariable=self.out_var, width=52)
        out_entry.grid(row=2, column=1, sticky="we", padx=(6, 6), pady=PAD)
        ttk.Button(frm, text="Browse...", command=self._browse_out).grid(row=2, column=2, pady=PAD)

        # --- Action buttons ---
        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=3, sticky="e", pady=(12, 6))
        self.gen_btn = ttk.Button(btns, text="Generate Report", command=self._run)
        self.gen_btn.grid(row=0, column=0)
        self.open_btn = ttk.Button(btns, text="Open report", command=self._open, state="disabled")
        self.open_btn.grid(row=0, column=1, padx=(8, 0))

        ttk.Separator(frm, orient="horizontal").grid(row=4, column=0, columnspan=3,
                                                     sticky="we", pady=(6, 10))

        # --- Status area ---
        self.status = tk.Text(frm, height=6, width=72, relief="flat",
                              background=self.cget("background"), wrap="word",
                              borderwidth=0, font=("Consolas", 9))
        self.status.grid(row=5, column=0, columnspan=3, sticky="we")
        self.status.configure(state="disabled")
        self._set_status("Ready. Choose a manifest file to begin.", "muted")

        # text colors
        self.status.tag_configure("muted", foreground="#777777")
        self.status.tag_configure("ok", foreground="#1a7f37")
        self.status.tag_configure("err", foreground="#cf222e")

        frm.columnconfigure(1, weight=1)

    # ------------------------------------------------------------------ helpers
    def _set_status(self, msg, tag="muted"):
        self.status.configure(state="normal")
        self.status.delete("1.0", "end")
        self.status.insert("1.0", msg, tag)
        self.status.configure(state="disabled")

    def _browse_in(self):
        path = filedialog.askopenfilename(
            title="Select AndroidManifest.xml",
            filetypes=[("AndroidManifest", "AndroidManifest.xml"),
                       ("XML files", "*.xml"), ("All files", "*.*")])
        if path:
            self.in_var.set(path)

    def _browse_out(self):
        path = filedialog.asksaveasfilename(
            title="Save report as",
            defaultextension=".html",
            initialfile="manifest_report.html",
            filetypes=[("HTML report", "*.html"), ("All files", "*.*")])
        if path:
            self.out_var.set(path)

    def _autofill_output(self, *_):
        """When a manifest is picked, suggest a default report path next to it."""
        src = self.in_var.get().strip()
        if not src:
            return
        base = src if os.path.isdir(src) else os.path.dirname(src)
        if base:
            self.out_var.set(os.path.join(base, "manifest_report.html"))

    # ------------------------------------------------------------------ actions
    def _run(self):
        src = self.in_var.get().strip()
        out = self.out_var.get().strip() or None
        if not src:
            self._set_status("Please choose a manifest file first.", "err")
            return
        self.gen_btn.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        self._set_status("Generating...", "muted")
        # parsing is fast, but run off the UI thread to stay responsive
        threading.Thread(target=self._work, args=(src, out), daemon=True).start()

    def _work(self, src, out):
        try:
            data = generate(src, out)
        except Exception as e:  # noqa: BLE001 - surface any failure to the user
            self.after(0, self._done_err, str(e))
        else:
            self.after(0, self._done_ok, data)

    def _done_ok(self, data):
        self.last_report = data["out_html"]
        msg = (
            "Done.\n\n"
            "Package    : %s\n"
            "Version    : %s (code %s)\n"
            "Permissions: %d  (%d high-privilege)\n"
            "Exported   : %d components   Providers: %d\n\n"
            "Report : %s\n"
            "Decoded: %s"
            % (data["package"], data["versionName"], data["versionCode"],
               data["perm_count"], len(data["perm_high"]),
               len(data["exported"]), len(data["providers"]),
               data["out_html"], data["out_xml"]))
        self._set_status(msg, "ok")
        self.gen_btn.configure(state="normal")
        self.open_btn.configure(state="normal")

    def _done_err(self, err):
        self._set_status("Error: " + err, "err")
        self.gen_btn.configure(state="normal")

    def _open(self):
        if self.last_report and os.path.isfile(self.last_report):
            # cross-platform: open the report in the default browser
            webbrowser.open(Path(self.last_report).resolve().as_uri())


if __name__ == "__main__":
    App().mainloop()
