"""export.sh and the camoucfg_lgpl directory.

Runs scripts/export.sh against a throwaway Chromium-like git repo.
  - branch without components/camoucfg_lgpl: exit 0, additions/camoucfg_lgpl kept
  - branch with it: additions/camoucfg_lgpl replaced by the branch's content
  - OLD_BLOCK (the pre-fix wipe-then-archive, inlined so no commit is needed)
    swapped in for the guarded block loses the sentinel: the first case can fail.

Run: python3 scripts/test_export_wipe.py
"""

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
OLD_BLOCK = """rm -rf "$ROOT/additions/camoucfg_lgpl"
mkdir -p "$ROOT/additions/camoucfg_lgpl"
git -C "$SRC" archive "$BRANCH" components/camoucfg_lgpl | tar -x -C "$ROOT/additions" --strip-components=1
"""
ENV = {
    **{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    "TZ": "UTC", "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull, "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def run(cmd, cwd, **kw):
    return subprocess.run(cmd, cwd=cwd, env=ENV, text=True,
                          capture_output=True, **kw)


def current_script():
    return (REPO / "scripts" / "export.sh").read_text()


def old_script():
    s = current_script()
    i = s.index("# A branch without the dir")
    j = s.index("\nfi\n", i) + len("\nfi\n")
    return s[:i] + OLD_BLOCK + s[j:]


class ExportLgpl:
    script_text = None
    with_lgpl = False
    expect_rc0 = True
    sentinel_survives = True

    def test_export(self):
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
            if self.with_lgpl:
                (src / "components/camoucfg_lgpl/data").mkdir(parents=True)
                (src / "components/camoucfg_lgpl/new.txt").write_text("new\n")
                (src / "components/camoucfg_lgpl/data/d.txt").write_text("d\n")
            (src / "base.txt").write_text("changed\n")
            run(["git", "add", "-A"], src)
            run(["git", "commit", "-q", "-m", "sp0-test"], src)

            (root / "scripts").mkdir(parents=True)
            (root / "scripts/export.sh").write_text(self.script_text or current_script())
            (root / "upstream.env").write_text(f"CHROMIUM_REV={rev}\n")
            for d in ("patches", "settings", "additions/camoucfg"):
                (root / d).mkdir(parents=True)
            sentinel = root / "additions/camoucfg_lgpl/sentinel"
            sentinel.parent.mkdir()
            sentinel.write_text("keep\n")

            r = run(["bash", str(root / "scripts/export.sh"), str(src)], root)
            out = r.stdout + r.stderr
            self.assertEqual(r.returncode == 0, self.expect_rc0, out)
            self.assertEqual(sentinel.exists(), self.sentinel_survives, out)
            if self.with_lgpl:
                lg = root / "additions/camoucfg_lgpl"
                self.assertEqual((lg / "new.txt").read_text(), "new\n")
                self.assertEqual((lg / "data/d.txt").read_text(), "d\n")


class BranchWithoutLgpl(ExportLgpl, unittest.TestCase):
    pass


class BranchWithLgpl(ExportLgpl, unittest.TestCase):
    with_lgpl = True
    sentinel_survives = False  # stale file removed


class OldBlockWipes(ExportLgpl, unittest.TestCase):
    """The pre-fix block fails and loses the sentinel: BranchWithoutLgpl can fail."""
    script_text = None
    expect_rc0 = False
    sentinel_survives = False

    def setUp(self):
        self.script_text = old_script()


if __name__ == "__main__":
    if not shutil.which("bash"):
        raise SystemExit("bash required")
    unittest.main()
