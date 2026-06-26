#!/usr/bin/env python3
"""
manifest_gui.py  --  Decode a binary AndroidManifest.xml and build a styled,
                     self-contained HTML report.  Single-file GUI application.

Pick a binary (or already-decoded) AndroidManifest.xml, choose where to save the
HTML report, and click Generate. A decoded AndroidManifest_decoded.xml is also
written next to the report.

Run:  python manifest_gui.py     (or double-click manifest_gui.pyw)
"""
import os
import struct
import html
import threading
import webbrowser
from pathlib import Path
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import ttk, filedialog

__version__ = "1.1.0"

ANDROID_NS = "http://schemas.android.com/apk/res/android"
A = "{%s}" % ANDROID_NS  # qualified-name prefix for android: attributes


# ===========================================================================
# 1. Binary XML (AXML) decoder  ->  plain XML string
# ===========================================================================
def _esc(v):
    if v is None:
        return ''
    return (v.replace('&', '&amp;').replace('<', '&lt;')
             .replace('>', '&gt;').replace('"', '&quot;'))


def decode_axml(path):
    with open(path, 'rb') as f:
        data = f.read()
    strings = []
    ns_map = {}
    out = []
    indent = 0

    def s(idx):
        if idx == 0xFFFFFFFF or idx < 0 or idx >= len(strings):
            return None
        return strings[idx]

    def fmt_val(dtype, val):
        if dtype == 0x03: return s(val)
        if dtype == 0x12: return 'true' if val != 0 else 'false'
        if dtype == 0x10: return str(struct.unpack('<i', struct.pack('<I', val))[0])
        if dtype == 0x11: return hex(val)
        if dtype == 0x01: return '@0x%08x' % val
        if dtype == 0x02: return '?0x%08x' % val
        if dtype == 0x04: return str(struct.unpack('<f', struct.pack('<I', val))[0])
        return '0x%08x' % val

    p = 8  # skip file header
    while p < len(data):
        if p + 8 > len(data):
            break
        ctype, chsize, csize = struct.unpack('<HHI', data[p:p+8])
        if csize <= 0:
            break
        if ctype == 0x0001:  # string pool
            scount, stylecount, flags, soffset, styoff = struct.unpack('<IIIII', data[p+8:p+28])
            is_utf8 = (flags & (1 << 8)) != 0
            offsets = struct.unpack('<%dI' % scount, data[p+28:p+28+4*scount])
            base = p + soffset
            for off in offsets:
                o = base + off
                if is_utf8:
                    cl = data[o]; o += 1
                    if cl & 0x80:
                        cl = ((cl & 0x7F) << 8) | data[o]; o += 1
                    bl = data[o]; o += 1
                    if bl & 0x80:
                        bl = ((bl & 0x7F) << 8) | data[o]; o += 1
                    strings.append(data[o:o+bl].decode('utf-8', 'replace'))
                else:
                    cl = struct.unpack('<H', data[o:o+2])[0]; o += 2
                    if cl & 0x8000:
                        cl = ((cl & 0x7FFF) << 16) | struct.unpack('<H', data[o:o+2])[0]; o += 2
                    strings.append(data[o:o+cl*2].decode('utf-16-le', 'replace'))
        elif ctype == 0x0100:  # start namespace
            prefix, uri = struct.unpack('<II', data[p+16:p+24])
            ns_map[s(uri)] = s(prefix)
        elif ctype == 0x0102:  # start element
            ns, name = struct.unpack('<II', data[p+16:p+24])
            attrstart = struct.unpack('<H', data[p+24:p+26])[0]
            attrcount = struct.unpack('<H', data[p+28:p+30])[0]
            tag = s(name)
            attrs = []
            ap = p + 16 + attrstart
            for _ in range(attrcount):
                a_ns, a_name, a_raw = struct.unpack('<III', data[ap:ap+12])
                a_dtype = struct.unpack('<B', data[ap+15:ap+16])[0]
                a_val = struct.unpack('<I', data[ap+16:ap+20])[0]
                aname = s(a_name)
                pfx = ns_map.get(s(a_ns)) if a_ns != 0xFFFFFFFF else None
                full = ('%s:%s' % (pfx, aname)) if pfx else aname
                attrs.append('%s="%s"' % (full, _esc(fmt_val(a_dtype, a_val))))
                ap += 20
            if not out:  # declare namespaces on the root element
                for uri, pfx in ns_map.items():
                    if uri and pfx:
                        attrs.insert(0, 'xmlns:%s="%s"' % (pfx, _esc(uri)))
            attr_str = (' ' + ' '.join(attrs)) if attrs else ''
            out.append('  ' * indent + '<%s%s>' % (tag, attr_str))
            indent += 1
        elif ctype == 0x0103:  # end element
            indent -= 1
            ns, name = struct.unpack('<II', data[p+16:p+24])
            out.append('  ' * indent + '</%s>' % s(name))
        p += csize
    return '<?xml version="1.0" encoding="utf-8"?>\n' + '\n'.join(out)


