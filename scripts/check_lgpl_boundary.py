"""LGPL include boundary: additions/camoucfg_lgpl/ is reachable only through cursory.h,
and only from additions/camoucfg/mouse_trajectories.cc. The LGPL dir must not include
components/camoucfg/, and must carry LICENSE and NOTICE.

Run: python3 scripts/check_lgpl_boundary.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LGPL = "additions/camoucfg_lgpl"
ALLOWED = ("additions/camoucfg/mouse_trajectories.cc", "cursory.h")
INCLUDE = re.compile(r'#include\s+"components/(camoucfg_lgpl|camoucfg)/([^"]+)"')


def violations(root: pathlib.Path) -> list[str]:
    out = []
    for lic in ("LICENSE", "NOTICE"):
        if not (root / LGPL / lic).is_file():
            out.append(f"{LGPL}/{lic}: missing")
    for top in ("additions", "patches"):
        for p in sorted((root / top).rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(root).as_posix()
            try:
                lines = p.read_text(errors="replace").splitlines()
            except OSError:
                continue
            inside = rel.startswith(LGPL + "/")
            for n, line in enumerate(lines, 1):
                m = INCLUDE.search(line)
                if not m:
                    continue
                if inside and m.group(1) == "camoucfg":
                    out.append(f"{rel}:{n}: LGPL code must not include components/camoucfg/")
                elif not inside and m.group(1) == "camoucfg_lgpl" and (rel, m.group(2)) != ALLOWED:
                    out.append(f"{rel}:{n}: only cursory.h from mouse_trajectories.cc may include camoucfg_lgpl")
    return out


if __name__ == "__main__":
    v = violations(ROOT)
    print("\n".join(v))
    sys.exit(1 if v else 0)
