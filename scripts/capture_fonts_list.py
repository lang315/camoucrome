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
    d["families"]["Windows" if a.where == "winhost" else "macOS"] = {
        "captured": datetime.date.today().isoformat(),
        "how": how + "; families in families.exclude (vendor software on this host) dropped", "list": fams}
    PATH.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
    print(len(fams), "families")


if __name__ == "__main__":
    main()