# ===========================================================================
# 2. Extract the interesting fields from the decoded manifest
# ===========================================================================
# High-privilege / system-only permissions worth flagging in red.
HIGH_PRIV = {
    "INSTALL_PACKAGES", "DELETE_PACKAGES", "INSTALL_EXISTING_PACKAGES",
    "MANAGE_USERS", "INTERACT_ACROSS_USERS", "INTERACT_ACROSS_USERS_FULL",
    "ACCESS_HIDDEN_PROFILES_FULL", "MANAGE_PROFILE_AND_DEVICE_OWNERS",
    "MANAGE_DEVICE_ADMINS", "BIND_DEVICE_ADMIN", "WRITE_SECURE_SETTINGS",
    "CHANGE_COMPONENT_ENABLED_STATE", "READ_PRIVILEGED_PHONE_STATE",
    "GET_ACCOUNTS_PRIVILEGED", "USE_BIOMETRIC_INTERNAL", "MANAGE_EXTERNAL_STORAGE",
    "REQUEST_DELETE_PACKAGES", "ACCESS_KEYGUARD_SECURE_STORAGE",
    "MANAGE_NOTIFICATIONS",
}
PROTECTION = {  # android:protectionLevel flag values -> label, css class
    "0x1": ("dangerous", "t-warn"),
    "0x2": ("signature", "t-info"),
    "0x3": ("signature + privileged", "t-warn"),
}


def short_name(n):
    """com.foo.bar.Baz -> Baz ; keep custom-permission tails readable."""
    if not n:
        return n
    return n.rsplit('.', 1)[-1] if '.' in n else n


def ellipsize(s, head=14, tail=8):
    """Shorten very long tokens (e.g. a push-token permission whose name embeds
    a long hex string) for display: 'TOKEN_a1b2c3d4...ef5678'. Short strings are
    returned unchanged."""
    if not s or len(s) <= head + tail + 3:
        return s
    return s[:head] + "..." + s[-tail:]


