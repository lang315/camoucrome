"""step2_rows and oracle_rules without a browser (roadmap step 2)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_oracle_rules_shared():
    import oracle_rules
    assert "screen.width" in oracle_rules.SHAPE_ONLY and "audioFp" in oracle_rules.SHAPE_ONLY
    assert oracle_rules.flatten({"a": {"b": 1, "c": [2]}, "d": None}) == {"a.b": 1, "a.c": [2], "d": None}


import json
import pathlib

import pytest

import step2_rows as r

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "step2"


def test_equal_rows_are_not_listed():
    assert r.label_rows({"x": 1}, {"x": 1}) == []


def test_unknown_difference_is_unexpected():
    assert r.label_rows({"oracle.nav.platform": "Win32"}, {"oracle.nav.platform": "Linux"}) == [
        ("oracle.nav.platform", "Win32", "Linux", "unexpected", "")]


def test_shape_only_leaf_value_difference_is_expected_same_type():
    [(name, _, _, label, reason)] = r.label_rows({"oracle.screen.width": 1920}, {"oracle.screen.width": 1536})
    assert (name, label) == ("oracle.screen.width", "expected") and reason


def test_shape_only_leaf_type_change_is_unexpected():
    [(_, _, _, label, _)] = r.label_rows({"oracle.screen.width": 1920}, {"oracle.screen.width": "1536"})
    assert label == "unexpected"


def test_shape_only_prefix_does_not_swallow_a_longer_name():
    # SHAPE_ONLY has nav.language; nav.languagesX is a different leaf.
    [(_, _, _, label, _)] = r.label_rows({"oracle.nav.languagesX": 1}, {"oracle.nav.languagesX": 2})
    assert label == "unexpected"


def test_absent_on_one_side_is_unexpected():
    [(_, c, f, label, _)] = r.label_rows({"oracle.nav.share": "function"}, {})
    assert (c, f, label) == ("function", "<absent>", "unexpected")


def test_volatile_row():
    [(_, _, _, label, _)] = r.label_rows({"net.ja3": "a"}, {"net.ja3": "b"})
    assert label == "volatile"


def test_unmeasured_wins():
    [(_, _, _, label, _)] = r.label_rows({"det.pixelscan": "UNMEASURED"}, {"det.pixelscan.x": 1})[:1]
    assert label == "unmeasured"


def test_argv_parity_allows_profile_and_accept_lang_only():
    c = ["chrome.exe", "--no-first-run", "--user-data-dir=C:\\a", "--remote-debugging-pipe"]
    f = ["chrome.exe", "--no-first-run", "--user-data-dir=C:\\b", "--remote-debugging-pipe", "--accept-lang=en-US"]
    assert r.argv_problems(c, f) == []


def test_argv_parity_allows_identity_window_and_dpr():
    c = ["chrome.exe", "--no-first-run"]
    f = ["chrome.exe", "--no-first-run", "--window-size=1536,816", "--force-device-scale-factor=1.25"]
    assert r.argv_problems(c, f) == []


def test_argv_parity_allows_window_position():
    f = ["chrome.exe", "--no-first-run", "--window-position=7,25"]
    assert r.argv_problems(["chrome.exe", "--no-first-run"], f) == []


def test_argv_parity_flags_extra_arg():
    c = ["chrome.exe", "--no-first-run"]
    f = ["chrome.exe", "--no-first-run", "--use-angle=swiftshader"]
    assert r.argv_problems(c, f) == ["fork only: --use-angle=swiftshader"]


def test_argv_parity_refuses_unread_argv():
    assert r.argv_problems([], ["chrome.exe"]) == ["argv not read: control=0 fork=1 elements"]


def test_version_precondition():
    assert r.version_problems({"control": "157.0.8103.15", "fork": "157.0.8103.15"}, "157.0.8103.15") == []
    assert r.version_problems({"control": "156.0.1.1", "fork": "157.0.8103.15"}, "157.0.8103.15") == [
        "control is 156.0.1.1, the pin is 157.0.8103.15"]


def test_network_rows_from_fixture():
    rows = r.network_rows(json.loads((FIX / "peet.json").read_text()))
    assert set(rows) == {"net.http_version", "net.ja4", "net.ja3", "net.akamai", "net.h2_order", "net.user_agent"}
    assert rows["net.ja4"] and rows["net.akamai"]
    assert rows["net.h2_order"][0].startswith(":")  # pseudo-headers first, names only


def test_stability_rows():
    rows = r.stability_rows({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4})
    assert rows == {"stab.compared": 3, "stab.changed": ["b", "c"]}


def test_link_rows():
    assert r.link_rows({"a": 1, "b": 2}, {"a": 1, "b": 3}) == {"link.total": 2, "link.shared": ["a"]}


def test_link_rows_n_shares_only_what_every_profile_shares():
    reps = [{"a": 1, "b": 2, "c": 9}, {"a": 1, "b": 2, "c": 8}, {"a": 1, "b": 3, "c": 9}]
    assert r.link_rows_n(reps) == {"link.total": 3, "link.shared": ["a"], "link.values": {"a": 1}}


def test_link_rows_n_two_reports_equals_link_rows():
    a, b = {"a": 1, "b": 2}, {"a": 1, "b": 3}
    assert {k: v for k, v in r.link_rows_n([a, b]).items() if k != "link.values"} == r.link_rows(a, b)


def test_link_rows_n_leaf_missing_from_one_report_is_not_shared():
    assert r.link_rows_n([{"a": 1, "b": 2}, {"a": 1}, {"a": 1, "b": 2}])["link.shared"] == ["a"]


def test_unexplained_honours_exact_and_prefix_constants():
    shared = ["ua.version", "webGl.renderer", "intl.locale.x", "fonts.list"]
    consts = {"ua.version": "same Chrome", "intl.": "ICU data ships with Chrome"}
    assert r.unexplained(shared, consts) == ["fonts.list", "webGl.renderer"]


def test_unexplained_empty_allowlist_explains_nothing():
    assert r.unexplained(["b", "a"], {}) == ["a", "b"]


def test_machine_constants_file_shape():
    import json
    doc = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "settings", "machine_constants.json")))
    assert isinstance(doc["leaves"], dict) and all(isinstance(v, str) and v for v in doc["leaves"].values())


def test_parse_tabbed():
    assert r.parse_tabbed("Test\tResult\nWebDriver (New)\tmissing (passed)\nplain line\n") == {
        "Test": "Result", "WebDriver (New)": "missing (passed)"}


def test_parse_colon_keeps_first_and_skips_long_keys():
    text = "WebGL: ANGLE (Intel)\nWebGL: second\n" + "x" * 50 + ": no\nempty:\n"
    assert r.parse_colon(text) == {"WebGL": "ANGLE (Intel)"}


def test_line_diff_is_a_multiset_diff():
    assert r.line_diff("a\nb\nb\n", "b\nc\n") == (["a", "b"], ["c"])


def test_compare_runs_skips_volatile_and_reports_the_rest():
    a = {"rows": {"network": {"fork": {"headless": {"net.ja3": "1", "net.ja4": "x"}}}}}
    b = {"rows": {"network": {"fork": {"headless": {"net.ja3": "2", "net.ja4": "y"}}}}}
    assert r.compare_runs(a, b) == [("network/fork/headless/net.ja4", "x", "y")]


def test_render_tables_labels_and_unmeasured():
    doc = {"run": "t", "versions": {"control": "1", "fork": "1"}, "flags": {}, "errors": {"noise/fork/headed": "boom"},
           "rows": {"noise": {"control": {"headless": {"noise.canvas2d": 1}, "headed": {"noise.canvas2d": 1}},
                              "fork": {"headless": {"noise.canvas2d": 7}, "headed": None}}}}
    md = r.render_tables(doc, {})
    assert "| noise.canvas2d | 1 | 7 | unexpected |" in md
    assert "## noise / headed" in md and "UNMEASURED: boom" in md


def test_render_tables_lists_unexplained_shared_leaves():
    cell = {"link.total": 3, "link.shared": ["a", "webGl.renderer"], "link.unexplained": ["webGl.renderer"],
            "link.unexplained_raw": 2, "link.unexplained_net": 1, "link.values": {"webGl.renderer": "SECRET-VALUE"}}
    doc = {"run": "t", "versions": {"control": "1", "fork": "1"}, "flags": {}, "errors": {},
           "rows": {"linkability": {"control": {"headless": dict(cell)}, "fork": {"headless": dict(cell)}}}}
    md = r.render_tables(doc, {})
    assert "that no machine constant explains (raw 2, net 1)" in md and "`webGl.renderer`" in md
    assert "SECRET-VALUE" not in md


def test_drop_link_values_removes_values_from_every_cell():
    doc = {"rows": {"linkability": {"fork": {"headed": {"link.values": {"a": 1}, "link.shared": ["a"]}}, "control": {"headed": None}}}}
    out = r.drop_link_values(doc)
    assert out["rows"]["linkability"]["fork"]["headed"] == {"link.shared": ["a"]}
    assert "link.values" in doc["rows"]["linkability"]["fork"]["headed"]


# Calibration from the 2026-10-04 host runs (docs/superpowers/measurements/2026-10-step2-baseline.md).
@pytest.mark.parametrize("name", ["oracle.err.stack", "oracle.navConnection.downlink", "oracle.navConnection.rtt",
                                  "oracle.voices", "oracle.mediaDevices.groupIds"])
def test_measured_volatile_rows(name):
    assert r.label_rows({name: 1}, {name: 2})[0][3] == "volatile"


@pytest.mark.parametrize("name", ["oracle.nav.webdriver", "oracle.media.(pointer: fine)", "oracle.media.(pointer: none)",
                                  "oracle.media.(hover: hover)", "oracle.media.(any-pointer: fine)",
                                  "oracle.media.(any-hover: hover)", "oracle.ua", "oracle.nav.appVersion"])
def test_designed_deviations_are_expected(name):
    [(_, _, _, label, reason)] = r.label_rows({name: True}, {name: False})
    assert label == "expected" and reason


def test_stability_and_link_skip_volatile_leaves():
    a, b = {"voices": 1, "audioFp": "x", "navConnection.rtt": 50}, {"voices": 2, "audioFp": "y", "navConnection.rtt": 100}
    assert r.stability_rows(a, b) == {"stab.compared": 3, "stab.changed": ["audioFp"]}
    assert r.link_rows({"voices": 1, "k": 1}, {"voices": 1, "k": 1}) == {"link.total": 2, "link.shared": ["k"]}


@pytest.mark.parametrize("name", ["det.creepjs.candidate", "det.creepjs.rtt", "det.creepjs.stack", "det.creepjs.trap",
                                  "det.creepjs.type & base ip"])
def test_measured_volatile_detector_rows(name):
    assert r.label_rows({name: "a"}, {name: "b"})[0][3] == "volatile"


@pytest.mark.parametrize("line", ["1582.20ms", "2143.90 ms", "WebRTC9ce33afb", "candidate:436789896 1 udp 1677729535 x",
                                  "rtt: 100, downlink: 1.55", "stack: 17790", "trap: 0.71", "type & base ip: 2513029441",
                                  '"depth": 13420,', "Sun Oct 04 2026 15:14:51 GMT+0000 (Coordinated Universal Time)",
                                  "10 22:25", "104.22.67.926 more", "D78AD52E", "Bot detection tools", "Ad", "0"])
def test_measured_volatile_lines_are_dropped(line):
    assert r.line_diff(line + "\n", "") == ([], [])


def test_ad_suffix_is_stripped_and_the_value_kept():
    # BrowserScan's ad unit appends a rotating link text to the value line before it.
    assert r.line_diff("springfieldTry Web Filters\n", "springfieldPrivacy Issues\n") == ([], [])
    assert r.line_diff("Chrome Headless 157.0.8103.15 DetectionKernel detection tool\n",
                       "Chrome 157.0.8103.15 DetectionCanvas fingerprint detection\n") == (
        ["Chrome Headless 157.0.8103.15 Detection"], ["Chrome 157.0.8103.15 Detection"])


def test_a_real_value_line_survives():
    assert r.line_diff("Your browser environment appears to be controlled by a robot.\n", "") == (
        ["Your browser environment appears to be controlled by a robot."], [])


@pytest.mark.parametrize("name", ["det.creepjs.....avail", "det.creepjs....screen", "det.creepjs.screen query",
                                  "det.creepjs.cores", "det.creepjs.lang", "det.creepjs.FP ID", "det.creepjs.Fuzzy",
                                  "det.creepjs.level", "det.creepjs.sum", "det.sannysoft.screen.width",
                                  "det.sannysoft.navigator.userAgent", "det.sannysoft.CHR_MEMORY"])
def test_identity_driven_detector_rows_are_expected(name):
    [(_, _, _, label, reason)] = r.label_rows({name: "a"}, {name: "b"})
    assert label == "expected" and reason


def test_remote_voices_stay_unexpected():
    # stock lists 19 remote voices, the fork's claim none: a finding, not the identity's by design
    assert r.label_rows({"det.creepjs.remote (19)": "x"}, {})[0][3] == "unexpected"


def test_second_null_pair_residue_is_dropped():
    # 20261004-153840-null: BrowserScan ad phrases and CreepJS status lines that flipped between two stock loads
    for line in ("DNS leak test", "Statusb03caef9", "0.10000038146972656", "1"):
        assert r.line_diff(line + "\n", "") == ([], [])
    assert r.line_diff("1024x768Gyroscope sensor tester\n", "1024x768\n") == ([], [])
    assert r.line_diff("springfieldOnline privacy guide\n", "springfield\n") == ([], [])


# step2b: synthetic fixtures in the shape each page printed on 2026-10-13; no host value.
REBROWSER = (
    "Test name\tTime since load\tNotes\n"
    "⚪️ dummyFn\t0.2 ms\tCall window.dummyFn() to test if you can access main world objects.\n"
    "\U0001f7e2 runtimeEnableLeak\t1.2 ms\tNo leak detected.\n"
    "\U0001f534 navigatorWebdriver\t2 ms\tnavigator.webdriver = true indicates that browser is automated.\n"
    "typeof navigator.webdriver = boolean; navigator.webdriver = true\n")


def test_rebrowser_status_per_test():
    assert r.parse_rebrowser(REBROWSER) == {
        "dummyFn": "not triggered", "runtimeEnableLeak": "pass", "navigatorWebdriver": "fail"}


DBI = """You are a bot!
Raw detection details
{
  "isBot": true,
  "details": {
    "hasBotUserAgent": true,
    "isPlaywright": false,
    "isAutomatedWithCDP": false
  }
}
Detection signals explained

