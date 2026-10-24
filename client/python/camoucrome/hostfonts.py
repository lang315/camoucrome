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


def families():
    """Families installed on this host (machine and user keys), or None off Windows."""
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
    return parse_registry_names(names)
