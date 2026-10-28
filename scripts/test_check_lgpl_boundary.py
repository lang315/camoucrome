import pathlib, tempfile, unittest
import check_lgpl_boundary as c

def tree(files):
    d = pathlib.Path(tempfile.mkdtemp())
    for rel, text in files.items():
        p = d / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
    return d

GOOD = {
    "additions/camoucfg_lgpl/LICENSE": "LGPL",
    "additions/camoucfg_lgpl/NOTICE": "n",
    "additions/camoucfg/mouse_trajectories.cc": '#include "components/camoucfg_lgpl/cursory.h"\n',
    "patches/.keep": "",
}

class Boundary(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(c.violations(tree(GOOD)), [])

    def test_other_header_is_a_violation(self):
        f = dict(GOOD); f["additions/camoucfg/mouse_trajectories.cc"] += '#include "components/camoucfg_lgpl/cursory_data.h"\n'
        self.assertEqual(len(c.violations(tree(f))), 1)

    def test_other_includer_is_a_violation(self):
        f = dict(GOOD); f["patches/x.patch"] = '+#include "components/camoucfg_lgpl/cursory.h"\n'
        self.assertEqual(len(c.violations(tree(f))), 1)

    def test_missing_license_files(self):
        f = {k: v for k, v in GOOD.items() if not k.endswith("NOTICE")}
        self.assertEqual(len(c.violations(tree(f))), 1)

    def test_lgpl_dir_must_not_include_camoucfg(self):
        f = dict(GOOD); f["additions/camoucfg_lgpl/cursory.cc"] = '#include "components/camoucfg/keys.h"\n'
        self.assertEqual(len(c.violations(tree(f))), 1)

if __name__ == "__main__":
    unittest.main()
