"""measure_layer3: the plumbing on synthetic files, and (opt-in, CAMOU_TEST_CHROME) the whole pipeline against a local
fixture site with a real browser -- a planted difference must be found, stock against stock must not."""
import http.server
import json
import os
import pathlib
import sys
import threading

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "client" / "python"))
import measure_layer3 as ml  # noqa: E402


def write_sites(tmp_path, base="http://127.0.0.1:1", vendors=("cloudflare",), per=2, **over):
    doc = {v: [{"id": f"{v[:2]}{i}", "url": f"{base}/{v}/{i}", "next_url": f"{base}/{v}/{i}/next", "ok_marker": "#content", **over}
               for i in range(per)] for v in vendors}
    p = tmp_path / "sites.json"
    p.write_text(json.dumps(doc))
    return str(p)


def test_load_sites_numbers_them_and_keeps_the_vendor(tmp_path):
    sites = ml.load_sites(write_sites(tmp_path, vendors=("cloudflare", "akamai")))
    assert [(s["idx"], s["vendor"]) for s in sites] == [(0, "cloudflare"), (1, "cloudflare"), (2, "akamai"), (3, "akamai")]


@pytest.mark.parametrize("missing", ["next_url", "ok_marker", "url"])
def test_load_sites_refuses_a_site_that_is_not_ready(tmp_path, missing):
    with pytest.raises(SystemExit, match=missing):
        ml.load_sites(write_sites(tmp_path, **{missing: None}))


def test_proxy_for_gives_both_arms_one_value_per_session():
    cfg = {"server": "http://p.example:1", "username_template": "u-session-{session}", "password": "pw"}
    assert ml.proxy_for(cfg, "r1") == {"server": "http://p.example:1", "username": "u-session-r1", "password": "pw"}
    assert ml.proxy_for(cfg, "r1") == ml.proxy_for(cfg, "r1") != ml.proxy_for(cfg, "r2")
    assert ml.proxy_for(None, "r1") is None


def test_the_same_extra_arguments_go_to_both_arms_and_no_dead_webrtc_switch():
    cfg = {"server": "http://p.example:1", "username_template": "u-{session}", "password": "pw"}
    assert ml.common_args(cfg, ["--x"]) == ["--x"] and not hasattr(ml, "WEBRTC_POLICY")
    assert ml.common_args(None, ["--x"]) == ["--x"] and ml.common_args(None) == []


def test_the_secret_scan_finds_the_password_and_the_proxy_host_in_any_file(tmp_path):
    cfg = {"server": "http://gate.proxy.example:8000", "username_template": "u-{session}", "password": "S3cretPw"}
    (tmp_path / "ok.jsonl").write_text('{"outcome": "pass"}')
    assert ml.secret_scan(tmp_path, ml.secrets_of(cfg)) == []
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "log.txt").write_text("proxy auth failed for s3cretpw")
    (tmp_path / "meta.json").write_text('{"x": "gate.proxy.example"}')
    assert sorted(pathlib.Path(p).name for p in ml.secret_scan(tmp_path, ml.secrets_of(cfg))) == ["log.txt", "meta.json"]
    assert ml.secrets_of(None) == []


def rows_file(run_dir, spec, rounds=10):
    """spec: {(vendor, site): (stock_outcome, fork_outcome)} -> results.jsonl + meta.json"""
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for (vendor, site), (s, f) in spec.items():
        for r in range(rounds):
            for arm, out in (("S", s), ("F", f)):
                lines.append(json.dumps({"round": r, "site": site, "vendor": vendor, "arm": arm, "order": "SF", "outcome": out, "bytes": 1000, "note": "http://lab.example/x"}))
    (run_dir / "results.jsonl").write_text("\n".join(lines) + "\n")
    (run_dir / "meta.json").write_text(json.dumps({"run": run_dir.name, "rounds": rounds, "warm": False, "aa": False, "plant": False, "proxy": True,
                                                     "sites_per_vendor": {v: 3 for v in ml.VENDORS}}))


def test_report_finds_a_planted_vendor_difference_and_not_a_null_one(tmp_path):
    rows_file(tmp_path / "run", {("cloudflare", i): ("pass", "challenge") for i in range(3)} | {("datadome", i + 3): ("pass", "pass") for i in range(3)})
    got = ml.vendor_rows(tmp_path / "run", resamples=500)
    assert got["cloudflare"]["d"] == 1.0 and got["cloudflare"]["lo"] > 0
    assert got["datadome"]["d"] == 0 and got["datadome"]["lo"] <= 0 <= got["datadome"]["hi"]
    assert "akamai" not in got  # no rows, no line


def test_unknown_and_unmeasured_runs_are_not_counted_as_passes(tmp_path):
    rows_file(tmp_path / "run", {("cloudflare", i): ("unknown", "unmeasured") for i in range(3)})
    got = ml.vendor_rows(tmp_path / "run", resamples=100)["cloudflare"]
    assert got["n"] == 0 and got["unmeasured"]
    assert "UNMEASURED" in ml.table({"cloudflare": got})


