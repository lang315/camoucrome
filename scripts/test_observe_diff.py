"""observe_diff.py on two hand-made arm dirs."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import observe_diff as od  # noqa: E402


def arm(tmp_path, name, endpoints, matches):
    p = tmp_path / name
    p.mkdir()
    ch = {"arm": name, "posts_captured": 0, "posts_missing": 0, "ws": {},
          "endpoints": {e: {"count": 1, "bytes": 1, "kinds": {"form": 1}, "initiators": {}, "fields": {f: {"count": 1, "classes": {"int": 1}} for f in fs}}
                        for e, fs in endpoints.items()}}
    (p / "channels.json").write_text(json.dumps(ch))
    (p / "matches.json").write_text(json.dumps([{"endpoint": e, "field": f, "surface": s, "encoding": "exact", "weak": False, "count": 1}
                                                for e, f, s in matches]))
    return p


def test_diff_names_what_only_one_arm_sent(tmp_path):
    a = arm(tmp_path, "1f", {"www.facebook.com/ajax/bz": ["q[].a", "q[].b"]}, [("www.facebook.com/ajax/bz", "q[].b", "timezone")])
    b = arm(tmp_path, "1c", {"www.facebook.com/ajax/bz": ["q[].a"], "www.facebook.com/ajax/qm/": []}, [])
    d = od.diff(a, b)
    assert d["endpoints"] == {"only_a": [], "only_b": ["www.facebook.com/ajax/qm/"]}
    assert d["fields"]["only_a"] == ["www.facebook.com/ajax/bz q[].b"]
    assert d["matches"]["only_a"] == ["www.facebook.com/ajax/bz q[].b timezone"]
    out = od.render(d, "fork", "stock")
    assert "only fork" in out and "q[].b" in out


def test_diff_parses_as_python_3_9():
    import ast
    ast.parse(pathlib.Path(od.__file__).read_text(encoding="utf-8"), feature_version=(3, 9))


def test_diff_never_prints_a_pop_style_host(tmp_path):
    host = "scontent.xyz9-1.fna.fbcdn.net"  # synthetic
    a = arm(tmp_path, "1d", {host + "/up": ["f"]}, [(host + "/up", "f", "timezone")])
    b = arm(tmp_path, "1s", {}, [])
    out = od.render(od.diff(a, b), "fork", "stock")
    assert "xyz9" not in out and "scontent.*.fbcdn.net/up" in out


def test_diff_bytes_per_kind_count_only_the_page_site(tmp_path):
    import test_observe_report as tr
    a = arm(tmp_path, "1d", {}, [])
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (a / "net.json").write_bytes(tr.site_netlog(scratch).read_bytes())
    b = arm(tmp_path, "1s", {}, [])
    d = od.diff(a, b)
    assert d["kinds"] == {"js": (100, 0)}
    assert d["browser"] == (4050, 0)
    out = od.render(d, "fork", "stock")
    assert "browser-internal" in out and "html" not in out


def test_diff_main_takes_a_site_name(tmp_path, capsys):
    a, b = arm(tmp_path, "a", {}, []), arm(tmp_path, "b", {}, [])
    assert od.main([str(a), str(b), "--site", "facebook"]) == 0
    assert od.main([str(a), str(b), "--site", "nosuch"]) == 3
