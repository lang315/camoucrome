"""Every additions/<dir> must be handled by the four scripts that move it.

apply.sh, rebuild_branch.sh, check_checkout_sync.sh and export.sh each
hard-wire the directory names under additions/. A new directory that one of
them forgets is silently not copied, not checked, or not exported back.

Run: python3 scripts/test_additions_mapping.py
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ["apply.sh", "rebuild_branch.sh", "check_checkout_sync.sh", "export.sh"]


def main():
    bad = 0
    for d in sorted(p.name for p in (ROOT / "additions").iterdir() if p.is_dir()):
        for s in SCRIPTS:
            # (?!\w): camoucfg must not satisfy camoucfg_lgpl.
            text = (ROOT / "scripts" / s).read_text()
            needle = f"components/{d}"
            ok = re.search(re.escape(needle) + r"(?!\w)", text)
            if not ok:
                print(f"FAIL  scripts/{s} never mentions {needle}")
                bad += 1
    if bad:
        return 1
    print("PASS  every additions/ dir is mapped in all four scripts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