def test_a_zero_width_interval_is_starred_and_footnoted(tmp_path):
    rows_file(tmp_path / "run", {("datadome", i): ("pass", "pass") for i in range(3)})
    got = ml.vendor_rows(tmp_path / "run", resamples=200)
    assert got["datadome"]["degenerate"]
    text = ml.table(got)
    assert "[+0.00, +0.00]*" in text and "* zero-width interval: no variation observed" in text
    rows_file(tmp_path / "run2", {("cloudflare", 0): ("pass", "challenge"), ("cloudflare", 1): ("pass", "pass"), ("cloudflare", 2): ("pass", "pass")})
    assert "*" not in ml.table(ml.vendor_rows(tmp_path / "run2", resamples=200))


def test_the_table_prints_the_site_weighted_d_not_the_pooled_one(tmp_path):
    rows_file(tmp_path / "run", {("cloudflare", i): ("pass", "challenge") for i in range(3)})
    got = ml.vendor_rows(tmp_path / "run", resamples=100)
    assert "d (fork - stock, site-weighted)" in ml.table(got)
    got["cloudflare"] = {**got["cloudflare"], "d": 0.25, "d_pooled": 0.75, "degenerate": False}
    text = ml.table(got)
    assert "+0.25" in text and "+0.75" not in text


def test_budget_extrapolates_one_round_and_refuses_over_the_limit(tmp_path, capsys):
    rows_file(tmp_path / "run", {("cloudflare", 0): ("pass", "pass")}, rounds=1)
    args = lambda sites, rounds, limit: type("A", (), {"run_dir": str(tmp_path / "run"), "sites": sites, "rounds": rounds, "limit_gb": limit})()  # noqa: E731
    assert ml.budget_cmd(args(12, 20, 5.0)) == 0  # 1000 B x 12 x 20 x 2 x 4 = 1.9 MB
    assert ml.budget_cmd(args(12, 20, 0.000001)) == 2
    assert "OVER" in capsys.readouterr().err


def test_budget_pins_four_run_equivalents_against_the_dry_run_mean(tmp_path):
    run = tmp_path / "run"
    rows_file(run, {("cloudflare", 0): ("pass", "pass")}, rounds=1)
    (run / "results.jsonl").write_text((run / "results.jsonl").read_text().replace('"bytes": 1000', '"bytes": 2465956'))  # dry run: 2.47 MB/visit
    args = lambda rounds: type("A", (), {"run_dir": str(run), "sites": 12, "rounds": rounds, "limit_gb": 5.0})()  # noqa: E731
    assert ml.budget_cmd(args(15)) == 0  # 3.55 GB
    assert ml.budget_cmd(args(21)) == 0  # 4 -> 4.97 GB; 4.5 would be 5.59 GB
    assert ml.budget_cmd(args(22)) == 2  # 5.20 GB


@pytest.fixture
def terms(monkeypatch):
    import check_privacy
    monkeypatch.setattr(check_privacy, "load_terms", lambda: {"<x>": ["zzqq-private"]})


def scrub_args(tmp_path):
    return type("A", (), {"run_dir": str(tmp_path / "run"), "out_dir": str(tmp_path / "out")})()


def test_scrub_writes_only_the_vendor_table(tmp_path, terms):
    rows_file(tmp_path / "run", {("cloudflare", i): ("pass", "challenge") for i in range(3)})
    assert ml.scrub_cmd(scrub_args(tmp_path)) == 0  # one vendor of three measured sites scrubs; the others have no rows
    text = (tmp_path / "out" / "layer3-baseline.md").read_text()
    assert "| cloudflare |" in text and "blocked in both arms" in text and "fork against stock" in text
    assert "lab.example" not in text and "http" not in text  # the rows carry a url; the table must not


def test_scrub_refuses_a_vendor_with_fewer_than_3_measured_sites_whatever_the_list_says(tmp_path, terms):
    rows_file(tmp_path / "run", {("cloudflare", 0): ("pass", "challenge"), ("cloudflare", 1): ("pass", "challenge")})  # meta lists 3
    with pytest.raises(SystemExit, match="fewer than 3 sites"):
        ml.scrub_cmd(scrub_args(tmp_path))


def test_scrub_names_a_no_identity_fork(tmp_path, terms):
    rows_file(tmp_path / "run", {("cloudflare", i): ("pass", "challenge") for i in range(3)})
    meta = json.loads((tmp_path / "run" / "meta.json").read_text())
    meta["flags"] = {"no_identity": True}
    (tmp_path / "run" / "meta.json").write_text(json.dumps(meta))
    ml.scrub_cmd(scrub_args(tmp_path))
    assert "fork (no identity) against stock" in (tmp_path / "out" / "layer3-baseline.md").read_text()


def test_scrub_refuses_when_there_are_no_private_terms(tmp_path, monkeypatch):
    import check_privacy
    monkeypatch.setattr(check_privacy, "load_terms", lambda: {})
    rows_file(tmp_path / "run", {("cloudflare", i): ("pass", "challenge") for i in range(3)})
    with pytest.raises(SystemExit, match="private terms"):
        ml.scrub_cmd(scrub_args(tmp_path))
    assert not (tmp_path / "out").exists()


