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


def test_both_arms_get_the_webrtc_policy_when_there_is_a_proxy_and_the_same_extra_arguments():
    cfg = {"server": "http://p.example:1", "username_template": "u-{session}", "password": "pw"}
    assert ml.common_args(cfg, ["--x"]) == [ml.WEBRTC_POLICY, "--x"]
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
                lines.append(json.dumps({"round": r, "site": site, "vendor": vendor, "arm": arm, "order": "SF", "outcome": out, "bytes": 1000}))
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
    assert ml.budget_cmd(args(12, 20, 5.0)) == 0  # 1000 B x 12 x 20 x 2 x 4.5 = 2.2 MB
    assert ml.budget_cmd(args(12, 20, 0.000001)) == 2
    assert "OVER" in capsys.readouterr().err


def test_scrub_writes_only_the_vendor_table_and_refuses_thin_vendors(tmp_path):
    rows_file(tmp_path / "run", {("cloudflare", i): ("pass", "challenge") for i in range(3)})
    a = type("A", (), {"run_dir": str(tmp_path / "run"), "out_dir": str(tmp_path / "out")})()
    assert ml.scrub_cmd(a) == 0
    text = (tmp_path / "out" / "layer3-baseline.md").read_text()
    assert "| cloudflare |" in text and "blocked in both arms" in text and "127.0.0.1" not in text
    meta = json.loads((tmp_path / "run" / "meta.json").read_text())
    meta["sites_per_vendor"]["datadome"] = 2
    (tmp_path / "run" / "meta.json").write_text(json.dumps(meta))
    with pytest.raises(SystemExit, match="fewer than 3 sites"):
        ml.scrub_cmd(a)


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
    assert lab.hits["img"] == 0
