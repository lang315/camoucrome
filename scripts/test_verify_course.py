"""verify_course's vendored-CreepJS lock and K1-K5 checks, without a browser."""
import os
import pathlib
import re
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("CAMOU_CLIENT", str(HERE.parent))
import verify_course  # noqa: E402


def test_vendor_intact():
    assert verify_course.check_vendor(verify_course.CREEP_DIR) == []


def test_vendor_detects_edit(tmp_path):
    d = tmp_path / "creepjs"
    shutil.copytree(verify_course.CREEP_DIR, d)
    with open(d / "creep.js", "ab") as f:
        f.write(b"x")
    bad = verify_course.check_vendor(d)
    assert len(bad) == 1 and "creep.js" in bad[0]


K1_OK = {"nav": [], "scr": [], "uad": [], "navP": True, "scrP": True, "uadP": True}


def test_k1():
    assert verify_course.k1_problems({"k1": K1_OK}) == []
    p = verify_course.k1_problems({"k1": {**K1_OK, "nav": ["deviceMemory"]}})
    assert len(p) == 1 and "deviceMemory" in p[0] and p[0].startswith("k1 nav own")
    assert verify_course.k1_problems({"k1": {**K1_OK, "navP": False}}) == ["k1 navP"]


def test_k2():
    ok = {"visited": 10076, "anomalies": []}
    assert verify_course.k2_problems({"k2": ok}, 5000) == []
    assert verify_course.k2_problems({"k2": {"visited": 0, "anomalies": []}}, 5000) == ["k2 visited 0 < floor 5000"]
    a = [["tostring", "Navigator.prototype.get hardwareConcurrency"]]
    assert verify_course.k2_problems({"k2": {"visited": 10076, "anomalies": a}}, 5000) == [
        "k2 tostring Navigator.prototype.get hardwareConcurrency"]


def test_k3():
    stock = {"threshold": -24, "knee": 30, "ratio": 12, "attack": 0.003000000026077032, "release": 0.25, "reduction": 0}
    assert verify_course.k3_problems({"k3": {"rt": stock, "off": dict(stock)}}) == []
    p = verify_course.k3_problems({"k3": {"rt": {**stock, "threshold": -23}, "off": dict(stock)}})
    assert p == ["k3 rt.threshold -23 != -24"]


def _r(v, **x):
    return {"k4": {"nav": {"hardwareConcurrency": v, **x}}}


def test_k4():
    assert verify_course.k4_problems([_r(8), _r(8), _r(8)], {}) == []
    assert verify_course.k4_problems([_r(8), _r(3), _r(5)], {}) == ["k4 nav.hardwareConcurrency [8, 3, 5]"]
    # a leaf absent from one report is reported, not a KeyError
    assert verify_course.k4_problems([_r(8), _r(8, extra=1), _r(8)], {}) == ["k4 nav.extra [None, 1, None]"]
    assert verify_course.k4_problems([_r(8), _r(3), _r(5)], {"nav.hardwareConcurrency": "why"}) == []


def test_k5():
    assert verify_course.k5_problems({"k5": "157.0.8103.51"}, "157.0.8103.51") == []
    assert verify_course.k5_problems({"k5": "157.0.8103.39"}, "157.0.8103.51") == [
        "k5 uaFullVersion 157.0.8103.39 != 157.0.8103.51"]


def test_r_row_ok():
    assert verify_course.r_row_ok(["k3 rt.threshold -23 != -24"], "k3 rt.threshold")
    assert not verify_course.r_row_ok(["k3 attack 1 != 0.003"], "threshold")
    assert not verify_course.r_row_ok([], "x")


def test_page_defines_no_global():
    body = verify_course.PAGE[verify_course.PAGE.index("<script>") + 8:].lstrip()
    assert re.match(r"\(\s*(async\s*)?(\(\)\s*=>|function)", body)


def test_creep_server_serves_vendor_and_harness():
    html, ct = verify_course.creep_response("index.html")
    wrap = b"<script>" + verify_course.HARNESS.encode() + b"</script>"
    assert ct.startswith("text/html") and html.count(wrap) == 1 and html.index(wrap) < html.rindex(b"</body>")
    assert html.replace(wrap, b"") == (verify_course.CREEP_DIR / "index.html").read_bytes()
    js, ct = verify_course.creep_response("creep.js")
    assert js == (verify_course.CREEP_DIR / "creep.js").read_bytes() and "javascript" in ct
    assert verify_course.creep_response("") [1].startswith("text/html")
    assert verify_course.creep_response("../verify_course.py") is None


K6_OK = {"lies": {"Navigator.userAgent": ["x"]}, "trash": ["a"], "stealth": [], "workerLied": False, "done": True}


def test_k6():
    assert verify_course.k6_problems(K6_OK, dict(K6_OK)) == []
    ident = {**K6_OK, "lies": {**K6_OK["lies"], "Navigator.hardwareConcurrency": ["lie"]}}
    p = verify_course.k6_problems(K6_OK, ident)
    assert len(p) == 1 and p[0].startswith("k6 lie Navigator.hardwareConcurrency") and "lie" in p[0]
    assert verify_course.k6_problems(K6_OK, {**K6_OK, "trash": ["a", "b"]}) == ["k6 trash b"]
    assert verify_course.k6_problems(K6_OK, {**K6_OK, "stealth": ["hasIframeProxy"]}) == ["k6 stealth hasIframeProxy"]
    assert verify_course.k6_problems(K6_OK, {**K6_OK, "workerLied": True}) == ["k6 worker lied"]
    err = {"error": "timeout"}
    assert verify_course.k6_problems(K6_OK, err) == ["k6 error ident timeout"]
    assert verify_course.k6_problems(err, K6_OK) == ["k6 error base timeout"]
    assert len(verify_course.k6_problems(err, err)) == 2


def test_k6_missing_sections():
    empty = {"missing": ["lies", "trash", "headless", "workerScope"], "lies": {}, "trash": [], "stealth": [],
             "workerLied": False, "done": True}
    p = verify_course.k6_problems(K6_OK, empty)
    assert len(p) == 4 and all("missing" in x and "ident" in x for x in p)
    assert p[0] == "k6 error ident missing lies"
    assert all("base" in x for x in verify_course.k6_problems(empty, K6_OK))
    assert verify_course.k6_problems(K6_OK, {**K6_OK, "missing": []}) == []


def test_k6_note():
    assert verify_course.k6_note("base", {**K6_OK, "lies": {"B": 1, "A": 2}, "trash": ["x", "y"]}) == "note: K6 base lies=2 ['A', 'B'] trash=['x', 'y']"
    assert verify_course.k6_note("ident", {"error": "timeout"}) == "note: K6 ident error timeout"


def test_r6_strict():
    exp = verify_course.MUTANTS["R6"][1]
    assert exp == "k6 lie Navigator.hardwareConcurrency"
    assert not verify_course.r_row_ok(["k6 lie Navigator.deviceMemory [...]"], exp)
    assert verify_course.r_row_pass(["k6 lie Navigator.hardwareConcurrency []"], exp, True, True)
    assert not verify_course.r_row_pass(["k6 lie Navigator.hardwareConcurrency []"], exp, True, False)
    assert not verify_course.r_row_pass(["k6 lie Navigator.hardwareConcurrency []"], exp, False, True)
