"""Mac-side check that chrome://credits can list components/camoucfg_lgpl.

Fetches the pristine tools/licenses/licenses.py at CHROMIUM_REV (cached under
the temp dir; skips when offline), imports it with its heavy imports stubbed,
and runs FindThirdPartyDirs + ParseDir over a temp tree holding only our
README.chromium and license files.

  RED:   pristine licenses.py does not list the dir (it is not under
         third_party/ and not in ADDITIONAL_PATHS).
  GREEN: with the one-line ADDITIONAL_PATHS edit (the box applies the same edit
         as a patch commit) it lists the dir and ParseDir returns our entry.
"""
import base64
import importlib.util
import os
import pathlib
import shutil
import sys
import tempfile
import types
import unittest
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIR = "components/camoucfg_lgpl"
ANCHOR = "ADDITIONAL_PATHS = (\n"
EDIT = ANCHOR + "  os.path.join('components', 'camoucfg_lgpl'),\n"


def pin():
    for line in (ROOT / "upstream.env").read_text().splitlines():
        if line.startswith("CHROMIUM_REV="):
            return line.split("=", 1)[1]


def _ctx():
    import ssl
    cafile = "/etc/ssl/cert.pem"  # macOS python often lacks its own CA bundle
    return ssl.create_default_context(cafile=cafile if os.path.exists(cafile) else None)


def pristine():
    if os.environ.get("LICENSES_PY"):  # a pre-downloaded pristine file
        return pathlib.Path(os.environ["LICENSES_PY"]).read_text()
    cache = pathlib.Path(tempfile.gettempdir()) / ("licenses-%s.py" % pin())
    if not cache.exists():
        url = ("https://chromium.googlesource.com/chromium/src/+/%s/tools/licenses/licenses.py"
               "?format=TEXT" % pin())
        try:
            cache.write_bytes(base64.b64decode(urllib.request.urlopen(url, timeout=60, context=_ctx()).read()))
        except OSError as e:
            raise unittest.SkipTest("offline: %s" % e)
    return cache.read_text()


def load(source, tmp):
    """licenses.py from `source`, its repo-only imports stubbed."""
    for name in ("spdx_writer", "action_helpers", "find_depot_tools",
                 "metadata", "metadata.fields", "metadata.fields.custom",
                 "metadata.fields.custom.license_allowlist"):
        m = types.ModuleType(name)
        m.SpdxWriter = object
        m.add_depot_tools_to_path = lambda: None
        sys.modules[name] = m
    path = tmp / "tools" / "licenses" / "licenses.py"
    path.parent.mkdir(parents=True)
    path.write_text(source)
    spec = importlib.util.spec_from_file_location("licenses_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CreditsEntry(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src = pristine()
        assert ANCHOR in self.src
        tree = self.tmp / "root"
        (tree / DIR).mkdir(parents=True)
        for n in ("README.chromium", "LICENSE", "COPYING"):
            shutil.copy(ROOT / "additions/camoucfg_lgpl" / n, tree / DIR / n)
        self.tree = str(tree)

    def test_red_pristine_does_not_list_it(self):
        mod = load(self.src, self.tmp / "a")
        self.assertNotIn(DIR, mod.FindThirdPartyDirs(self.tree))

    def test_green_patched_lists_and_parses_it(self):
        mod = load(self.src.replace(ANCHOR, EDIT, 1), self.tmp / "b")
        self.assertIn(DIR, mod.FindThirdPartyDirs(self.tree))
        metas, errors = mod.ParseDir(DIR, self.tree, require_license_file=True,
                                     optional_keys=mod.OPTIONAL_FIELDS)
        self.assertEqual(errors, [])
        self.assertEqual(len(metas), 1)
        m = metas[0]
        self.assertEqual((m["Name"], m["Shipped"]), ("Cursory", "yes"))
        self.assertEqual(m["License File"], [DIR + "/LICENSE", DIR + "/COPYING"])
        self.assertIn("GNU LESSER GENERAL PUBLIC LICENSE",
                      (pathlib.Path(self.tree) / m["License File"][0]).read_text())


if __name__ == "__main__":
    unittest.main()
