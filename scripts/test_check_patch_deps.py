import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import check_patch_deps as c

# Raising this needs the owner: every exception is a known-illegal include.
MAX_EXCEPTIONS = 1

PATCH = """diff --git a/a/b/x.cc b/a/b/x.cc
--- a/a/b/x.cc
+++ b/a/b/x.cc
@@ -1 +1 @@
diff --git a/a/b/c/new.cc b/a/b/c/new.cc
--- /dev/null
+++ b/a/b/c/new.cc
@@ -0,0 +1 @@
diff --git a/d/gone.cc b/d/gone.cc
--- a/d/gone.cc
+++ /dev/null
@@ -1 +0,0 @@
diff --git a/top.gn b/top.gn
--- a/top.gn
+++ b/top.gn
"""

OUT = """/x/y.py:1: SyntaxWarning: invalid escape sequence '\\d'
ERROR in /src/third_party/blink/renderer/modules/font_access/font_access.cc
  Illegal include: "base/strings/string_split.h"
    Because of "-base" from third_party's include_rules.
  Illegal include: "base/foo.h"
    Because of "-base" from third_party's include_rules.
ERROR in /src/a/b.cc
  Illegal include: "q/r.h"
    Because of x.
FAILED
"""
FA = "third_party/blink/renderer/modules/font_access/font_access.cc"
EXC = [{"file": FA, "include": "base/strings/string_split.h",
        "issue": "#45", "why": "w"}]


def test_dirs_from_patch():
    assert c.dirs_from_patch(PATCH) == {"a/b", "a/b/c"}


def test_minimal_set():
    assert c.minimal({"a/b", "a/b/c", "d", "a/bc"}) == ["a/b", "a/bc", "d"]


def test_parse():
    assert c.parse(OUT, "/src") == [(FA, "base/strings/string_split.h"),
                                    (FA, "base/foo.h"), ("a/b.cc", "q/r.h")]


def fake(out, rc=1):
    return lambda d, src: (rc, out)


def test_excepted_ok(capsys):
    out = OUT.replace("base/foo.h", "base/strings/string_split.h")
    out = out.split("ERROR in /src/a/b.cc")[0]
    assert c.run_all(["x"], "/src", EXC, fake(out)) == 0
    assert "EXCEPTION issue #45 " + FA in capsys.readouterr().out


def test_unmatched_fails(capsys):
    assert c.run_all(["x"], "/src", EXC, fake(OUT)) == 1
    assert "FAIL a/b.cc: illegal include q/r.h" in capsys.readouterr().out


def test_stale_fails(capsys):
    assert c.run_all(["x"], "/src", EXC, fake("SUCCESS", 0)) == 1
    assert "STALE exception (remove it)" in capsys.readouterr().out


def test_unparsable_failure_fails():
    assert c.run_all(["x"], "/src", [], fake("boom", 2)) == 1


def test_clean_ok(capsys):
    assert c.run_all(["x"], "/src", [], fake("SUCCESS", 0)) == 0
    assert "check_patch_deps: 1 directories, 0 violations (0 excepted)" in capsys.readouterr().out


def test_exceptions_file():
    e = json.loads(c.EXC_FILE.read_text())
    assert len(e) <= MAX_EXCEPTIONS
    for x in e:
        assert all(x.get(k) for k in ("file", "include", "issue", "why"))
        assert c.re.fullmatch(r"#\d+", x["issue"])


def test_build_files_do_not_widen_the_directory_set():
    # checkdeps reads includes of source files. A BUILD.gn or DEPS hunk in components/ or
    # third_party/blink/renderer/ would otherwise pull in a whole subtree.
    text = ("+++ b/components/BUILD.gn\n+++ b/third_party/blink/renderer/DEPS\n"
            "+++ b/third_party/blink/renderer/x/y.gni\n+++ b/third_party/blink/renderer/modules/font_access/font_access.cc\n"
            "+++ b/chrome/browser/foo.mm\n+++ b/net/bar.h\n")
    assert c.dirs_from_patch(text) == {"third_party/blink/renderer/modules/font_access", "chrome/browser", "net"}
