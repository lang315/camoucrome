#!/usr/bin/env python3
"""Captured, not authored: the family names a stock Windows 10 / macOS host
exposes. Windows: the box's host over ssh (PowerShell, InstalledFontCollection);
macOS: system_profiler on this Mac. Writes families.<os> in settings/fonts.json."""
import argparse
import datetime
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
ROOT = pathlib.Path(__file__).resolve().parent.parent
PATH = ROOT / "settings" / "fonts.json"


def winhost_families():
    import winhost
    out = winhost.powershell("Add-Type -AssemblyName System.Drawing; "
                             "(New-Object System.Drawing.Text.InstalledFontCollection).Families | ForEach-Object { $_.Name }")
    return sorted({l.strip() for l in out.splitlines() if l.strip()}), \
        "PowerShell System.Drawing.Text.InstalledFontCollection on the build box's Windows 10 host (ssh buildpc)"


def winhost_names():
    """Every font file on the host through fontnames.py pushed as text (no fontTools there)."""
    import winhost
    src = (pathlib.Path(__file__).resolve().parent / "fontnames.py").read_text()
    driver = src + """
import glob, json, os
res = {}
for f in glob.glob(r"C:\\Windows\\Fonts\\*.*"):
    if f.lower().endswith((".ttf", ".ttc", ".otf")):
        res[os.path.basename(f)] = faces_of_file(f)
print(json.dumps(res))
"""
    ps = "Set-Content -Path $env:TEMP\\camou_fontnames.py -Value @'\n" + driver + "\n'@\npython $env:TEMP\\camou_fontnames.py\nRemove-Item $env:TEMP\\camou_fontnames.py"
    out = winhost.powershell(ps, timeout=300)
    # the last line is the driver's JSON (fontnames.py's own __main__ prints {} first when run this way)
    return json.loads([l for l in out.splitlines() if l.startswith("{")][-1])


def winhost_versions():
    import winhost
    v = winhost.powershell("(Get-CimInstance Win32_OperatingSystem).Version").strip()
    # UA-CH platformVersion: Windows 10 reports "10.0.0"; Windows 11 (build >= 22000) 13.0.0+.
    return v, "10.0.0" if int(v.split(".")[2]) < 22000 else "15.0.0"


MAC_DIRS = ["/System/Library/Fonts", "/System/Library/Fonts/Supplemental", "/Library/Fonts",
            "/System/Library/PrivateFrameworks/FontServices.framework/Resources/Reserved"]


def mac_names():
    import glob
    import fontnames
    res = {}
    for d in MAC_DIRS:
        for f in glob.glob(d + "/*"):
            if f.lower().endswith((".ttf", ".ttc", ".otf")):
                res[pathlib.Path(f).name] = fontnames.faces_of_file(f)
    return res


def mac_versions():
    v = subprocess.run(["sw_vers", "-productVersion"], capture_output=True, text=True, check=True).stdout.strip()
    return v, v  # UA-CH platformVersion on macOS is the product version


def unique_names(files, families):
    """{full or PostScript name -> {family, style}} for faces of a captured family, minus names equal to the family."""
    out = {}
    for faces in files.values():
        for f in faces:
            if f["family"] in families:
                for n in (f["full"], f["ps"]):
                    if n and n != f["family"] and n not in out:
                        out[n] = {"family": f["family"], "style": f["style"]}
    return out


def mac_families():
    raw = subprocess.run(["system_profiler", "SPFontsDataType", "-json"], capture_output=True, text=True, check=True).stdout
    fams = set()
    for f in json.loads(raw)["SPFontsDataType"]:
        for t in f.get("typefaces", []):
            fams.add(t.get("family") or t["_name"])
    return sorted(f for f in fams if not f.startswith(".")), \
        "system_profiler SPFontsDataType -json on the Mac (dot-prefixed system-private families dropped)"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--where", choices=["winhost", "mac"], required=True)
    a = ap.parse_args()
    fams, how = winhost_families() if a.where == "winhost" else mac_families()
    d = json.loads(PATH.read_text())
    exclude = d["families"].get("exclude", {})  # vendor fonts of the capture host, named with a reason
    fams = [f for f in fams if f not in exclude]
    files = winhost_names() if a.where == "winhost" else mac_names()
    os_version, platform_version = winhost_versions() if a.where == "winhost" else mac_versions()
    names = unique_names(files, set(fams))
    d["families"]["Windows" if a.where == "winhost" else "macOS"] = {
        "captured": datetime.date.today().isoformat(),
        "how": how + "; families in families.exclude (vendor software on this host) dropped", "list": fams,
        "os_version": os_version, "platform_version": platform_version,
        "unique_names_how": f"full and PostScript names (name IDs 4/6, Windows platform, en-US) of the {sum(map(len, files.values()))} faces in {len(files)} font files on the same host, for the captured families",
        "unique_names": dict(sorted(names.items()))}
    PATH.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
    print(len(fams), "families,", len(names), "unique names,", os_version, "->", platform_version)


if __name__ == "__main__":
    main()
