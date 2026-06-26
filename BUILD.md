# AndroidManifest Report Generator — Build & Run

The whole app is a single file, `manifest_gui.py` (AXML decoder, parser, HTML
renderer, and the Tkinter GUI).

---

## Run from source (no build needed)

Requires Python 3.

```
python manifest_gui.py
```
Tip: rename to `manifest_gui.pyw` and double-click to launch with no console window.

The report and the decoded `AndroidManifest_decoded.xml` are written to the
location you choose in the GUI.

---

## Build a standalone .exe (PyInstaller)

This produces a single `ManifestReport.exe` that runs on machines **without** Python.

1. Install PyInstaller (one time):
   ```
   pip install pyinstaller
   ```

2. Build:
   ```
   pyinstaller --onefile --windowed --name ManifestReport manifest_gui.py
   ```
   - `--onefile`  → one self-contained `.exe`
   - `--windowed` → no console window appears behind the GUI

3. Result:
   ```
   dist\ManifestReport.exe
   ```
   Copy that `.exe` anywhere and run it.

### Notes / gotchas
- **First launch is slow.** `--onefile` unpacks to a temp dir on each start. For faster startup use folder mode instead (drop `--onefile`); the app then lives in `dist\ManifestReport\`.
- **Antivirus false positives** are common with PyInstaller `--onefile` builds. If flagged, the folder-mode build (no `--onefile`) usually avoids it, or add an AV exclusion.
- **Build artifacts:** PyInstaller also creates `build\` and `ManifestReport.spec` — safe to delete; they're regenerated on each build.
- **No extra dependencies.** Everything used (`tkinter`, `struct`, `xml`, `html`) is in the Python standard library, so no `--hidden-import` or data-file flags are required.

### One-line clean rebuild (PowerShell)
```
Remove-Item -Recurse -Force build, dist, ManifestReport.spec -ErrorAction SilentlyContinue; pyinstaller --onefile --windowed --name ManifestReport manifest_gui.py
```