hasBotUserAgent: True if the User-Agent string matches known bot patterns.
isPlaywright: True if Playwright-specific global variables are present.
"""


def test_dbi_reads_only_the_json_booleans():
    assert r.parse_dbi(DBI) == {"isBot": True, "hasBotUserAgent": True, "isPlaywright": False, "isAutomatedWithCDP": False}


INCOLUMITAS = """{
  "puppeteerEvaluationScript": "OK",
  "webdriverPresent": "FAIL",
  "connectionRTT": "OK"
}
Old Bot Detection Tests
{
    "webDriver": "FAIL",
    "WEBDRIVER": "FAIL",
    "connectionRTT": "FAIL"
}
"""


def test_incolumitas_first_occurrence_wins_and_case_matters():
    got = r.parse_incolumitas(INCOLUMITAS)
    assert got == {"puppeteerEvaluationScript": "OK", "webdriverPresent": "FAIL", "connectionRTT": "OK",
                   "webDriver": "FAIL", "WEBDRIVER": "FAIL"}


FP_PRO = ("Your Visitor ID is \n\nABCDEFGHIJ0123456789\nBrowser\t\nHeadlessChrome 154.0.0\n\n"
          "IP Address\t\n203.0.113.7\n\nGeolocation\nSomewhere City, Region\n\t\n"
          "Incognito Mode\t\nNot detected\n\nBot\t\nYou are a bad bot (type: headless_chrome)\n\n"
          "VPN\t\nNot detected\n\nSuspect Score\t\n11\n\n"
          "VPN (Mobile)\tAvailable in native iOS and Android SDKs\nBot detection\n")


def test_fingerprint_pro_named_signals_only():
    got = r.parse_fingerprint_pro(FP_PRO)
    assert got == {"Incognito Mode": "Not detected", "Bot": "You are a bad bot (type: headless_chrome)",
                   "VPN": "Not detected", "Suspect Score": "11"}


def test_blocked_names_the_cloudflare_interstitial():
    assert r.blocked("whoer.net\nPerforming security verification\nRay ID: x") == "cloudflare challenge"
    assert r.blocked("Antibot\nUser Agent (Old)") == "no"


@pytest.mark.parametrize("raw,want", [
    ("ip_address: \"203.0.113.7\"", "ip_address: \"<ip>\""),
    ("peer 203.0.113.7:443 up", "peer <ip>:443 up"),
    ("v6 [2001:db8::1]:443", "v6 [<ip6>]:443"),
    ("at 10.7623, 106.6602 now", "at <coord> now"),
    ("HeadlessChrome/157.0.8103.15 Safari/537.36", "HeadlessChrome/157.0.8103.15 Safari/537.36"),
    ("at 10:00:00 on 2026-10-13T17:15:42.195Z", "at 10:00:00 on 2026-10-13T17:15:42.195Z"),
    ("mac aa:bb:cc:dd:ee:ff", "mac aa:bb:cc:dd:ee:ff"),
    ("Somewhere City, Region (SC), Land", "<city>, <region> (SC), <country>"),
])
def test_scrub(raw, want):
    geo = {"<city>": ["Somewhere City"], "<region>": ["Region"], "<country>": ["Land"]}
    assert r.scrub(raw, geo) == want


def test_scrub_dms_coordinates_and_geo_case():
    # BrowserScan prints degrees-minutes-seconds and a lower-case city (step2b null runs, 2026-10-13).
    geo = {"<city>": ["Somewhere City"]}
    assert r.scrub("12°34′0.56000″E", geo) == "<coord>"
    assert r.scrub("somewhere cityOnline privacy security", geo) == "<city>Online privacy security"


# step2b null runs 20261013-143709-null / -150324-null (stock against stock): lines that changed.
@pytest.mark.parametrize("line", [
    "downlink : 1.35", "rtt\t100", "Downlink\t1.75", "effectiveType : 3g", "Connection Rtt\tConnection-rtt: 100",
    "DateTimeFormat\tTuesday, October 13, 2026 at 10:06:36 PM Central Daylight Time", "toLocaleString\t10/13/2026, 9:40:32 PM",
    "13 hours ago", "1791902611717", "2026-10-13T14:43:31.560Z",
    "0x1A1A", "JA3\t110d039670ab65feea9580aa5f67e249", "JA4_o\tt13d1517h2_acb858a92679_15f8eb733a2a",
    "config_id\t166", "payload_length\t144",
    'event_id: "1791902627741.WwICUm"', "last_seen_at: 1791902627758", "1 IP, 3 Linked IDs in the past 24 hours",
    "1_hour: 4", "24_hours: 7", "Last Seen\tUnknown", "proxy_ml_score: 0.273", "tampering_ml_score: 0.5616",
    "virtual_machine_ml_score: 0.17", "vpn_ml_score: 0.046", "score: 0.99", "visitor_found: true",
    '"ip_checksum": 21267,', '"ip_id": 61889,', '"cHeight": 5693,', '"num_fingerprints": 2,', '"src_port": 32902,',
    '"tcp_checksum": 15309,', '"tcp_seq": 1262858357,', '"webSocketSupportTimeout": true', '"connectionRTT": "OK",',
    "\U0001f7e2 viewport\t19 ms\tViewport is different from default values used in automation libraries.",
    "Time Elapse\tTime elapsed to close alert: 13 (< 30)", "Ray ID: a49f2e295889603a",
    "1034.8", "+485", "0422b3a2", "3g", "true",
    "Collecting Data…", "Your Browser Fingerprint is scanning…", "Your Browser Fingerprint is inconsistent",
    "Masking detected", "No masking detected", "Scroll Down for More Info", "Restart", "How to Fix it?",
    "Best antidetect browsers", "Detection", "Bot detection service", "Browser fingerprinting tools",
    "NodeMaven - buy a proxy, get a browser. WHO35 - 35% discount.", "High-quality aged accounts store. Trusted since 2023.",
    "AccsBulk: Buy Social Media & Email Accounts In Bulk. Aged, Verified, Instant", "Open", "Try",
])
def test_step2b_null_run_lines_are_volatile(line):
    assert r.line_diff(line + "\n", "") == ([], [])


def test_browserscan_ad_suffixes_seen_in_step2b():
    for ad in ("Secure Networks", "Online privacy security", "Protect Privacy"):
        assert r.line_diff("springfield" + ad + "\n", "springfield\n") == ([], [])


@pytest.mark.parametrize("row", ["det.detect_headless.Time Elapse", "det.detect_headless.Connection Rtt",
                                 "det.incolumitas.connectionRTT"])
def test_step2b_null_run_rows_are_volatile(row):
    assert r.label_rows({row: "a"}, {row: "b"})[0][3] == "volatile"


def test_compare_skips_a_site_unmeasured_in_either_run():
    # Null run 2 lost rebrowser in one cell (the page did not load or settle): not a value disagreement.
    a = {"rows": {"detectors": {"fork": {"headless": {"det.rebrowser": "ok", "det.rebrowser.viewport": "pass",
                                                       "det.sannysoft": "ok", "det.sannysoft.x": "1"}}}}}
    b = {"rows": {"detectors": {"fork": {"headless": {"det.rebrowser": "UNMEASURED",
                                                       "det.sannysoft": "ok", "det.sannysoft.x": "2"}}}}}
    assert r.compare_runs(a, b) == [("detectors/fork/headless/det.sannysoft.x", "1", "2")]
    assert r.unmeasured_sites(a, b) == ["b: detectors/fork/headless/det.rebrowser"]


def test_a_labelled_identity_line_is_not_volatile():
    # The calibration must not swallow a value the fork changes on purpose.
    assert r.line_diff("hardwareConcurrency\t16\n", "hardwareConcurrency\t12\n") == (["hardwareConcurrency\t16"], ["hardwareConcurrency\t12"])


@pytest.mark.parametrize("raw,want", [
    ("Your IP is 203.0.113.5.", "Your IP is <ip>."),            # final review: a sentence's full stop
    ("IP:203.0.113.5", "IP:<ip>"), ("Address:203.0.113.5", "Address:<ip>"),
    ("x 2001:db8::1.", "x <ip6>."),
    ("Chrome/154.0.0.0 Safari/537.36", "Chrome/154.0.0.0 Safari/537.36"),  # a reduced UA version, not an address
    ("Chrome 154.0.0.0 on Windows", "Chrome 154.0.0.0 on Windows"),
])
def test_scrub_final_review_cases(raw, want):
    assert r.scrub(raw, {}) == want


def test_compare_exits_nonzero_when_it_skipped_a_cell(tmp_path):
    import measure_step2 as m
    for name, site in (("a", "ok"), ("b", "UNMEASURED")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "rows.json").write_text(json.dumps(
            {"rows": {"detectors": {"fork": {"headless": {"det.rebrowser": site}}}}}), encoding="utf-8")
    assert m.main(["compare", str(tmp_path / "a"), str(tmp_path / "b")]) == 2


def test_a_gate_read_that_raises_is_unmeasured_not_an_error():
    import gpu_gate

    class Ctx:
        def new_page(self):
            raise RuntimeError("target closed")
    assert gpu_gate.read_ctx(Ctx()) is None


def test_scrub_an_address_glued_to_a_digit():
    # whoer.net prints an edge address with a digit glued on ("203.0.113.1922  Singapore", step2b fork run 1).
    assert r.scrub("203.0.113.1922  Singapore", {}) == "<ip>  Singapore"
    assert r.scrub("Chrome 157.0.8103.15 on Windows", {}) == "Chrome 157.0.8103.15 on Windows"


# step2b fork run 20261013-161750: rows the identity or SP2 explain.
@pytest.mark.parametrize("row,label", [
    ("det.dbi_bot.isBot", "expected"), ("det.dbi_bot.hasWebdriverTrue", "expected"),
    ("det.dbi_bot.hasWebdriverInFrameTrue", "expected"), ("det.dbi_bot.hasBotUserAgent", "expected"),
    ("det.incolumitas.webDriver", "expected"), ("det.incolumitas.webdriverPresent", "expected"),
    ("det.incolumitas.userAgent", "expected"), ("det.incolumitas.HEADCHR_UA", "expected"),
    ("det.incolumitas.CHR_MEMORY", "expected"), ("det.rebrowser.navigatorWebdriver", "expected"),
    ("det.detect_headless.Webdriver", "expected"), ("det.detect_headless.Languages", "expected"),
    ("det.detect_headless.Outer dimensions", "expected"), ("det.detect_headless.User Agent", "expected"),
    ("det.detect_headless.App Version", "expected"), ("det.fingerprint_pro.Bot", "expected"),
    ("det.fingerprint_pro.VPN", "expected"), ("det.fingerprint_pro.Suspect Score", "expected"),
    ("det.fingerprint_pro.High-Activity Device", "volatile"), ("det.creepjs.images", "expected"),
    ("det.creepjs.0% headless", "expected"), ("det.creepjs.31% like headless", "expected"),
    ("det.whoer.blocked", "expected"), ("oracle.audio.sampleRate", "expected"),
    ("det.fingerprint_pro.Browser Tampering", "unexpected"), ("det.creepjs.remote (0)", "unexpected"),
])
def test_step2b_fork_rows_are_labelled(row, label):
    assert r.label_rows({row: "a"}, {row: "b"})[0][3] == label


def test_scrub_walks_rows():
    doc = {"rows": {"x": {"control": {"headed": {"net.ip": "203.0.113.7", "n": 3}}}}}
    assert r.scrub(doc, {}) == {"rows": {"x": {"control": {"headed": {"net.ip": "<ip>", "n": 3}}}}}


def test_verdict_table_prints_every_cell_even_when_equal():
    cell = {"det.rebrowser": "ok", "det.rebrowser.navigatorWebdriver": "fail", "det.rebrowser.blocked": "no",
            "det.sannysoft": "ok", "det.sannysoft.blocked": "no", "det.sannysoft.WEBDRIVER": "x"}
    doc = {"rows": {"detectors": {"control": {"headed": cell, "headless": None},
                                  "fork": {"headed": cell, "headless": {"det.rebrowser": "UNMEASURED"}}}}}
    out = "\n".join(r.verdict_table(doc))
    assert "| det.rebrowser.navigatorWebdriver | \"fail\" | \"fail\" | UNMEASURED | UNMEASURED |" in out
    assert "| det.sannysoft.blocked | \"no\" | \"no\" | UNMEASURED | \"<absent>\" |" in out
    assert "WEBDRIVER" not in out  # a key/value row of a non-verdict site is not a verdict


def test_detectors_are_the_twenty_live_sites():
    import measure_step2 as m
    assert len(m.DETECTORS) == 20
    assert all("." not in name for name in m.DETECTORS)  # label_rows finds a site from the first two dotted parts
    assert all(url.startswith("https://") for url in m.DETECTORS.values())
    for dropped in ("brotector", "botd", "areyouheadless", "turnstile"):
        assert dropped not in m.DETECTORS


def test_a_gated_detector_launch_leaves_no_text(tmp_path, monkeypatch):
    import argparse
    import contextlib
    import gpu_gate
    import measure_step2 as m

    class Page:
        def goto(self, *a, **k):
            pass

        def screenshot(self, path, **k):
            open(path, "wb").write(b"png")

    @contextlib.contextmanager
    def crashed(pw, arm, mode, **k):
        yield type("Ctx", (), {"pages": [Page()]})()
        raise gpu_gate.GpuCrashed(1)

    monkeypatch.setattr(m, "opened", crashed)
    monkeypatch.setattr(m, "settle", lambda page: "some text")
    monkeypatch.setattr(m, "DETECTORS", {"sannysoft": "https://bot.sannysoft.com/"})
    (tmp_path / "raw").mkdir()
    run = argparse.Namespace(dir=tmp_path)
    out = m.probe_detectors(None, m.Arm("fork", "x", None), "headless", run)
    assert out == {"det.sannysoft": "UNMEASURED", "det.sannysoft.gpu_crash": 1}
    assert list((tmp_path / "raw").iterdir()) == []


def test_argv_read_survives_a_gpu_crash(monkeypatch):
    # The argv precondition does not depend on the GPU process: a crash there must not abort
    # the run before any probe (seen 2026-10-13 in the session-0 RED: a traceback, no rows).
    import contextlib
    import sys
    import types
    import gpu_gate
    import measure_step2 as m

    class Page:
        def goto(self, *a, **k):
            pass

    @contextlib.contextmanager
    def crashed(pw, arm, mode, **k):
        yield type("Ctx", (), {"pages": [Page()]})()
        raise gpu_gate.GpuCrashed(1)

    monkeypatch.setattr(m, "opened", crashed)
    monkeypatch.setitem(sys.modules, "camoucrome.probe", types.SimpleNamespace(browser_argv=lambda exe: [exe, "--x"]))
    assert m.argv_of(None, m.Arm("fork", "chrome.exe", None)) == ["chrome.exe", "--x"]


def test_measure_step2_identity_passes_host_draw_inputs(monkeypatch):
    import measure_step2 as m
    seen = {}

    class G:
        @staticmethod
        def generate(os, **kw):
            seen.update(kw)
            return {}
    monkeypatch.setitem(sys.modules, "camoucrome.gen", G)
    monkeypatch.setattr(m, "HOST_DRAW", {"host_renderer": "R", "host_families": {"F"}})
    m.identity(3)
    assert seen == {"seed": 3, "host_renderer": "R", "host_families": {"F"}}
    seen.clear()
    monkeypatch.setattr(m, "HOST_DRAW", {})
    m.identity(3)
    assert seen == {"seed": 3}


def _fake_host(monkeypatch, display, pv):
    import types
    monkeypatch.syspath_prepend(str(pathlib.Path(__file__).resolve().parents[1] / "client" / "python"))
    import camoucrome
    probe = types.SimpleNamespace(host_renderer=lambda e: "R", host_display=lambda e: display,
                                  host_platform_version=lambda e: pv)
    fonts = types.SimpleNamespace(families=lambda: {"F"})
    for name, mod in (("probe", probe), ("hostfonts", fonts)):
        monkeypatch.setitem(sys.modules, f"camoucrome.{name}", mod)
        monkeypatch.setattr(camoucrome, name, mod, raising=False)


def test_probe_host_draw_passes_display_and_platform_version(monkeypatch, capsys):
    import measure_step2 as m
    d = {"gamut": "p3", "colorBits": 8, "hdr": False}
    _fake_host(monkeypatch, d, "15.0.0")
    assert m.probe_host_draw("x") == {"host_renderer": "R", "host_families": {"F"}, "host_display": d,
                                      "host_platform_version": "15.0.0"}
    assert "display unknown" not in capsys.readouterr().out


def test_probe_host_draw_leaves_out_a_failed_probe_and_says_so(monkeypatch, capsys):
    import measure_step2 as m
    _fake_host(monkeypatch, None, None)
    assert m.probe_host_draw("x") == {"host_renderer": "R", "host_families": {"F"}}
    assert "display unknown: gamut, bit depth and HDR keep the host's values" in capsys.readouterr().out


_ROW = {"value": True, "class": "windows-desktop", "source": "CSS Media Queries 4 initial value for a mouse"}


def test_accepted_default_needs_a_source_a_class_and_the_baseline_value():
    base = {"media.(hover: hover)": True}
    assert r.accepted(["media.(hover: hover)"], {"media.(hover: hover)": True}, {"media.(hover: hover)": _ROW}, base) == ["media.(hover: hover)"]


def test_accepted_default_must_equal_stock_baseline():
    assert r.accepted(["media.(hover: hover)"], {"media.(hover: hover)": True}, {"media.(hover: hover)": _ROW}, {"media.(hover: hover)": False}) == []


def test_shared_value_that_differs_from_the_default_stays_unexplained():
    assert r.accepted(["media.(hover: hover)"], {"media.(hover: hover)": False}, {"media.(hover: hover)": _ROW}, {"media.(hover: hover)": True}) == []


def test_accepted_default_without_class_or_source_is_refused():
    base = {"k": True}
    for bad in ({"value": True, "class": "windows-desktop", "source": "short"}, {"value": True, "source": "x" * 20}):
        assert r.accepted(["k"], {"k": True}, {"k": bad}, base) == []


def test_counts_report_raw_and_net():
    acc = {"a": {"value": 1, "class": "windows-desktop", "source": "x" * 20}}
    out = r.unexplained_counts(["a", "b"], {"a": 1, "b": 2}, {}, acc, {"a": 1, "b": 2})
    assert (out["raw"], out["net"], out["unexplained"]) == (2, 1, ["b"])


def test_accepted_defaults_rows_meet_both_criteria():
    """(a) a class and a cited source, (b) the value equals what stock Chrome reads in the committed baseline."""
    import json, pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    d = json.loads((root / "settings" / "accepted_defaults.json").read_text(encoding="utf-8"))
    assert "BOTH" in d["$comment"]
    base = r.baseline_for_mode(json.loads((root / "baselines" / "chrome-8103-stock-oracle-windows.json").read_text(encoding="utf-8")), "headed")
    for k, row in d["leaves"].items():
        assert row["class"] in r.ACCEPTED_CLASSES and len(row["source"]) >= 20, k
        assert k in base and r._same(base[k], row["value"]), f"{k}: baseline {base.get(k)!r} != row {row['value']!r}"


def test_audio_sample_rate_reason_matches_the_shipped_rate():
    import json, pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    rate = json.loads((root / "settings" / "audio.json").read_text(encoding="utf-8"))["Windows"]["sampleRate"]
    why = r.label_rows({"oracle.audio.sampleRate": 1}, {"oracle.audio.sampleRate": 2})[0][4]
    assert str(rate) in why and "48000" not in why


def test_link_values_never_reach_tables_or_comparisons():
    c = {"link.total": 1, "link.shared": ["a"], "link.values": {"a": "CTRL-SECRET"}}
    f = {"link.total": 1, "link.shared": ["a"], "link.values": {"a": "FORK-SECRET"}}
    assert r.label_rows(c, f) == []
    doc = {"run": "t", "versions": {"control": "1", "fork": "1"}, "flags": {}, "errors": {},
           "rows": {"linkability": {"control": {"headless": c}, "fork": {"headless": f}}}}
    md = r.render_tables(doc, {})
    assert "CTRL-SECRET" not in md and "FORK-SECRET" not in md
    a = {"rows": {"linkability": {"fork": {"headed": c}}}}
    b = {"rows": {"linkability": {"fork": {"headed": f}}}}
    assert r.compare_runs(a, b) == []


def test_baseline_for_mode_uses_the_same_mode_or_nothing():
    stock = {"headed": {"x": 1}, "headless": {"x": 2}}
    assert r.baseline_for_mode(stock, "headless") == {"x": 2}
    assert r.baseline_for_mode({"headed": {"x": 1}}, "headless") == {}
    row = {"x": {"value": 1, "class": "windows-desktop", "source": "s" * 20}}
    n = r.unexplained_counts(["x"], {"x": 1}, {}, row, r.baseline_for_mode({"headed": {"x": 1}}, "headless"))
    assert (n["raw"], n["net"]) == (1, 1)


def test_accepted_requires_leaf_in_baseline_even_for_null():
    row = {"k": {"value": None, "class": "windows-desktop", "source": "s" * 20}}
    assert r.accepted(["k"], {"k": None}, row, {}) == []
    assert r.accepted(["k"], {"k": None}, row, {"k": None}) == ["k"]


def test_accepted_equality_is_type_strict():
    for rowv, val in ((True, 1), (0, False), (1, 1.0)):
        row = {"k": {"value": rowv, "class": "windows-desktop", "source": "s" * 20}}
        assert r.accepted(["k"], {"k": val}, row, {"k": rowv}) == []
        assert r.accepted(["k"], {"k": rowv}, row, {"k": val}) == []


def test_accepted_class_must_be_known():
    row = {"k": {"value": 1, "class": "x", "source": "s" * 20}}
    assert r.accepted(["k"], {"k": 1}, row, {"k": 1}) == []
