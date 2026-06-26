# Changelog

All notable changes to this project are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-06-26

First release.

### Features
- Decode a binary `AndroidManifest.xml` (compiled AXML) to readable plain XML.
- Generate a self-contained, styled HTML report covering:
  - app identity (package, version, SDK levels, build signature/environment),
  - application flags (`allowBackup`, `usesCleartextTraffic`, RTL) with
    secure/insecure coloring,
  - permissions split into high-privilege and other (de-duplicated, long token
    names ellipsized with full value on hover),
  - custom permissions and their protection levels,
  - exported components (the attack surface), including **implicitly-exported**
    detection (intent-filter with no `android:exported`),
  - content-provider authorities and their guards.
- Command-line interface and a Tkinter GUI (`manifest_gui.py`).
- Accepts either a manifest file or an extracted APK directory.
- Decoded XML is written next to the generated report.
- Zero third-party dependencies (Python standard library only).

### Known limitations
- Resource references (`@0x........`) are not resolved (no `resources.arsc`
  parsing).
- Deliberately obfuscated/adversarial manifests may not parse; use a dedicated
  tool (e.g. androguard, aapt2) for those.
