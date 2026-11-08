"""The six host scripts that launch a stock control run it on a seeded profile and refuse an unseeded one (stock_seed.py,
measure_step2.seeded_control). Each script's real main() runs against a fake `camoucrome.launch`, a fake patchright and
a fake winhost whose priming launch writes what a primed template holds: no browser, proxy or site is touched."""
import json
import pathlib
import sys
import types
from unittest import mock

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "client" / "python"))
import measure_step2 as m2  # noqa: E402
import stock_seed  # noqa: E402
from test_stock_seed import write_template  # noqa: E402

STOCK = "stock/chrome.exe"
FORK = "fork/chrome.exe"


class Halt(BaseException):
    """The script launched as many browsers as the test wanted to see."""


class Page:
    def __init__(self, w):
        self.w = w

    def evaluate(self, js, *a):
        if stock_seed.UNSEEDED_MARKER in js:
            return self.w.join_on
        if "RTCPeerConnection" in js:
            return []
        return "203.0.113.9" if "fetch(" in js else None

    def locator(self, sel):
        return types.SimpleNamespace(text_content=lambda: '{"a": 1}')

    def goto(self, url, **k):
        self.w.gotos.append(url)

    def __getattr__(self, name):  # wait_for_function, mouse, bring_to_front...
        return mock.MagicMock()


@pytest.fixture
def w(monkeypatch, tmp_path):
    import camoucrome
    import gpu_gate
    w = types.SimpleNamespace(launches=[], gotos=[], primes=[], join_on=False, allow=99)

    def launch(pw, exe, **k):
        d = k.get("user_data_dir")
        if len(w.launches) >= w.allow:
            raise Halt
        w.launches.append({"exe": exe, "dir": d, "files": sorted(x.name for x in pathlib.Path(d).iterdir()) if d else None,
                           "proxy": k.get("proxy")})
        ctx = mock.MagicMock()
        ctx.pages = [Page(w)]
        return ctx

    def cdp_eval(page_html, expression="", args=(), headed=True, profile=None, wait_ms=0, exe=None, graceful_close=False, **k):
        w.primes.append({"exe": exe, "args": list(args), "graceful": graceful_close, "profile": profile})
        write_template(profile)

    fake_pw = types.ModuleType("patchright.sync_api")
    fake_pw.sync_playwright = lambda: mock.MagicMock(**{"__enter__.return_value": object(), "__exit__.return_value": False})
    monkeypatch.setitem(sys.modules, "patchright", types.ModuleType("patchright"))
    monkeypatch.setitem(sys.modules, "patchright.sync_api", fake_pw)
    monkeypatch.setitem(sys.modules, "winhost", types.SimpleNamespace(cdp_eval=cdp_eval))
    monkeypatch.setattr(camoucrome, "launch", launch)
    monkeypatch.setattr(gpu_gate, "check", lambda *a: None)
    monkeypatch.setattr(gpu_gate, "read_ctx", lambda ctx: 0)
    monkeypatch.setattr(gpu_gate, "require_interactive", lambda: None)
    monkeypatch.setenv("CAMOU_STOCK_APP", "stock")
    monkeypatch.setenv("CAMOU_FORK_EXE", FORK)
    monkeypatch.setattr(m2, "identity", lambda seed: {"config": {"mediaDevices:seed": 1}, "launch": {}})
    monkeypatch.setattr(m2, "probe_host_draw", lambda exe: {"host_renderer": "r", "host_families": []})
    monkeypatch.chdir(tmp_path)
    return w


def copies(w, exe):
    return [x for x in w.launches if x["exe"] == exe]


# ---- measure_canvas_noise ----
def run_canvas(tmp_path, monkeypatch):
    import measure_canvas_noise as mc
    import step2_rows
    import windows_verify_set
    monkeypatch.setattr(m2, "exe_version", lambda p: "1")
    monkeypatch.setattr(step2_rows, "version_problems", lambda *a, **k: [])
    monkeypatch.setattr(windows_verify_set, "pin_tag", lambda c: "x")
    return lambda: mc.main(["run", "--seeds", "2", "--out", str(tmp_path / "out")])


