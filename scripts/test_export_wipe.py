"""export.sh must not empty additions/camoucfg_lgpl when the branch lacks it.

Runs scripts/export.sh against a throwaway Chromium-like git repo whose branch
has components/camoucfg but not components/camoucfg_lgpl. The fixed script
exits non-zero and keeps the sentinel; the script as of 5974403 (the commit
before the fix) wipes it. The second case proves the first can fail.

Run: python3 scripts/test_export_wipe.py
"""

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
OLD_REV = "5974403"
ENV = {
    **os.environ, "TZ": "UTC", "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull, "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def run(cmd, cwd, **kw):
    return subprocess.run(cmd, cwd=cwd, env=ENV, text=True,
                          capture_output=True, **kw)


class ExportWipe(unittest.TestCase):
    script_text = (REPO / "scripts" / "export.sh").read_text()
    sentinel_survives = True

    def test_branch_without_lgpl_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            src, root = tmp / "src", tmp / "root"
            src.mkdir()
            run(["git", "init", "-q"], src)
            (src / "base.txt").write_text("base\n")
            run(["git", "add", "-A"], src)
            run(["git", "commit", "-q", "-m", "base"], src)
            rev = run(["git", "rev-parse", "HEAD"], src).stdout.strip()
            run(["git", "checkout", "-q", "-b", "camoucrome/main"], src)
            (src / "components/camoucfg").mkdir(parents=True)
            (src / "components/camoucfg/invariants.json").write_text("{}\n")
            (src / "base.txt").write_text("changed\n")
            run(["git", "add", "-A"], src)
            run(["git", "commit", "-q", "-m", "sp0-test"], src)

            (root / "scripts").mkdir(parents=True)
            (root / "scripts/export.sh").write_text(self.script_text)
            (root / "upstream.env").write_text(f"CHROMIUM_REV={rev}\n")
            for d in ("patches", "settings", "additions/camoucfg"):
                (root / d).mkdir(parents=True)
            sentinel = root / "additions/camoucfg_lgpl/sentinel"
            sentinel.parent.mkdir()
            sentinel.write_text("keep\n")

            r = run(["bash", str(root / "scripts/export.sh"), str(src)], root)
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(sentinel.exists(), self.sentinel_survives,
                             r.stdout + r.stderr)


class OldExportWipes(ExportWipe):
    """The pre-fix script loses the sentinel: the test above can fail."""
    sentinel_survives = False
    script_text = run(["git", "show", f"{OLD_REV}:scripts/export.sh"],
                      REPO).stdout


if __name__ == "__main__":
    if not shutil.which("bash"):
        raise SystemExit("bash required")
    unittest.main()