def parse_manifest(xml_text):
    root = ET.fromstring(xml_text)
    app = root.find("application")
    d = {
        "package": root.get("package", "?"),
        "versionName": root.get(A + "versionName", "?"),
        "versionCode": root.get(A + "versionCode", "?"),
        "compileSdk": root.get(A + "compileSdkVersion", "?"),
    }
    uses_sdk = root.find("uses-sdk")
    d["minSdk"] = uses_sdk.get(A + "minSdkVersion", "?") if uses_sdk is not None else "?"
    d["targetSdk"] = uses_sdk.get(A + "targetSdkVersion", "?") if uses_sdk is not None else "?"

    # application-level flags
    d["appName"] = (app.get(A + "name") if app is not None else None) or "?"
    d["allowBackup"] = app.get(A + "allowBackup") if app is not None else None
    d["cleartext"] = app.get(A + "usesCleartextTraffic") if app is not None else None
    d["rtl"] = app.get(A + "supportsRtl") if app is not None else None

    # build signature meta (Samsung-specific, optional)
    d["buildSig"] = None
    d["env"] = None
    if app is not None:
        for m in app.findall("meta-data"):
            if m.get(A + "name") == "SPDE.build.signature":
                d["buildSig"] = m.get(A + "value")
            if m.get(A + "name") == "SPDE.env.version":
                d["env"] = m.get(A + "value")

    # permissions requested (de-duplicated for an accurate count)
    perms = [u.get(A + "name", "") for u in root.findall("uses-permission")]
    d["perm_count"] = len(set(perms))
    d["perm_high"] = sorted({p for p in perms if short_name(p) in HIGH_PRIV})
    d["perm_other"] = sorted({p for p in perms if short_name(p) not in HIGH_PRIV})

    # custom permissions defined
    d["custom_perms"] = []
    for pm in root.findall("permission"):
        lvl = pm.get(A + "protectionLevel", "")
        label, cls = PROTECTION.get(lvl, (lvl or "normal", "t-muted"))
        d["custom_perms"].append((pm.get(A + "name", "?"), label, cls))
    d["custom_perms"].sort()

    # components
    d["exported"] = []
    d["providers"] = []
    if app is not None:
        for kind, tag in (("Activity", "activity"), ("Activity", "activity-alias"),
                          ("Receiver", "receiver"), ("Service", "service")):
            for c in app.findall(tag):
                name = c.get(A + "name", "?")
                exp = c.get(A + "exported")
                perm = c.get(A + "permission")
                enabled = c.get(A + "enabled")
                has_intent = c.find("intent-filter") is not None
                # exported="true", OR implicitly exported: no explicit flag but
                # an intent-filter is present (the pre-API-31 default).
                implicit = exp is None and has_intent
                if exp == "true" or implicit:
                    d["exported"].append({
                        "name": name, "kind": kind, "perm": perm,
                        "enabled": enabled, "has_intent": has_intent,
                        "implicit": implicit,
                    })
        for pv in app.findall("provider"):
            d["providers"].append({
                "name": pv.get(A + "name", "?"),
                "authorities": pv.get(A + "authorities", ""),
                "exported": pv.get(A + "exported"),
                "perm": pv.get(A + "permission"),
                "grant": pv.get(A + "grantUriPermissions"),
            })
    return d


# ===========================================================================
# 3. Render HTML
# ===========================================================================
CSS = """
:root{--bg:#0f1419;--card:#1a2027;--card2:#222b34;--line:#2c3742;--txt:#e6edf3;
--muted:#9aa7b4;--accent:#4f9cf9;--accent2:#7c5cff;--ok:#3fb950;--warn:#d29922;--danger:#f85149;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;line-height:1.5}
.wrap{max-width:1100px;margin:0 auto;padding:32px 20px 80px}
header{display:flex;align-items:center;gap:18px;margin-bottom:8px}
.logo{width:58px;height:58px;border-radius:14px;flex:0 0 auto;background:linear-gradient(135deg,var(--accent),var(--accent2));display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:700;color:#fff;text-transform:uppercase;user-select:none}
h1{font-size:24px;margin:0}.sub{color:var(--muted);font-size:14px;margin-top:2px}
.pkg{font-family:ui-monospace,Consolas,monospace;color:var(--accent);font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin:24px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.stat .k{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.5px}
.stat .v{font-size:20px;font-weight:600;margin-top:4px}
section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin:22px 0}
section h2{font-size:17px;margin:0 0 4px;display:flex;align-items:center;gap:9px}
.hint{color:var(--muted);font-size:13px;margin:0 0 16px}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.4px}
tr:last-child td{border-bottom:none}
td.mono,.mono{font-family:ui-monospace,Consolas,monospace;font-size:12.5px}
.tag{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11.5px;font-weight:600;white-space:nowrap}
.t-ok{background:rgba(63,185,80,.15);color:var(--ok)}
.t-warn{background:rgba(210,153,34,.15);color:var(--warn)}
.t-danger{background:rgba(248,81,73,.15);color:var(--danger)}
.t-info{background:rgba(79,156,249,.15);color:var(--accent)}
.t-muted{background:rgba(154,167,180,.13);color:var(--muted)}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{background:var(--card2);border:1px solid var(--line);border-radius:8px;padding:6px 11px;font-size:12.5px;font-family:ui-monospace,Consolas,monospace}
.chip.danger{border-color:rgba(248,81,73,.4)}
.grp{margin-bottom:18px}.grp h3{font-size:13px;color:var(--muted);margin:0 0 9px;text-transform:uppercase;letter-spacing:.5px}
.cols{columns:2;column-gap:28px}.cols .chip{display:inline-block;width:100%;margin-bottom:8px;break-inside:avoid}
.note{background:var(--card2);border-left:3px solid var(--accent);border-radius:6px;padding:12px 14px;font-size:13px;color:var(--muted);margin-top:14px}
footer{color:var(--muted);font-size:12px;text-align:center;margin-top:40px}
@media(max-width:640px){.cols{columns:1}}
"""


