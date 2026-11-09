"""measure_layer3's stock arms launch on a seeded profile and an unseeded one is never `ok` (stock_seed.py).
`camoucrome.launch` is a fake; no browser, proxy or site is touched."""
import json
import pathlib
import sys
import types

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "client" / "python"))
import measure_layer3 as ml  # noqa: E402
import measure_step2 as m2  # noqa: E402
import stock_seed  # noqa: E402
from test_stock_seed import write_template  # noqa: E402

SITE = {"vendor": "cloudflare", "url": "https://a.example/", "next_url": "https://a.example/n", "ok_marker": "m"}


class Page:
    url = "https://a.example/"
    mouse = types.SimpleNamespace(wheel=lambda *a: None)

    def __init__(self, join_on):
        self.join_on, self.evaluated = join_on, []

    def on(self, *a):
        pass

    def wait_for_timeout(self, _ms):
        pass

    def evaluate(self, js):
        self.evaluated.append(js)
        return self.join_on if "joinAdInterestGroup" in js else 5


@pytest.fixture
def world(monkeypatch, tmp_path):
    """A fake launcher recording each launch's profile contents; `join_on` makes the page look unseeded."""
    import camoucrome
    import gpu_gate
    w = types.SimpleNamespace(launches=[], pages=[], loads=[], join_on=False)

    def launch(pw, exe, **k):
        d = pathlib.Path(k["user_data_dir"])
        w.launches.append({"exe": exe, "dir": d, "files": sorted(x.name for x in d.iterdir()),
                           "pref": json.loads((d / "Default" / "Preferences").read_text())["webrtc"]["ip_handling_policy"]})
        page = Page(w.join_on)
        w.pages.append(page)
        return types.SimpleNamespace(pages=[page], route=lambda *a: None, close=lambda: None)

    monkeypatch.setattr(camoucrome, "launch", launch)
    monkeypatch.setattr(gpu_gate, "read_ctx", lambda ctx: 0)
    monkeypatch.setattr(ml, "settle", lambda *a, **k: ({"outcome": "pass", "markers": [], "cookies": []}, False))
    monkeypatch.setattr(ml, "load", lambda page, url, note=None: w.loads.append(url) or 200)
    monkeypatch.setattr(ml, "read_exit_ip", lambda page: w.loads.append("exit-ip") or "203.0.113.5")
    w.args = types.SimpleNamespace(gpu_gate=False, headed=False, settle=1, dwell=0, warm=False)
    w.seed = stock_seed.SeededStock(write_template, tmp_path)
    w.seed.__enter__()
    yield w
    w.seed.__exit__(None, None, None)


def arm(stock):
    return m2.Arm("stock" if stock else "fork", "x.exe", None, [], stock=stock)


def test_a_stock_visit_runs_on_a_seeded_copy_that_still_carries_the_webrtc_pref_and_is_removed(world):
    ml.visit(None, arm(True), SITE, None, world.args, seed=world.seed)
    one = world.launches[0]
    assert "VariationsSeedV2" in one["files"] and "Local State" in one["files"]
    assert one["pref"] == "disable_non_proxied_udp"
    assert not one["dir"].exists() and world.seed.copies == []


def test_the_fork_arm_gets_no_seed_and_is_not_guarded(world):
    ml.visit(None, arm(False), SITE, None, world.args, seed=world.seed)
    assert world.launches[0]["files"] == ["Default"]  # the WebRTC pref only
    assert not any("joinAdInterestGroup" in js for js in world.pages[0].evaluated)


def test_an_unseeded_stock_visit_raises_before_any_proxy_or_site_traffic_and_the_row_is_unmeasured(world):
    world.join_on = True
    with pytest.raises(stock_seed.Unseeded, match="UNSEEDED"):
        ml.visit(None, arm(True), SITE, {"server": "p"}, world.args, seed=world.seed)
    assert world.loads == []  # no exit-address lookup, no vendor page
    assert not world.launches[0]["dir"].exists()
    assert ml.unmeasured(stock_seed.Unseeded("x")) and not ml.unmeasured(RuntimeError("x"))


def test_a_stock_visit_without_a_seed_object_is_still_guarded_not_ok(world):
    world.join_on = True  # a bare profile: the browser shows the compiled defaults
    with pytest.raises(stock_seed.Unseeded):
        ml.visit(None, arm(True), SITE, None, world.args)


