"""Every additions/<dir> must be handled by the four scripts that move it.

apply.sh, rebuild_branch.sh, check_checkout_sync.sh and export.sh each
hard-wire the directory names under additions/. A new directory that one of
them forgets is silently not copied, not checked, or not exported back.

Run: python3 scripts/test_additions_mapping.py
"""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ["apply.sh", "rebuild_branch.sh", "check_checkout_sync.sh", "export.sh"]
DIRS = sorted(p.name for p in (ROOT / "additions").iterdir() if p.is_dir())


class AdditionsMapping(unittest.TestCase):
    def test_every_dir_mapped(self):
        self.assertTrue(DIRS, "no directories under additions/")
        for d in DIRS:
            for s in SCRIPTS:
                with self.subTest(dir=d, script=s):
                    text = (ROOT / "scripts" / s).read_text()
                    # (?!\w): camoucfg must not satisfy camoucfg_lgpl.
                    needle = re.escape(f"components/{d}") + r"(?!\w)"
                    self.assertRegex(text, needle)


if __name__ == "__main__":
    unittest.main()