def test_budget_averages_only_visits_that_measured_something(tmp_path, capsys):
    rows_file(tmp_path / "run", {("cloudflare", 0): ("pass", "pass"), ("cloudflare", 1): ("unknown", "unknown")}, rounds=1)
    a = type("A", (), {"run_dir": str(tmp_path / "run"), "sites": 1, "rounds": 1, "limit_gb": 5.0})()
    ml.budget_cmd(a)
    assert "mean 1000 bytes" in capsys.readouterr().out
    rows_file(tmp_path / "none", {("cloudflare", 0): ("unknown", "unmeasured")}, rounds=1)
    a.run_dir = str(tmp_path / "none")
    with pytest.raises(SystemExit, match="budget"):
        ml.budget_cmd(a)


def test_compare_exit_codes(tmp_path, capsys):
    same = {("cloudflare", i): ("pass", "pass") for i in range(3)}
    diff = {("cloudflare", i): ("pass", "challenge") for i in range(3)}
    for name, spec in (("a", same), ("b", same), ("c", diff), ("n", {("akamai", i): ("pass", "pass") for i in range(3)}),
                       ("u", {("cloudflare", i): ("unknown", "unknown") for i in range(3)})):
        rows_file(tmp_path / name, spec)
    cmp = lambda x, y: ml.compare_cmd(type("A", (), {"run_a": str(tmp_path / x), "run_b": str(tmp_path / y)})())  # noqa: E731
    assert cmp("a", "b") == 0
    assert cmp("a", "c") == 2
    assert cmp("a", "n") == 3  # nothing in common was compared
    assert cmp("a", "u") == 3  # unmeasured


def test_parity_problems():
    s = ["chrome", "--a"]
    assert ml.parity_problems(s, s, None, on_windows=True) == []
    assert ml.parity_problems([], s, None, on_windows=True)  # an unread argv refuses the run on Windows
    assert ml.parity_problems(None, s, None, on_windows=True)
    assert ml.parity_problems([], [], None, on_windows=False) == []  # no /proc here
    assert ml.parity_problems(s, s + ["--b"], None, on_windows=True)
    assert ml.parity_problems(s, s + ["--b"], "--b", on_windows=True) == []


def test_resume_refuses_a_changed_flag_and_keeps_started():
    old = {"started": "T0", "rounds": 5, "flags": {"aa": True, "seed": 1}}
    with pytest.raises(SystemExit, match="aa"):
        ml.resume_meta(old, {"rounds": 5, "started": "T1", "flags": {"aa": False, "seed": 1}})
    with pytest.raises(SystemExit, match="flags"):
        ml.resume_meta({"started": "T0", "rounds": 5}, {"rounds": 5, "started": "T1", "flags": {"aa": False}})
    got = ml.resume_meta(old, {"rounds": 8, "started": "T1", "flags": {"aa": True, "seed": 1}})
    assert got["started"] == "T0" and got["rounds"] == 8


class FakePage:
    def __init__(self, fail=1):
        self.fail, self.waited = fail, 0

    def evaluate(self, _js):
        if self.fail:
            self.fail -= 1
            raise RuntimeError("Execution context was destroyed")
        return {"title": "Home", "text": "hi", "html": "<main id=content></main>", "frames": []}

    def locator(self, _sel):
        return type("L", (), {"count": lambda self: 1})()

    def wait_for_load_state(self, timeout=0):
        self.waited += 1

    def wait_for_timeout(self, _ms):
        pass


def test_settle_survives_a_navigation_during_the_poll():
    ctx = type("C", (), {"cookies": lambda self: []})()
    page = FakePage(fail=1)
    res, saw = ml.settle(page, ctx, {"vendor": "cloudflare", "ok_marker": "#content"}, 200, limit=5)
    assert res["outcome"] == "pass" and page.waited == 1
    res, _ = ml.settle(FakePage(fail=10**6), ctx, {"vendor": "cloudflare", "ok_marker": "#content"}, 200, limit=0.01)
    assert res["outcome"] == "unknown"


def test_secrets_of_handles_an_ipv6_server_and_skips_short_hosts():
    cfg = {"server": "http://[::1]:8000", "username_template": "u-{session}", "password": "pw"}
    assert ml.secrets_of(cfg) == ["pw"]
    cfg["server"] = "http://gate.proxy.example:8000"
    assert ml.secrets_of(cfg) == ["pw", "gate.proxy.example"]


def test_secret_scan_skips_the_warm_profiles(tmp_path):
    (tmp_path / "profiles" / "S-0").mkdir(parents=True)
    (tmp_path / "profiles" / "S-0" / "Cookies").write_text("S3cretPw")
    assert ml.secret_scan(tmp_path, ["S3cretPw"]) == []


def ns(**kw):
    return type("NS", (), kw)()


def test_the_identity_run_refuses_without_the_host_zone_and_locale():
    for kw in ({}, {"timezone": "Europe/Paris"}, {"locale": "fr-FR"}):
        with pytest.raises(SystemExit, match="timezone"):
            ml.build_identity(ns(aa=False, no_identity=False, identity_seed=1, **{"timezone": None, "locale": None, **kw}))
    for kw in ({"aa": True, "no_identity": False}, {"aa": False, "no_identity": True}):
        assert ml.build_identity(ns(identity_seed=1, timezone=None, locale=None, **kw)) is None


