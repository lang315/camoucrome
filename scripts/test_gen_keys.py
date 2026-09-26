"""gen_keys.py --check's literal-key scan: the call shapes it must see."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gen_keys  # noqa: E402


def hits(text, patch=False):
    return gen_keys.literal_key_lines(text.splitlines(keepends=True), patch)


def test_flat_call():
    assert hits('camoucfg::GetString(scope, "a.b");\n') == [1]


def test_nested_scope_call():
    assert hits('camoucfg::GetString(camoucfg::ScopeFor(ctx), "a.b");\n') == [1]


def test_multiline_call():
    assert hits('x = camoucfg::GetBool(camoucfg::ScopeFor(nullptr),\n    "a.b");\n') == [1]


def test_multiline_call_in_patch():
    patch = ('+  x = camoucfg::GetDouble(camoucfg::ScopeFor(ctx),\n'
             '+                          "a.b");\n')
    assert hits(patch, patch=True) == [1]


def test_removed_lines_ignored():
    assert hits('-  camoucfg::GetString(camoucfg::ScopeFor(ctx), "a.b");\n', patch=True) == []


def test_constant_key_passes():
    assert hits('camoucfg::GetString(camoucfg::ScopeFor(ctx), keys::kFoo);\n'
                'camoucfg::HasKey(scope, keys::kBar);\n') == []


def test_literal_in_later_argument_passes():
    assert hits('camoucfg::GetString(scope, keys::kFoo, "fallback");\n') == []


P1 = """diff --git a/x.cc b/x.cc
--- a/x.cc
+++ b/x.cc
@@ -1 +1,3 @@
+  bool b = camoucfg::HasKey(
+      camoucfg::GlobalScope(), "a.b");
 int y;
"""


def series(tmp_path, *patches):
    for i, text in enumerate(patches):
        (tmp_path / f"p{i}.patch").write_text(text)
    (tmp_path / "series").write_text("".join(f"p{i}.patch\n" for i in range(len(patches))))
    return gen_keys.patch_literal_hits(str(tmp_path))


def test_a_literal_a_later_patch_removes_is_not_in_the_applied_tree(tmp_path):
    removes = P1.replace("@@ -1 +1,3 @@\n+", "@@ -1,3 +1 @@\n-").replace("\n+      ", "\n-      ")
    assert series(tmp_path, P1, removes) == []


def test_a_literal_that_survives_the_series_fails(tmp_path):
    assert series(tmp_path, P1) == [("p0.patch", 5)]
    other = P1.replace("x.cc", "z.cc").replace("@@ -1 +1,3 @@\n+", "@@ -1,3 +1 @@\n-").replace("\n+      ", "\n-      ")
    assert series(tmp_path, P1, other) == [("p0.patch", 5)]  # same text removed from another file
    half = P1.replace("@@ -1 +1,3 @@\n+", "@@ -1,2 +1,2 @@\n-").replace('\n+      camoucfg::GlobalScope(), "a.b");', "")
    assert series(tmp_path, P1, half) == [("p0.patch", 5)]  # only the first line of the call removed