def _flag_tag(val, true_is_good):
    if val is None:
        return '<span class="tag t-muted">not set</span>'
    good = (val == "false") if true_is_good == "false_good" else (val == "true")
    cls = "t-ok" if good else "t-warn"
    return '<span class="tag %s">%s</span>' % (cls, html.escape(val))


def render_html(d):
    # stat cards
    stats = [
        ("Version", d["versionName"]),
        ("Version Code", d["versionCode"]),
        ("Min Android", "SDK %s" % d["minSdk"]),
        ("Target Android", "SDK %s" % d["targetSdk"]),
    ]
    stat_html = "".join(
        '<div class="stat"><div class="k">%s</div><div class="v">%s</div></div>'
        % (html.escape(k), html.escape(str(v))) for k, v in stats)

    # overview rows
    ov = [("Application class", '<span class="mono">%s</span>' % html.escape(short_name(d["appName"])))]
    if d["compileSdk"] not in (None, "?"):
        ov.append(("Compiled with", "SDK %s" % html.escape(str(d["compileSdk"]))))
    if d["buildSig"]:
        ov.append(("Build signature", '<span class="mono">%s</span>' % html.escape(d["buildSig"])))
    if d["env"]:
        ov.append(("Environment", '<span class="mono">%s</span>' % html.escape(d["env"])))
    ov.append(("Backup allowed", _flag_tag(d["allowBackup"], "false_good")))
    ov.append(("Cleartext traffic", _flag_tag(d["cleartext"], "false_good")))
    ov.append(("RTL support", _flag_tag(d["rtl"], "true_good")))
    ov_html = "".join(
        '<tr><td style="width:230px;color:var(--muted)">%s</td><td>%s</td></tr>' % (k, v)
        for k, v in ov)

    # permission chip: short, ellipsized label; full name in a hover tooltip
    def perm_chip(p, extra=""):
        label = ellipsize(short_name(p))
        return ('<span class="chip%s" title="%s">%s</span>'
                % (extra, html.escape(p), html.escape(label)))

    high_html = "".join(perm_chip(p, " danger") for p in d["perm_high"]) \
        or '<span class="hint">None detected.</span>'
    other_html = "".join(perm_chip(p) for p in d["perm_other"])

    # custom permissions
    cperm_html = "".join(
        '<tr><td class="mono" title="%s">%s</td><td><span class="tag %s">%s</span></td></tr>'
        % (html.escape(n), html.escape(ellipsize(short_name(n))), cls, html.escape(lbl))
        for n, lbl, cls in d["custom_perms"]) or '<tr><td colspan="2" class="hint">None.</td></tr>'

    # exported components
    def guard_tag(c):
        if c["perm"]:
            return '<span class="tag t-ok">%s</span>' % html.escape(short_name(c["perm"]))
        if c["has_intent"]:
            return '<span class="tag t-warn">none (intent-filter)</span>'
        return '<span class="tag t-muted">none</span>'

    def comp_badges(c):
        b = ""
        if c["enabled"] == "false":
            b += ' <span class="tag t-muted">disabled</span>'
        if c.get("implicit"):
            b += ' <span class="tag t-warn">implicit</span>'
        return b
    exp_rows = "".join(
        '<tr><td class="mono">%s%s</td><td>%s</td><td>%s</td></tr>'
        % (html.escape(short_name(c["name"])), comp_badges(c),
           html.escape(c["kind"]), guard_tag(c))
        for c in d["exported"]) or '<tr><td colspan="3" class="hint">None exported.</td></tr>'

    # providers
    def pv_guard(pv):
        if pv["perm"]:
            return html.escape(short_name(pv["perm"]))
        if pv["grant"] == "true":
            return "grantUriPermissions"
        return '<span class="tag t-muted">none</span>'
    pv_rows = "".join(
        '<tr><td class="mono">%s</td><td>%s</td><td>%s</td></tr>'
        % (html.escape(pv["authorities"] or short_name(pv["name"])),
           ('<span class="tag t-warn">Yes</span>' if pv["exported"] == "true"
            else '<span class="tag t-ok">No</span>'),
           pv_guard(pv))
        for pv in d["providers"]) or '<tr><td colspan="3" class="hint">None.</td></tr>'

    # app display name + monogram initial for the generic "app" tile
    display = short_name(d["appName"]) if d["appName"] != "?" else d["package"]
    initial = next((ch for ch in display if ch.isalnum()), "?").upper()

    return """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{pkg} - Manifest Report</title><style>{css}</style></head><body><div class="wrap">
<header><div class="logo">{initial}</div><div>
<h1>{app}</h1><div class="sub"><span class="pkg">{pkg}</span></div></div></header>

<div class="grid">{stats}</div>

<section><h2>&#128203; Overview</h2><table>{overview}</table></section>

<section><h2>&#128273; Permissions</h2>
<p class="hint">{perm_count} permissions requested. Red = high-privilege / system-only.</p>
<div class="grp"><h3>High privilege</h3><div class="cols">{high}</div></div>
<div class="grp" style="margin-bottom:0"><h3>Other</h3><div class="chips">{other}</div></div></section>

<section><h2>&#128221; Custom Permissions Defined</h2>
<table><thead><tr><th>Permission</th><th>Protection level</th></tr></thead><tbody>{cperms}</tbody></table></section>

<section><h2>&#128682; Exported Components (attack surface)</h2>
<p class="hint">Components reachable by other apps, and what guards each.</p>
<table><thead><tr><th>Component</th><th>Type</th><th>Guard</th></tr></thead><tbody>{exported}</tbody></table></section>

<section><h2>&#128450; Content Provider Authorities</h2>
<table><thead><tr><th>Authority</th><th>Exported</th><th>Guard</th></tr></thead><tbody>{providers}</tbody></table></section>

<footer>Generated by manifest_gui.py v{tool_ver} &middot; {pkg} {ver} &middot; Resource references (@0x...) not resolved.</footer>
</div></body></html>""".format(
        css=CSS, app=html.escape(display), initial=html.escape(initial),
        tool_ver=__version__,
        pkg=html.escape(d["package"]), ver=html.escape(d["versionName"]),
        stats=stat_html, overview=ov_html, perm_count=d["perm_count"],
        high=high_html, other=other_html, cperms=cperm_html,
        exported=exp_rows, providers=pv_rows)