def test_the_identity_carries_exactly_the_given_zone_and_locale():
    ident = ml.build_identity(ns(aa=False, no_identity=False, identity_seed=1, timezone="Europe/Paris", locale="fr-FR"))
    assert ident["config"]["timezone:id"] == "Europe/Paris" and ident["config"]["locale:tag"] == "fr-FR"


GEN9_HOST = "ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00009BC5) Direct3D11 vs_5_0 ps_5_0, D3D11)"
RTX_HOST = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) Direct3D11 vs_5_0 ps_5_0, D3D11)"


def _webgl_keys(ident):
    return [k for k in ident["config"] if k.startswith(("webGl:", "webGl2:"))]


def test_the_identity_claims_no_gpu_without_a_host_probe_and_on_a_non_gen9_host():
    a = ns(aa=False, no_identity=False, identity_seed=13, timezone="Europe/Paris", locale="fr-FR")
    assert _webgl_keys(ml.build_identity(a)) == []
    assert _webgl_keys(ml.build_identity(a, {"host_renderer": RTX_HOST})) == []


def test_the_identity_draws_a_gen9_gpu_on_a_gen9_host():
    a = ns(aa=False, no_identity=False, identity_seed=13, timezone="Europe/Paris", locale="fr-FR")
    ident = ml.build_identity(a, {"host_renderer": GEN9_HOST})
    assert "Direct3D11" in ident["config"]["webGl:renderer"] and "Intel" in ident["config"]["webGl:renderer"]


def test_headed_defaults_to_the_platform_and_can_be_switched_off():
    p = ml.build_parser()
    assert p.parse_args(["run"]).headed == (os.name == "nt")
    assert p.parse_args(["run", "--no-headed"]).headed is False and p.parse_args(["run", "--headed"]).headed is True


def test_scrub_header_names_headed_or_headless(tmp_path, terms):
    rows_file(tmp_path / "run", {("cloudflare", i): ("pass", "challenge") for i in range(3)})
    for headed, word in ((True, "headed"), (False, "headless")):
        meta = json.loads((tmp_path / "run" / "meta.json").read_text())
        meta["flags"] = {"headed": headed}
        (tmp_path / "run" / "meta.json").write_text(json.dumps(meta))
        ml.scrub_cmd(scrub_args(tmp_path))
        assert f"; {word};" in (tmp_path / "out" / "layer3-baseline.md").read_text()


def test_a_window_larger_than_the_desktop_is_a_problem():
    assert ml.window_problems([1920, 1152], [2560, 1440]) == []
    assert ml.window_problems([1920, 1152], [1920, 1080]) and ml.window_problems([2000, 800], [1920, 1080])
    assert ml.window_problems([1920, 1152], None) == [] and ml.window_problems(None, [1, 1]) == []


def test_budget_refuses_a_measured_visit_without_bytes_and_says_what_the_bytes_are(tmp_path, capsys):
    rows_file(tmp_path / "run", {("cloudflare", 0): ("pass", "pass")}, rounds=1)
    a = type("A", (), {"run_dir": str(tmp_path / "run"), "sites": 1, "rounds": 1, "limit_gb": 5.0})()
    ml.budget_cmd(a)
    assert "lower bound, not the proxy's counter" in capsys.readouterr().out
    ml.report_cmd(a)
    assert "lower bound, not the proxy's counter" in capsys.readouterr().out
    rows_file(tmp_path / "zero", {("cloudflare", 0): ("pass", "pass")}, rounds=1)
    rs = [json.loads(line) for line in (tmp_path / "zero" / "results.jsonl").read_text().splitlines()]
    rs[0]["bytes"] = 0
    (tmp_path / "zero" / "results.jsonl").write_text("\n".join(json.dumps(r) for r in rs) + "\n")
    a.run_dir = str(tmp_path / "zero")
    with pytest.raises(SystemExit, match="bytes"):
        ml.budget_cmd(a)


def test_report_mean_bytes_excludes_failed_visits(tmp_path, capsys):
    rows_file(tmp_path / "run", {("cloudflare", 0): ("pass", "pass"), ("cloudflare", 1): ("unknown", "unknown")}, rounds=1)
    ml.report_cmd(type("A", (), {"run_dir": str(tmp_path / "run")})())
    assert "mean 1000 over 2 measured visits" in capsys.readouterr().out


def test_the_version_gate():
    assert ml.version_problems_for({"S": "156.0.8078.48", "F": "156.0.8078.48"}, "156.0.8078.48", aa=False) == []
    assert ml.version_problems_for({"S": "157.0.8100.1", "F": "156.0.8078.48"}, "156.0.8078.48", aa=False)
    assert ml.version_problems_for({"S": "157.0.8100.1", "F": "157.0.8100.1"}, "156.0.8078.48", aa=True) == []