def test_aa_makes_the_f_arm_a_stock_arm_and_a_fork_run_does_not():
    aa = ml.pair_arms("stock.exe", "stock.exe", None, [], None)
    assert aa["S"].stock and aa["F"].stock
    fork = ml.pair_arms("stock.exe", "fork.exe", {"config": {}, "launch": {}}, ["--a"], "--plant")
    assert fork["S"].stock and not fork["F"].stock and fork["F"].args == ["--a", "--plant"]


def test_a_warm_profile_is_seeded_once_and_then_kept(world, tmp_path):
    udd = tmp_path / "profiles" / "S-0"
    udd.mkdir(parents=True)
    ml.visit(None, arm(True), SITE, None, world.args, str(udd), world.seed)
    assert "VariationsSeedV2" in world.launches[0]["files"]
    (udd / "Local State").write_text('{"made-by-the-browser": 1}')  # what the first launch left
    ml.visit(None, arm(True), SITE, None, world.args, str(udd), world.seed)
    assert json.loads((udd / "Local State").read_text()) == {"made-by-the-browser": 1}  # not overwritten
    assert udd.exists()  # a warm profile is the caller's


def test_a_warm_profile_that_lost_its_seed_is_caught_by_the_guard(world, tmp_path):
    udd = tmp_path / "warm"
    ml.visit(None, arm(True), SITE, None, world.args, str(udd), world.seed)
    world.join_on = True  # variations safe mode after too many killed launches
    with pytest.raises(stock_seed.Unseeded):
        ml.visit(None, arm(True), SITE, None, world.args, str(udd), world.seed)


def test_the_pair_loop_keeps_an_unseeded_row_unmeasured_and_does_not_retry_it():
    tries = []

    def attempt(k):
        tries.append(k)
        return ({"S": {"outcome": "unmeasured", "error": "Unseeded", "bytes": 0}, "F": {"outcome": "pass", "bytes": 9}},
                {"S": None, "F": "203.0.113.5"})
    rows = ml.run_pair_with_retries(attempt, 2, check=True)
    assert tries == [0] and rows["S"]["outcome"] == "unmeasured" and rows["S"]["error"] == "Unseeded"


def test_the_stock_note_says_whether_the_control_was_seeded():
    assert "seeded" in ml.stock_note({"stock_seeded": True}) and "NO variations seed" not in ml.stock_note({"stock_seeded": True})
    for old in ({}, {"stock_seeded": False}):  # a run before this change has no key
        assert "NO variations seed" in ml.stock_note(old)


def test_meta_flags_record_the_opt_out_so_a_resume_cannot_switch():
    a = ml.build_parser().parse_args(["run", "--no-seed-stock"])
    assert ml.flags_of(a)["no_seed_stock"] is True
    assert ml.flags_of(ml.build_parser().parse_args(["run"]))["no_seed_stock"] is False


def test_a_template_that_fails_its_checks_exits_unmeasured_before_any_browser_or_proxy(monkeypatch, tmp_path):
    fake = types.ModuleType("patchright.sync_api")
    fake.sync_playwright = lambda: pytest.fail("a browser must not start")
    monkeypatch.setitem(sys.modules, "patchright", types.ModuleType("patchright"))
    monkeypatch.setitem(sys.modules, "patchright.sync_api", fake)
    monkeypatch.setitem(sys.modules, "winhost", types.SimpleNamespace())

    def refuse(winhost, exe, args=(), headed=True, workdir=None):
        raise stock_seed.Unseeded("UNSEEDED: the priming launch left no usable seeded template: no VariationsSeedV2")
    monkeypatch.setattr(stock_seed, "seeded_stock", refuse)
    sites = tmp_path / "sites.json"
    sites.write_text(json.dumps({"cloudflare": [{"id": f"c{i}", "url": "https://a.example/", "next_url": "https://a.example/n",
                                                 "ok_marker": "#c"} for i in range(3)]}))
    with pytest.raises(SystemExit, match="UNMEASURED: UNSEEDED"):
        ml.main(["run", "--out", str(tmp_path), "--sites", str(sites), "--stock-exe", "stock.exe", "--aa"])