def test_canvas_noise_stock_cell_is_seeded_and_the_fork_cells_are_not(w, tmp_path, monkeypatch):
    run = run_canvas(tmp_path, monkeypatch)
    w.allow = 3
    with pytest.raises(Halt):
        run()
    stock, *fork = w.launches
    assert stock["exe"].endswith("chrome.exe") and "VariationsSeedV2" in stock["files"]
    assert [x["exe"] for x in fork] == [FORK, FORK] and all("VariationsSeedV2" not in (x["files"] or []) for x in fork)
    assert len(w.primes) == 1 and w.primes[0]["exe"] == stock["exe"] and w.primes[0]["args"] == []


def test_canvas_noise_unseeded_stock_is_unmeasured_after_one_launch(w, tmp_path, monkeypatch):
    w.join_on = True
    with pytest.raises(SystemExit, match="UNMEASURED: UNSEEDED"):
        run_canvas(tmp_path, monkeypatch)()
    assert len(w.launches) == 1


# ---- verify_s3_host ----
def run_s3():
    import verify_s3_host as s3
    return s3.main


def test_s3_control_is_seeded_the_fork_is_not_and_no_stock_profile_is_reused(w):
    w.allow = 2
    with pytest.raises(Halt):
        run_s3()()
    control, fork = w.launches[:2]
    assert "VariationsSeedV2" in control["files"] and "VariationsSeedV2" not in (fork["files"] or [])
    assert len(w.primes) == 1


def test_s3_unseeded_control_is_unmeasured(w):
    w.join_on = True
    with pytest.raises(SystemExit, match="UNMEASURED: UNSEEDED"):
        run_s3()()
    assert len(w.launches) == 1


# ---- verify_pixels_real ----
def run_pixels():
    import verify_pixels_real as vp
    return vp.main


def test_pixels_both_stock_reads_are_seeded_and_get_their_own_copy(w):
    w.allow = 3
    with pytest.raises(Halt):
        run_pixels()([])
    s1, s2, fork = w.launches
    assert "VariationsSeedV2" in s1["files"] and "VariationsSeedV2" in s2["files"] and s1["dir"] != s2["dir"]
    assert "VariationsSeedV2" not in (fork["files"] or [])


def test_pixels_unseeded_stock_is_unmeasured(w):
    w.join_on = True
    with pytest.raises(SystemExit, match="UNMEASURED: UNSEEDED"):
        run_pixels()([])
    assert len(w.launches) == 1


# ---- verify_geoip_pixelscan ----
def run_pixelscan(monkeypatch):
    import verify_geoip_pixelscan as vg
    from camoucrome import gen, geoip
    monkeypatch.setenv("CAMOU_GEOIP_DB", "db")
    monkeypatch.setattr(m2, "settle", lambda page: "text")  # the real one polls the page for minutes
    monkeypatch.setattr(geoip, "exit_ip", lambda *a, **k: "203.0.113.9")
    monkeypatch.setattr(geoip, "lookup", lambda ip, db=None: {"timezone": "Europe/Paris"})
    monkeypatch.setattr(geoip, "check_zone", lambda a, b: "contradicts")
    monkeypatch.setattr(gen, "generate", lambda *a, **k: {"config": {}, "launch": {}})
    return vg.main


def test_pixelscan_stock_is_seeded_and_primed_direct_and_the_fork_arms_are_not(w, monkeypatch):
    run_pixelscan(monkeypatch)([])  # all three loads run, then the verdict
    stock, red, green = w.launches
    assert "VariationsSeedV2" in stock["files"] and all("VariationsSeedV2" not in (x["files"] or []) for x in (red, green))
    assert w.primes[0]["args"] == []  # the prime has no proxy or site argument
    assert w.primes[0]["graceful"] and w.gotos[0] == m2.DETECTORS["pixelscan"]  # only the script's own load, after the guard


def test_pixelscan_unseeded_stock_is_unmeasured_before_the_detector_page_loads(w, monkeypatch):
    w.join_on = True
    with pytest.raises(SystemExit, match="UNMEASURED: UNSEEDED"):
        run_pixelscan(monkeypatch)([])
    assert len(w.launches) == 1 and w.gotos == []


# ---- measure_remote_voices ----
def run_voices(tmp_path, monkeypatch, arms):
    import measure_remote_voices as mv
    monkeypatch.setattr(mv, "gpu_crash_count", lambda ctx: "0")
    monkeypatch.setattr(sys, "argv", ["x", str(tmp_path / "o.jsonl"), "1", arms])
    return mv.main


