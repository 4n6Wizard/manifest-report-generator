# AndroidManifest Report Generator

Decode a binary **`AndroidManifest.xml`** (the compiled AXML found inside an APK)
into readable XML, and generate a clean, self-contained **HTML report** that
summarizes the most important fields — app identity, SDK levels, permissions,
custom permissions, exported components, and content-provider authorities.

Pure Python standard library. No third-party dependencies. Works as a
command-line tool **or** a simple GUI.

---

## Why

APKs store `AndroidManifest.xml` in a compiled binary format that a text editor
or browser can't read. This tool decodes it and produces:

- `AndroidManifest_decoded.xml` — valid, browser-readable plain XML
- `manifest_report.html` — a styled, at-a-glance summary

---

## Usage

### Command line
```bash
python manifest_report.py <AndroidManifest.xml | extracted_apk_dir> [output.html]
```
Examples:
```bash
python manifest_report.py path/to/AndroidManifest.xml
python manifest_report.py path/to/extracted_apk/        # finds AndroidManifest.xml inside
python manifest_report.py AndroidManifest.xml report.html
```
Both output files are written next to the input (or to the path you give).

### GUI
```bash
python manifest_gui.py
```
Browse to a manifest, choose where to save the report, click **Generate Report**,
then **Open report**. The decoded XML is written next to the report. (Tip: rename
to `manifest_gui.pyw` to launch with no console window on Windows.)

> **Notes:**
> - The GUI imports `manifest_report.py`, so keep both files in the same folder
>   when running from source.
> - Tkinter is built in on Windows/macOS Python and bundled into the `.exe`.
>   On some Linux distributions install it separately, e.g.
>   `sudo apt install python3-tk`.

---

## Example

A synthetic demo manifest (a fictional `com.example.notes` app — not a real
application) is included so you can see the output without supplying your own APK:

| File | What it is |
|---|---|
| [`examples/AndroidManifest.xml`](examples/AndroidManifest.xml) | Input manifest |
| [`examples/AndroidManifest_decoded.xml`](examples/AndroidManifest_decoded.xml) | Decoded plain XML |
| [`examples/manifest_report.html`](examples/manifest_report.html) | Generated report (open in a browser) |

Regenerate it with:
```bash
python manifest_report.py examples/AndroidManifest.xml examples/manifest_report.html
```
The example exercises every section, including a high-privilege permission, a
custom permission, and an **implicitly-exported** receiver (an `<intent-filter>`
with no `android:exported` flag).

## Build a standalone .exe (optional)

See [BUILD.md](BUILD.md). In short:
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name ManifestReport manifest_gui.py
```
Produces `dist/ManifestReport.exe`, runnable on machines without Python.

---

## What the report shows

| Section | Contents |
|---|---|
| Header | App name + package, with a generic letter-monogram app tile |
| Stats | versionName / versionCode / minSdk / targetSdk |
| Overview | application class, build signature & environment (if present), `allowBackup`, `usesCleartextTraffic`, RTL — color-coded by whether the value is the secure one |
| Permissions | requested permissions, split into **high-privilege** (red) and other; long token names are ellipsized with the full value in a tooltip |
| Custom Permissions | permissions the app *defines*, with protection level |
| Exported Components | activities/services/receivers reachable by other apps, and what guards each (the attack surface) |
| Content Providers | provider authorities, exported status, and guard |

---

## Limitations

- **Resource references are not resolved.** Values stored as resources (labels,
  icons, themes, the device-admin policy XML, etc.) appear as `@0x........`
  because the tool does not parse `resources.arsc`.
- Heuristics: the "high-privilege" set is a curated list of common AOSP
  system-only permissions; vendor permissions that share a final segment name
  could be flagged. Treat the report as a summary, not an authoritative audit.

---

## Files

| File | Role |
|---|---|
| `manifest_report.py` | Core: AXML decoder, parser, HTML renderer; CLI + importable `generate()` |
| `manifest_gui.py` | Tkinter GUI front-end |
| `BUILD.md` | Build / packaging instructions |

---

## Legal / ethical use

Only analyze APKs and manifests you are **authorized** to inspect. APK binaries
are typically copyrighted by their publishers — do **not** commit third-party
APKs, device extractions, keystores, or other private data to this repository.
This tool reads only the manifest you point it at; it does not download or
redistribute anything.

## License

[MIT](LICENSE)