def test_resume_also_refuses_a_rebuilt_fork_or_an_edited_site_list():
    old = {"started": "T0", "rounds": 5, "flags": {"aa": False}, "versions": {"S": "1", "F": "2"}, "sites_per_vendor": {"cloudflare": 3}}
    same = {"rounds": 5, "started": "T1", "flags": {"aa": False}, "versions": {"S": "1", "F": "2"}, "sites_per_vendor": {"cloudflare": 3}}
    assert ml.resume_meta(old, same)["started"] == "T0"
    with pytest.raises(SystemExit, match="versions"):
        ml.resume_meta(old, {**same, "versions": {"S": "1", "F": "3"}})
    with pytest.raises(SystemExit, match="sites_per_vendor"):
        ml.resume_meta(old, {**same, "sites_per_vendor": {"cloudflare": 4}})


def test_a_missing_order_does_not_crash_the_report(tmp_path):
    rows_file(tmp_path / "run", {("cloudflare", i): ("pass", "challenge") for i in range(3)})
    rs = [json.loads(line) for line in (tmp_path / "run" / "results.jsonl").read_text().splitlines()]
    for r in rs:
        del r["order"]
    (tmp_path / "run" / "results.jsonl").write_text("\n".join(json.dumps(r) for r in rs) + "\n")
    assert ml.vendor_rows(tmp_path / "run", resamples=100)["cloudflare"]["d"] == 1.0


def test_scrub_prints_an_unmeasured_vendor_instead_of_refusing(tmp_path, terms):
    rows_file(tmp_path / "run", {("cloudflare", i): ("pass", "challenge") for i in range(3)} | {("datadome", i + 3): ("unknown", "unknown") for i in range(3)})
    assert ml.scrub_cmd(scrub_args(tmp_path)) == 0
    assert "| datadome |" in (tmp_path / "out" / "layer3-baseline.md").read_text() and "UNMEASURED" in (tmp_path / "out" / "layer3-baseline.md").read_text()


def test_a_gpu_crash_during_the_visit_makes_it_unmeasured(monkeypatch):
    import camoucrome
    import gpu_gate

    class Page:
        mouse = type("M", (), {"wheel": lambda self, *a: None})()

        def on(self, *a):
            pass

        def wait_for_timeout(self, _ms):
            pass

    class Ctx:
        pages = [Page()]

        def route(self, *a):
            pass

        def close(self):
            pass

    calls = []

    def check(n):
        calls.append(n)
        if len(calls) == 2:
            raise gpu_gate.Unmeasured("crashed")
    monkeypatch.setattr(camoucrome, "launch", lambda *a, **k: Ctx())
    monkeypatch.setattr(gpu_gate, "read_ctx", lambda ctx: 0)
    monkeypatch.setattr(gpu_gate, "check", check)
    monkeypatch.setattr(ml, "settle", lambda *a, **k: ({"outcome": "pass", "markers": [], "cookies": []}, False))
    monkeypatch.setattr(ml, "load", lambda *a: 200)
    a = ns(gpu_gate=True, headed=False, settle=1, dwell=0)
    arm = ns(ident=None, exe="x", args=[])
    with pytest.raises(gpu_gate.Unmeasured):
        ml.visit(None, arm, {"vendor": "cloudflare", "url": "u", "next_url": "n", "ok_marker": "m"}, None, a)
    assert len(calls) == 2


# ---- the whole pipeline, opt-in --------------------------------------------------------------------------------------
CHROME = os.environ.get("CAMOU_TEST_CHROME")
live = pytest.mark.skipif(not CHROME, reason="set CAMOU_TEST_CHROME to a Chrome executable")

CF_CHALLENGE = b'<html><head><title>Just a moment...</title></head><body><form id="challenge-form"></form>Checking your browser</body></html>'
PX_CHALLENGE = b'<html><head><title>x</title></head><body><div id="px-captcha"></div>Press &amp; Hold</body></html>'
HOME = b'<html><head><title>Home</title></head><body><main id="content">real content</main><img src="/pixel.png"></body></html>'