# ===========================================================================
# 4. generate()  --  decode + parse + render
# ===========================================================================
def generate(manifest_path, out_html=None):
    """Decode a manifest and write the HTML report + decoded XML.

    manifest_path : path to AndroidManifest.xml, or an extracted APK directory.
    out_html      : where to write the report (default: <manifest_dir>/manifest_report.html).

    Returns a dict with the parsed data plus 'out_html' and 'out_xml' paths.
    """
    inp = manifest_path
    if os.path.isdir(inp):
        inp = os.path.join(inp, "AndroidManifest.xml")
    if not os.path.isfile(inp):
        raise FileNotFoundError("Manifest not found: %s" % inp)

    base = os.path.dirname(os.path.abspath(inp))
    out_html = out_html or os.path.join(base, "manifest_report.html")
    # decoded XML goes next to the report, not next to the input manifest
    out_xml = os.path.join(os.path.dirname(os.path.abspath(out_html)),
                           "AndroidManifest_decoded.xml")

    with open(inp, "rb") as f:
        head = f.read(4)
    if head[:2] == b"\x03\x00":
        xml_text = decode_axml(inp)
    else:
        with open(inp, encoding="utf-8") as f:
            xml_text = f.read()

    with open(out_xml, "w", encoding="utf-8", newline="\n") as f:
        f.write(xml_text)

    data = parse_manifest(xml_text)
    with open(out_html, "w", encoding="utf-8", newline="\n") as f:
        f.write(render_html(data))

    data["out_html"] = out_html
    data["out_xml"] = out_xml
    return data


# ===========================================================================
# 5. Tkinter GUI
# ===========================================================================
PAD = 8


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AndroidManifest Report Generator  v%s" % __version__)
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
