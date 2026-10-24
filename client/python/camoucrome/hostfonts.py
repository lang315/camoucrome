"""The host's real font families, read from the Windows registry (step 6: the fork may hide a font, never add one)."""
import re
import sys

_KEYS = (("HKEY_LOCAL_MACHINE", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
         ("HKEY_CURRENT_USER", r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"))


def parse_registry_names(names):
    """Registry value names ("Cambria & Cambria Math (TrueType)") -> family set."""
    out = set()
    for n in names:
        for part in re.sub(r"\s*\((?:TrueType|OpenType)\)\s*$", "", n).split("&"):
            if part.strip():
                out.add(part.strip())
    return out


def host_families_from_labels(labels, fam):
    """Registry labels (face names such as "Yu Gothic Regular", or family names) -> the captured
    families they stand for, via the captured faces' full names (field 1 -> field 2). Case-folded
    both sides, as the C++ gate is. A label with no captured face or family is dropped, never guessed.
    Bahnschrift registers once but its named instances are captured as families of their own."""
    by_label = {f[1].casefold(): f[2] for f in fam.get("faces", [])}
    by_family = {f.casefold(): f for f in fam["list"]}
    out = set()
    for label in labels:
        key = label.casefold()
        if key in by_family:
            out.add(by_family[key])
        if key in by_label:
            out.add(by_label[key])
        if key == "bahnschrift":
            out |= {f for f in fam["list"] if f.startswith("Bahnschrift")}
    return out


def families():
    """Registry labels installed on this host (machine and user keys), unmapped; None off Windows
    or when nothing could be read. fonts_keys maps them with host_families_from_labels."""
    if sys.platform != "win32":
        return None
    import winreg  # noqa: PLC0415 -- Windows only
    names = []
    for hive, path in _KEYS:
        try:
            with winreg.OpenKey(getattr(winreg, hive), path) as k:
                names += [winreg.EnumValue(k, i)[0] for i in range(winreg.QueryInfoKey(k)[1])]
        except OSError:
            pass  # no per-user key
    return parse_registry_names(names) or None