class Lab(http.server.ThreadingHTTPServer):
    """Serves a normal page, or a vendor's challenge page to a browser whose user agent says "Challenge"."""

    def __init__(self):
        self.hits = {"img": 0, "page": 0}
        lab = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.endswith(".png"):
                    lab.hits["img"] += 1
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.end_headers()
                    return
                lab.hits["page"] += 1
                challenged = "Challenge" in (self.headers.get("User-Agent") or "")
                body = (CF_CHALLENGE if "/cloudflare/" in self.path else PX_CHALLENGE) if challenged else HOME
                self.send_response(403 if challenged else 200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Set-Cookie", "__cf_bm=SENTINELVALUE; Path=/")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        super().__init__(("127.0.0.1", 0), H)
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def base(self):
        return f"http://127.0.0.1:{self.server_port}"


def run_lab(tmp_path, *extra):
    lab = Lab()
    sites = write_sites(tmp_path, base=lab.base, vendors=("cloudflare", "perimeterx"), per=1)
    code = ml.main(["run", "--out", str(tmp_path), "--rounds", "3", "--sites", sites, "--stock-exe", CHROME, "--fork-exe", CHROME,
                    "--no-identity", "--dwell", "0.2", "--settle", "1", "--min-gap", "0", *extra])
    lab.shutdown()
    run = next((tmp_path / "layer3").iterdir())
    return code, run, lab


@live
def test_a_planted_difference_is_found_end_to_end(tmp_path):
    code, run, lab = run_lab(tmp_path, "--plant=--user-agent=Challenge/1")
    assert code == 0
    got = ml.vendor_rows(run, resamples=500)
    for vendor in ("cloudflare", "perimeterx"):
        assert got[vendor]["d"] == 1.0, got[vendor]  # fork challenged in every round, stock in none
    assert lab.hits["img"] == 0, "images were not blocked"
    assert json.loads((run / "meta.json").read_text())["blocked"] == ["font", "image", "media"]


@live
def test_stock_against_stock_finds_no_difference_end_to_end(tmp_path):
    code, run, lab = run_lab(tmp_path, "--aa")
    assert code == 0
    got = ml.vendor_rows(run, resamples=500)
    assert all(v["d"] == 0 and v["rate_stock"] == 0 for v in got.values()), got
    rows = ml.read_results(run)
    assert len(rows) == 12 and {r["outcome"] for r in rows} == {"pass"}
    assert all(r["bytes"] > 0 for r in rows) and not any("cookie_values" in r for r in rows)
    assert "SENTINELVALUE" not in (run / "results.jsonl").read_text() and any("__cf_bm" in r["cookie_names"] for r in rows)
    assert lab.hits["img"] == 0


@pytest.mark.parametrize("ips,tag", [
    ({"S": "203.0.113.5", "F": "203.0.113.5"}, "same"),
    ({"S": "203.0.113.5", "F": "203.0.113.9"}, "differ"),
    ({"S": "203.0.113.5", "F": None}, "unread"),
    ({"S": None, "F": None}, "unread"),
])
def test_a_pair_on_two_exit_addresses_or_an_unread_one_is_unknown(ips, tag):
    rows = {"S": {"outcome": "pass", "bytes": 5}, "F": {"outcome": "challenge", "bytes": 7}}
    out = ml.pair_exit_ips(rows, ips)
    assert [r["ip_pair"] for r in out.values()] == [tag, tag]
    if tag == "same":
        assert [r["outcome"] for r in out.values()] == ["pass", "challenge"]
    else:
        assert all(r["outcome"] == "unknown" and r["error"] == "ip_" + tag for r in out.values())
    assert "203.0.113" not in json.dumps(out)


def _attempt(plan):
    """A fake attempt(k): plan[k] is the pair of exit addresses the arms got on try k."""
    def attempt(k):
        s, f = plan[min(k, len(plan) - 1)]
        return ({"S": {"outcome": "pass", "bytes": 10}, "F": {"outcome": "pass", "bytes": 20}}, {"S": s, "F": f})
    return attempt


def test_a_pair_on_two_addresses_is_retried_on_a_fresh_session_and_the_wasted_bytes_are_kept():
    rows = ml.run_pair_with_retries(_attempt([("a", "b"), ("a", "b"), ("c", "c")]), 2)
    assert [r["outcome"] for r in rows.values()] == ["pass", "pass"]
    assert [r["ip_pair"] for r in rows.values()] == ["same", "same"]
    assert [r["retries"] for r in rows.values()] == [2, 2]
    assert [r["retry_bytes"] for r in rows.values()] == [20, 40]  # two failed tries: 2 x 10 (S), 2 x 20 (F)


def test_a_pair_that_never_agrees_stops_after_the_retries_and_stays_unknown():
    calls = []
    plan = [("a", "b")]

    def attempt(k):
        calls.append(k)
        return _attempt(plan)(k)
    rows = ml.run_pair_with_retries(attempt, 2)
    assert calls == [0, 1, 2]
    assert all(r["outcome"] == "unknown" and r["error"] == "ip_differ" and r["retries"] == 2 for r in rows.values())


def test_a_pair_on_one_address_is_not_retried():
    calls = []

    def attempt(k):
        calls.append(k)
        return _attempt([("a", "a")])(k)
    rows = ml.run_pair_with_retries(attempt, 2)
    assert calls == [0] and [r["retries"] for r in rows.values()] == [0, 0]


def test_a_visit_costs_what_it_spent_on_retries_too():
    assert ml.visit_cost({"bytes": 5, "retry_bytes": 7}) == 12 and ml.visit_cost({"bytes": 5}) == 5


def test_the_default_round_count_is_twelve():
    assert ml.build_parser().parse_args(["run"]).rounds == 12


def test_seed_profile_writes_the_webrtc_pref_and_keeps_what_is_there(tmp_path):
    (tmp_path / "Default").mkdir()
    (tmp_path / "Default" / "Preferences").write_text(json.dumps({"webrtc": {"other": 1}, "x": 2}))
    ml.seed_profile(tmp_path)
    prefs = json.loads((tmp_path / "Default" / "Preferences").read_text())
    assert prefs["webrtc"] == {"other": 1, "ip_handling_policy": "disable_non_proxied_udp"} and prefs["x"] == 2


def test_every_arm_launches_on_a_profile_that_carries_the_webrtc_pref(monkeypatch):
    """--force-webrtc-ip-handling-policy is a no-op in //chrome (only the pref works), so stock gets the pref too."""
    import camoucrome
    import gpu_gate
    seen = []

    class Page:
        mouse = type("M", (), {"wheel": lambda self, *a: None})()

        def on(self, *a):
            pass

        def wait_for_timeout(self, _ms):
            pass

    class Ctx:
        pages = [Page()]

        def route(self, *a):
            pass

        def close(self):
            pass

    def launch(pw, exe, **k):
        f = pathlib.Path(k["user_data_dir"]) / "Default" / "Preferences"
        seen.append((json.loads(f.read_text())["webrtc"]["ip_handling_policy"], k["user_data_dir"]))
        return Ctx()
    monkeypatch.setattr(camoucrome, "launch", launch)
    monkeypatch.setattr(gpu_gate, "read_ctx", lambda ctx: 0)
    monkeypatch.setattr(ml, "settle", lambda *a, **k: ({"outcome": "pass", "markers": [], "cookies": []}, False))
    monkeypatch.setattr(ml, "load", lambda *a: 200)
    a = ns(gpu_gate=False, headed=False, settle=1, dwell=0, warm=False)
    for ident in (None, {"config": {}, "launch": {}}):  # stock, fork
        ml.visit(None, ns(ident=ident, exe="x", args=[]), {"vendor": "cloudflare", "url": "u", "next_url": "n", "ok_marker": "m"}, None, a)
    assert [v for v, _ in seen] == ["disable_non_proxied_udp"] * 2
    assert not any(pathlib.Path(d).exists() for _, d in seen)  # the temporary profile is removed afterwards


def test_a_webrtc_candidate_on_a_non_exit_address_is_a_leak_and_mdns_names_are_not():
    c = ["candidate:1 1 udp 2122 abcd-ef.local 5000 typ host", "candidate:2 1 udp 1686 203.0.113.9 5001 typ srflx raddr 0.0.0.0 rport 0",
         "candidate:3 1 tcp 1518 198.51.100.7 9 typ host tcptype active"]
    assert ml.webrtc_leaks(c, "198.51.100.7") == 1
    assert ml.webrtc_leaks([], "198.51.100.7") == 0


def test_a_leak_makes_the_pair_unknown_and_is_not_retried():
    calls = []

    def attempt(k):
        calls.append(k)
        return ({"S": {"outcome": "pass", "bytes": 1, "webrtc_leaks": 0}, "F": {"outcome": "pass", "bytes": 1, "webrtc_leaks": 2}},
                {"S": "a", "F": "a"})
    rows = ml.run_pair_with_retries(attempt, 2)
    assert calls == [0]
    assert all(r["outcome"] == "unknown" and r["error"] == "webrtc_leak" and r["ip_pair"] == "same" for r in rows.values())


# ---- why a visit read unknown ----------------------------------------------------------------------------------------
class NavTimeout(Exception):
    pass


def test_load_notes_the_navigation_exception_class_and_returns_no_status():
    page = type("P", (), {"goto": lambda self, url, **k: (_ for _ in ()).throw(NavTimeout("x"))})()
    note = {}
    assert ml.load(page, "https://a.example/", note) is None
    assert note == {"exc": "NavTimeout"}


def test_unknown_reason_has_only_the_class_status_length_and_a_host_bool():
    page = type("P", (), {"url": "https://b.example/challenge", "evaluate": lambda self, js: 7})()
    got = ml.unknown_reason(page, "https://a.example/start", 403, {"exc": "NavTimeout"})
    assert got == {"exc": "NavTimeout", "status": 403, "body_len": 7, "same_host": False}
    assert "example" not in json.dumps(got)
    same = ml.unknown_reason(page, "https://b.example/start", None, {})
    assert same == {"exc": None, "status": None, "body_len": 7, "same_host": True}


def test_unknown_reason_survives_a_page_that_cannot_be_read():
    def boom(self, js):
        raise RuntimeError("Execution context was destroyed")
    page = type("P", (), {"url": property(boom), "evaluate": boom})()
    assert ml.unknown_reason(page, "https://a.example/", None, {}) == {"exc": None, "status": None, "body_len": None, "same_host": None}


def _visit_with(monkeypatch, outcomes):
    import camoucrome
    import gpu_gate

    class Page:
        url = "https://a.example/"
        mouse = type("M", (), {"wheel": lambda self, *a: None})()

        def on(self, *a):
            pass

        def wait_for_timeout(self, _ms):
            pass

        def evaluate(self, js):
            return 5

    class Ctx:
        pages = [Page()]

        def route(self, *a):
            pass

        def close(self):
            pass
    monkeypatch.setattr(camoucrome, "launch", lambda *a, **k: Ctx())
    monkeypatch.setattr(gpu_gate, "read_ctx", lambda ctx: 0)
    it = iter(outcomes)
    monkeypatch.setattr(ml, "settle", lambda *a, **k: ({"outcome": next(it), "markers": [], "cookies": []}, False))
    monkeypatch.setattr(ml, "load", lambda *a: 200)
    a = ns(gpu_gate=False, headed=False, settle=1, dwell=0, warm=False)
    return ml.visit(None, ns(ident=None, exe="x", args=[]), {"vendor": "cloudflare", "url": "https://a.example/", "next_url": "https://a.example/n", "ok_marker": "m"}, None, a)


def test_a_row_with_an_unknown_stage_carries_a_reason_for_that_stage_only(monkeypatch):
    row = _visit_with(monkeypatch, ["unknown", "pass"])
    assert set(row["reason"]) == {"stage1"}
    assert row["reason"]["stage1"] == {"exc": None, "status": 200, "body_len": 5, "same_host": True}


def test_a_row_with_no_unknown_stage_has_no_reason(monkeypatch):
    assert "reason" not in _visit_with(monkeypatch, ["pass", "challenge"])


# ---- navigation errors and server errors are retried; the exit address has fallback echo services --------------------
def _unknown(reason):
    return {"outcome": "unknown", "bytes": 10, "reason": reason}


NAV_ERR = {"stage1": {"exc": "Error", "status": None, "body_len": 214, "same_host": False}}
HTTP_502 = {"stage1": {"exc": None, "status": 502, "body_len": 54, "same_host": True}}
HTTP_200_OTHER = {"stage1": {"exc": None, "status": 200, "body_len": 176, "same_host": False}}
BLANK = {"stage1": {"exc": None, "status": None, "body_len": 0, "same_host": True}}
HTTP_403 = {"stage1": {"exc": None, "status": 403, "body_len": 900, "same_host": True}}


@pytest.mark.parametrize("reason,retried", [(NAV_ERR, True), (HTTP_502, True), (HTTP_200_OTHER, False), (BLANK, False), (HTTP_403, False)])
def test_only_a_navigation_error_or_a_5xx_makes_a_pair_try_again(reason, retried):
    calls = []

    def attempt(k):
        calls.append(k)
        bad = _unknown(reason) if k == 0 else {"outcome": "pass", "bytes": 10}
        return ({"S": bad, "F": {"outcome": "pass", "bytes": 20}}, {"S": "a", "F": "a"})
    rows = ml.run_pair_with_retries(attempt, 2)
    assert calls == ([0, 1] if retried else [0])
    if retried:
        assert [r["outcome"] for r in rows.values()] == ["pass", "pass"]
        assert [r["retry_bytes"] for r in rows.values()] == [10, 20]  # the failed try is charged to both arms


def test_a_pair_that_keeps_failing_to_navigate_stops_at_the_cap_and_stays_unknown():
    calls = []

    def attempt(k):
        calls.append(k)
        return ({"S": _unknown(NAV_ERR), "F": {"outcome": "pass", "bytes": 20}}, {"S": "a", "F": "a"})
    rows = ml.run_pair_with_retries(attempt, 2)
    assert calls == [0, 1, 2] and rows["S"]["outcome"] == "unknown" and rows["S"]["retries"] == 2


def test_a_navigation_error_is_not_retried_without_a_proxy():
    calls = []

    def attempt(k):
        calls.append(k)
        return ({"S": _unknown(NAV_ERR), "F": {"outcome": "pass", "bytes": 20}}, {"S": "direct", "F": "direct"})
    ml.run_pair_with_retries(attempt, 2, check=False)
    assert calls == [0]


class EchoPage:
    """goto raises for a host listed in `down`; the body is what `bodies` says for the last host visited."""
    def __init__(self, down=(), bodies=None):
        self.down, self.bodies, self.visited = set(down), bodies or {}, []

    def goto(self, url, **k):
        self.visited.append(url)
        if url in self.down:
            raise RuntimeError("net::ERR_TIMED_OUT")

    def inner_text(self, _sel):
        return self.bodies.get(self.visited[-1], "198.51.100.7\n")


def test_the_exit_address_is_read_from_the_next_echo_service_when_one_fails():
    assert ml.ECHO_URLS == ("https://api.ipify.org", "https://checkip.amazonaws.com", "https://icanhazip.com")
    page = EchoPage(down={ml.ECHO_URLS[0]})
    assert ml.read_exit_ip(page) == "198.51.100.7" and page.visited == list(ml.ECHO_URLS[:2])
    page = EchoPage(down=set(ml.ECHO_URLS[:2]))
    assert ml.read_exit_ip(page) == "198.51.100.7" and page.visited == list(ml.ECHO_URLS)
    page = EchoPage(bodies={ml.ECHO_URLS[0]: "<html>blocked</html>"})
    assert ml.read_exit_ip(page) == "198.51.100.7" and len(page.visited) == 2  # a body that is no address is a failure too


def test_the_first_echo_service_that_answers_is_the_only_one_asked_and_all_failing_is_unread():
    page = EchoPage()
    ml.read_exit_ip(page)
    assert page.visited == [ml.ECHO_URLS[0]]
    page = EchoPage(down=set(ml.ECHO_URLS))
    assert ml.read_exit_ip(page) is None and page.visited == list(ml.ECHO_URLS)


def test_no_row_names_an_echo_service_or_an_address():
    rows = {"S": {"outcome": "pass", "bytes": 5}, "F": {"outcome": "pass", "bytes": 7}}
    text = json.dumps(ml.pair_exit_ips(rows, {"S": "198.51.100.7", "F": "198.51.100.7"}))
    assert "198.51.100" not in text and not any(u.split("//")[1] in text for u in ml.ECHO_URLS)