def test_voices_every_stock_arm_profile_is_seeded_and_the_fork_arm_is_not(w, tmp_path, monkeypatch):
    run_voices(tmp_path, monkeypatch, "stock,stock-fr,fork")()
    names = [x["files"] for x in w.launches]
    assert len(names) == 3 and all("VariationsSeedV2" in f for f in names[:2]) and "VariationsSeedV2" not in names[2]
    assert len(w.primes) == 1
    assert all(not pathlib.Path(x["dir"]).exists() for x in w.launches)  # the script removes its own profiles


def test_voices_an_unseeded_stock_cell_is_recorded_unmeasured_never_ok(w, tmp_path, monkeypatch):
    w.join_on = True
    run_voices(tmp_path, monkeypatch, "stock")()
    row = json.loads((tmp_path / "o.jsonl").read_text().splitlines()[0])
    assert "Unseeded" in row["error"] and row["unmeasured"] is True


def test_voices_unseeded_template_exits_unmeasured_before_any_launch(w, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "winhost", types.SimpleNamespace(cdp_eval=lambda *a, **k: None))  # primes nothing
    with pytest.raises(SystemExit, match="UNMEASURED: UNSEEDED"):
        run_voices(tmp_path, monkeypatch, "stock")()
    assert w.launches == []


# ---- verify_webrtc_realproxy ----
def run_webrtc(tmp_path, monkeypatch, arm):
    import verify_webrtc_realproxy as vr
    proxy = tmp_path / "p.json"
    proxy.write_text(json.dumps({"server": "proxy.invalid:1", "username_template": "u-{session}", "password": "pw"}))
    monkeypatch.setattr(vr.urllib.request, "urlopen", lambda *a, **k: types.SimpleNamespace(read=lambda: b"198.51.100.1"))
    return lambda: vr.main(["--arm", arm, "--proxy", str(proxy)])


def test_webrtc_stock_arm_is_seeded_primed_without_the_proxy_and_the_fork_arm_is_not(w, tmp_path, monkeypatch):
    run_webrtc(tmp_path, monkeypatch, "stock")()
    assert "VariationsSeedV2" in w.launches[0]["files"] and w.launches[0]["proxy"]
    assert len(w.primes) == 1 and w.primes[0]["args"] == []  # the priming launch carries no proxy
    run_webrtc(tmp_path, monkeypatch, "fork")()
    assert w.launches[1]["dir"] is None and len(w.primes) == 1


def test_webrtc_unseeded_stock_is_unmeasured_before_the_proxy_sees_a_request(w, tmp_path, monkeypatch):
    w.join_on = True
    with pytest.raises(SystemExit, match="UNMEASURED: UNSEEDED"):
        run_webrtc(tmp_path, monkeypatch, "stock")()
    assert w.gotos == [] and len(w.launches) == 1


def test_a_template_that_fails_its_checks_ends_every_script_unmeasured_before_a_launch(w, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "winhost", types.SimpleNamespace(cdp_eval=lambda *a, **k: None))
    with pytest.raises(SystemExit, match="UNMEASURED: UNSEEDED.*priming launch"):
        run_webrtc(tmp_path, monkeypatch, "stock")()
    with pytest.raises(SystemExit, match="UNMEASURED: UNSEEDED.*priming launch"):
        run_s3()()
    assert w.launches == []


# ---- the stock path: CAMOU_STOCK_APP, else the shared default m2.STOCK_APP ----
def test_voices_stock_arm_honours_camou_stock_app(w, tmp_path, monkeypatch):
    monkeypatch.setenv("CAMOU_STOCK_APP", "elsewhere")
    run_voices(tmp_path, monkeypatch, "stock")()
    assert w.launches[0]["exe"] == "elsewhere/chrome.exe"


def test_webrtc_stock_arm_uses_the_shared_stock_default(w, tmp_path, monkeypatch):
    monkeypatch.delenv("CAMOU_STOCK_APP")
    monkeypatch.setattr(m2, "STOCK_APP", "pinned")  # m2's own default is the installed Chrome path, so mark it
    run_webrtc(tmp_path, monkeypatch, "stock")()
    assert w.launches[0]["exe"] == "pinned/chrome.exe"
