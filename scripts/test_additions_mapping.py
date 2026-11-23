"""Every additions/<dir> must be in scripts/additions_map.txt, and the four
scripts that move it must read that map instead of hard-wiring directory names.

A new directory missing from the map is silently not copied, not checked and not
exported back; a script that hard-wires a name again is how that map drifted.

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
        pairs = dict(l.split() for l in (ROOT / "scripts" / "additions_map.txt").read_text().splitlines()
                     if l.strip() and not l.startswith("#"))
        for d in DIRS:
            with self.subTest(dir=d):
                self.assertEqual(pairs.get(f"additions/{d}"), f"components/{d}")

    def test_scripts_read_the_map(self):
        for s in SCRIPTS:
            with self.subTest(script=s):
                text = (ROOT / "scripts" / s).read_text()
                self.assertIn("lib_additions.sh", text)
                code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
                # The registry's own path is the one deliberate layout difference (apply.sh).
                code = code.replace("components/camoucfg/invariants.json", "")
                self.assertNotRegex(code, r"components/camoucfg")


if __name__ == "__main__":
    unittest.main()
