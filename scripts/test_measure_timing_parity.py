"""measure_timing_parity: the pure parts (verdicts, page generation, result parsing)."""
import json
import pathlib
import statistics

import pytest

import measure_timing_parity as m

ROOT = pathlib.Path(__file__).resolve().parent.parent


# ---- g_verdict: camoucrome's port of camoufox's ci/tests/test_getter_cost_verdict.py ----

def test_verdict_a_getter_three_times_its_control_against_stock_at_one_times_is_slower():
    assert m.verdict(60, 180, 40, 40) == (True, False)


def test_verdict_a_uniformly_slower_build_is_not_slower():
    assert m.verdict(60, 132, 40, 88) == (False, False)


def test_verdict_equal_costs_pass():
    assert m.verdict(60, 60, 40, 40) == (False, False)


def test_verdict_a_large_ratio_under_the_gap_is_not_slower():
    assert m.verdict(8, 24, 40, 40) == (False, False)


def test_verdict_a_getter_that_returns_early_is_still_faster():
    assert m.verdict(107, 20, 50, 60) == (False, True)


def test_verdict_exactly_twice_stock_is_not_slower_but_over_it_by_the_gap_is():
    assert m.verdict(30, 60, 40, 40) == (False, False)
    assert m.verdict(30, 60.1, 40, 40) == (True, False)


def test_verdict_exactly_the_gap_is_slower_and_just_under_it_is_not():
    assert m.verdict(20, 50, 40, 40) == (True, False)
    assert m.verdict(20, 49.9, 40, 40) == (False, False)


def test_verdict_faster_needs_the_gap_and_a_strictly_smaller_ratio():
    assert m.verdict(100, 70, 40, 200) == (False, True)
    assert m.verdict(100, 70.5, 40, 200) == (False, False)
    assert m.verdict(100, 50, 40, 40) == (False, False)


def test_g_verdict_names():
    assert m.g_verdict(60, 60, 40, 40) == "PASS"
    assert m.g_verdict(60, 180, 40, 40) == "FAIL-slower"
    assert m.g_verdict(107, 20, 50, 60) == "FAIL-faster"
    assert m.g_verdict(8, 24, 40, 40) == "PASS"


def test_g_verdict_a_bad_control_fails_the_run_not_the_getter():
    # the control is itself over twice stock's and 30 ns apart: the browsers are not comparable
    assert m.g_verdict(60, 60, 40, 100) == "FAIL-control"


def test_g_verdict_missing_figure_is_unmeasured():
    assert m.g_verdict(None, 60, 40, 40) == "UNMEASURED"
    assert m.g_verdict(60, 60, 40, None) == "UNMEASURED"
    assert m.g_verdict(60, 60, 0, 40) == "UNMEASURED"


# ---- p_verdict ----

def test_p_equal_is_ok():
    assert m.p_verdict([2.0, 2.1, 2.2], [2.0, 2.1, 2.2], 1.15) == "OK"


def test_p_gap_needs_outside_range_and_over_the_factor():
    stock = [2.0, 2.1, 2.2]
    assert m.p_verdict(stock, [3.3, 3.4, 3.5], 1.15) == "GAP"
    assert m.p_verdict(stock, [2.25, 2.3, 2.3], 1.15) == "OK"        # outside the range, under the factor
    assert m.p_verdict([1.0, 3.0, 3.1], [2.0, 2.1, 2.2], 1.15) == "OK"   # over the factor of S's median, inside S's range


def test_p_faster_also_gaps():
    assert m.p_verdict([2.0, 2.1, 2.2], [1.0, 1.1, 1.2], 1.15) == "GAP"


def test_p_empty_is_unmeasured():
    assert m.p_verdict([], [2.0], 1.15) == "UNMEASURED"
    assert m.p_verdict([2.0], [], 1.15) == "UNMEASURED"


# ---- first read ----

def test_first_read_fails_over_one_ms_and_three_times_stock():
    assert m.first_read_verdict(0.2, 5.0) == "FAIL"
    assert m.first_read_verdict(0.2, 0.9) == "PASS"      # under 1 ms
    assert m.first_read_verdict(2.0, 5.0) == "PASS"      # over 1 ms but not 3x
    assert m.first_read_verdict(None, 5.0) == "UNMEASURED"


# ---- summarise, ratios ----

def test_summarise_takes_the_median_over_launches_not_the_minimum():
    runs = [{"g_window": {"g": v}} for v in (50, 52, 51, 300, 49, 50)]
    assert m.median_over(runs, "g_window")["g"] == 50.5


def test_summarise_skips_launches_without_a_figure():
    runs = [{"g_window": {"g": None}}, {"g_window": {"g": 10}}, {"g_window": {"g": 12}}]
    assert m.median_over(runs, "g_window")["g"] == 11


def test_ratios_are_workload_over_the_regexp_replace():
    r = m.ratios({"int": 2.0, "json_parse": 5.0, "regexp": 4.0})
    assert r["json_parse"] == 1.25 and r["int"] == 0.5
    assert "regexp" not in r


# ---- page generation ----

def test_getters_cover_every_dot_key_of_keys_json():
    keys = json.loads((ROOT / "settings" / "keys.json").read_text(encoding="utf-8"))["keys"]
    dots = {k["key"] for k in keys if "." in k["key"]}
    assert len(dots) == 25
    window = m.window_getters()
    for k in dots:
        expr = m.KEY_EXPR.get(k, k)
        assert expr in window, k


def test_getters_include_the_synthetic_ones_and_the_controls():
    window = m.window_getters()
    for e in ("navigator.userAgentData.platform", "devicePixelRatio", "A.sampleRate", "A.destination.maxChannelCount",
              "M.matches", m.WINDOW_CONTROL):
        assert e in window, e
    assert m.WORKER_CONTROL in m.worker_getters()


def test_controls_are_not_touched_by_any_patch_or_addition():
    # the grep the PR carries: a control a patch touches would hide the cost it is there to measure
    for ctl in (m.WINDOW_CONTROL, m.WORKER_CONTROL):
        stem = ctl.split(".")[-1]
        for sub in ("patches", "additions"):
            for p in (ROOT / sub).rglob("*"):
                if p.is_file() and p.suffix in (".patch", ".cc", ".h", ".json", ".gn", ".py", ".sh", ""):
                    assert stem not in p.read_text(encoding="utf-8", errors="ignore"), (stem, p)


def test_page_has_the_isolation_flag_the_read_loops_and_no_cdp_dependence():
    page = m.page_html()
    assert "crossOriginIsolated" in page
    assert "1e5" in page or "100000" in page
    assert "POST" in page                      # results come back by POST, never by evaluate
    assert "document.body.dataset" not in page  # nothing reads it through a driver


def test_page_spec_carries_the_plant_and_the_expression_lists():
    spec = json.loads(m.page_spec("S2", plant="regexp"))
    assert spec["plant"] == "regexp" and spec["arm"] == "S2"
    assert spec["window"] and spec["worker"] and spec["first"]["window"] and spec["first"]["worker"]


def test_workloads_keep_the_labelled_split():
    assert m.WORKLOAD_GROUP["int"] == "jit" and m.WORKLOAD_GROUP["regexp"] == "jit"
    assert m.WORKLOAD_GROUP["json_parse"] == "cpp"
    assert m.WORKLOAD_GROUP["sort_builtin"] == "builtin"
    assert set(m.WORKLOAD_GROUP) == set(m.workload_names())


# ---- result parsing ----

def good():
    return {"arm": "S", "crossOriginIsolated": True, "p": {"int": 2.0}, "g_window": {"navigator.onLine": 50.0},
            "g_worker": {"navigator.onLine": 60.0}, "first": {"window": {"screen.width": 0.01},
                                                              "worker": {"screen.width": None}},
            "worker_ok": True, "errors": []}


def test_parse_result_ok():
    r, why = m.parse_result(good())
    assert why is None and r["arm"] == "S"


def test_parse_result_missing_worker_block_is_unmeasured_never_pass():
    bad = good()
    bad["worker_ok"] = False
    r, why = m.parse_result(bad)
    assert why and "worker" in why


def test_parse_result_not_isolated_is_unmeasured():
    bad = good()
    bad["crossOriginIsolated"] = False
    r, why = m.parse_result(bad)
    assert why and "isolated" in why.lower()


def test_parse_result_garbage_is_unmeasured():
    r, why = m.parse_result({"arm": "S"})
    assert why


# ---- verdict tables ----

def run_of(arm, scale=1.0, n=6, gscale=1.0):
    out = []
    for i in range(n):
        j = 1 + 0.01 * (i % 3)
        out.append({"arm": arm,
                    "p": {"int": 2.0 * j, "float": 3.0 * j, "regexp": 4.0 * j, "json_parse": 8.0 * j * scale,
                          "sort_builtin": 5.0 * j},
                    "g_window": {"navigator.onLine": 50.0 * j, "screen.width": 60.0 * j * gscale},
                    "g_worker": {"navigator.onLine": 60.0 * j, "navigator.hardwareConcurrency": 70.0 * j},
                    "first": {"window": {"screen.width": 0.05}, "worker": {"navigator.hardwareConcurrency": 0.1}}})
    return out


def test_tables_stock_against_stock_gives_no_gap_and_no_fail():
    rows = m.compare(run_of("S"), run_of("S2"), p_factor=1.15)
    assert not [r for r in rows["p"] if r["verdict"] == "GAP"], rows["p"]
    assert not [r for r in rows["g"] if r["verdict"].startswith("FAIL")], rows["g"]
    assert not [r for r in rows["first"] if r["verdict"] == "FAIL"]


def test_tables_a_planted_workload_gaps_only_that_ratio():
    rows = m.compare(run_of("S"), run_of("S2", scale=2.0), p_factor=1.15)
    gaps = sorted(r["name"] for r in rows["p"] if r["verdict"] == "GAP")
    assert gaps == ["json_parse"], gaps


def test_tables_a_slow_getter_fails_only_that_getter():
    rows = m.compare(run_of("S"), run_of("F", gscale=4.0), p_factor=1.15)
    fails = [r["name"] for r in rows["g"] if r["verdict"].startswith("FAIL")]
    assert fails == ["screen.width"], fails


def test_session_active_reads_session_one_only():
    act = " services   0  Disc\n>rdp-tcp#17  lang315  1  Active\n console  3  Conn"
    disc = " services   0  Disc\n lang315  1  Disc\n console  3  Conn"
    assert m.session_active(act) and not m.session_active(disc) and not m.session_active("")


# ---- review fixes (PR #179) ----

def write_run(tmp_path, ok_arms, bad_arms):
    run = tmp_path / "run"
    run.mkdir()
    for arm, recs in ok_arms.items():
        for i, r in enumerate(recs):
            (run / f"launch-{arm}-{i:02d}.json").write_text(json.dumps({"arm": arm, "result": r}))
    for arm in bad_arms:
        (run / f"launch-{arm}-00.json").write_text(json.dumps({"arm": arm, "unmeasured": "the page never reported"}))
    return run


def report_code(run, ref="S"):
    import argparse
    return m.report_cmd(argparse.Namespace(dir=str(run), ref=ref, p_factor=1.15))


def test_report_exits_3_when_an_arm_has_no_measured_launch(tmp_path):
    run = write_run(tmp_path, {"S": run_of("S")}, ["F"])
    assert report_code(run) == 3


def test_report_exits_0_for_equal_arms_and_1_for_a_gap(tmp_path):
    assert report_code(write_run(tmp_path, {"S": run_of("S"), "F": run_of("F")}, [])) == 0
    sub = tmp_path / "b"
    sub.mkdir()
    assert report_code(write_run(sub, {"S": run_of("S"), "F": run_of("F", scale=2.0)}, [])) == 1


def test_report_exits_3_when_a_row_is_unmeasured(tmp_path):
    other = run_of("F")
    for r in other:
        del r["g_window"]["screen.width"]
    run = write_run(tmp_path, {"S": run_of("S"), "F": other}, [])
    assert report_code(run) == 3


def test_a_getter_missing_on_one_side_is_an_unmeasured_row_not_dropped():
    other = run_of("F")
    for r in other:
        del r["g_window"]["screen.width"]
    rows = m.compare(run_of("S"), other)
    row = [r for r in rows["g"] if r["name"] == "screen.width"]
    assert row and row[0]["verdict"] == "UNMEASURED"
    assert m.totals(rows)[2] >= 1


def test_a_first_read_missing_on_one_side_is_unmeasured():
    other = run_of("F")
    for r in other:
        del r["first"]["window"]["screen.width"]
    rows = m.compare(run_of("S"), other)
    row = [r for r in rows["first"] if r["name"] == "screen.width"]
    assert row and row[0]["verdict"] == "UNMEASURED"


def test_page_keeps_the_getter_result_alive_outside_the_loop():
    page = m.page_html()
    assert page.count("self.__s = x") == 2          # the measured loop and the empty loop both sink


def test_page_builds_the_first_read_function_before_the_clock_starts():
    page = m.page_html()
    assert "f = new Function('return (' + e + ');')" in page
    assert page.index("f = new Function('return (' + e") < page.index("const t = clk(); let v, ok = true")
    assert "!ok ? null" in page                      # a throw records null, not a time


def test_lock_problem_free_and_held():
    assert m.lock_problem("free\n") is None
    assert "build_lock" in m.lock_problem("held by getter-cost since 2026-11-14T00:00:00Z\n")
    assert m.lock_problem("") is not None


def test_g_verdict_a_much_cheaper_fork_control_is_not_comparable_either():
    # stock control 100 ns, the fork's 40 ns: more than 2x the other way, over the gap
    assert m.g_verdict(60, 60, 100, 40) == "FAIL-control"
    assert m.g_verdict(60, 60, 100, 70) != "FAIL-control"      # under the factor


def test_parse_result_missing_worker_getter_block_is_unmeasured():
    bad = good()
    del bad["g_worker"]
    r, why = m.parse_result(bad)
    assert r is None and why


def test_a_first_read_missing_on_the_stock_side_is_unmeasured_too():
    stock = run_of("S")
    for r in stock:
        del r["first"]["window"]["screen.width"]
    rows = m.compare(stock, run_of("F"))
    row = [r for r in rows["first"] if r["name"] == "screen.width"]
    assert row and row[0]["verdict"] == "UNMEASURED"


# ---- arm_spec: the canvas2d bisection arms (release -5, Task 3) ----

IDENT = {"config": {"canvas:seed": 5, "navigator.hardwareConcurrency": 4, "navigator.language": "en-US"},
         "launch": {"window": [1280, 800], "dpr": 1.5, "position": [10, 20], "args": ["--x"]}}


def test_arm_spec_table():
    cfg, lo = IDENT["config"], IDENT["launch"]
    assert m.arm_spec("F", IDENT) == (cfg, lo, True)
    c, l, p = m.arm_spec("FH", IDENT)
    assert c == {**cfg, "navigator.hardwareConcurrency": __import__("os").cpu_count()} and l == lo and p is False
    assert m.arm_spec("FA", IDENT) == (None, lo, False)
    assert m.arm_spec("FS", IDENT) == ({"canvas:seed": 5}, None, False)
    c, l, p = m.arm_spec("FN", IDENT)
    assert "canvas:seed" not in c and c["navigator.hardwareConcurrency"] == 4 and l == lo and p is True
    assert m.arm_spec("SP", IDENT) == (None, None, True)
    assert m.arm_spec("SA", IDENT) == (None, lo, False)
    for arm in ("S", "S2", "F0", "V", "F0P", "SE"):
        assert m.arm_spec(arm, IDENT) == (None, None, False)


def test_arm_spec_does_not_mutate_the_identity():
    import copy
    before = copy.deepcopy(IDENT)
    for arm in m.FORK_ARMS + m.STOCK_ARMS:
        m.arm_spec(arm, IDENT)
    assert IDENT == before


def test_arm_spec_unknown_arm_refused():
    with pytest.raises(KeyError):
        m.arm_spec("ZZ", IDENT)


def test_profile_arms_split_seeded_from_fresh():
    assert "F0P" in m.SEEDED_PROFILE_ARMS and "SE" not in m.SEEDED_PROFILE_ARMS
    assert "S" in m.SEEDED_PROFILE_ARMS and "F0" not in m.SEEDED_PROFILE_ARMS


def test_finch_seed_reads_local_state(tmp_path):
    assert m._finch_seed(tmp_path) is None
    (tmp_path / "Local State").write_text('{"variations_compressed_seed": "x"}', encoding="utf-8")
    assert m._finch_seed(tmp_path) is True
    (tmp_path / "Local State").write_text('{"other": 1}', encoding="utf-8")
    assert m._finch_seed(tmp_path) is False


# ---- release -5: the harness must not hide a bimodal cost behind the minimum ----

def bimodal_run(arm, min_c, med_c, n=6):
    return [{"arm": arm,
             "p": {"regexp": 4.0, "json_parse": 8.0, "canvas2d": min_c},
             "p_med": {"regexp": 4.0, "json_parse": 8.0, "canvas2d": med_c},
             "g_window": {"navigator.onLine": 50.0, "screen.width": 60.0},
             "g_worker": {"navigator.onLine": 60.0, "navigator.hardwareConcurrency": 70.0},
             "first": {"window": {"screen.width": 0.05}, "worker": {"navigator.hardwareConcurrency": 0.1}}}
            for _ in range(n)]


def test_p_verdict_is_on_the_median_of_reps_and_names_the_direction():
    # -4's canvas2d: the seeded canvas flushes in most reps (7 us/op) and not in one (0.27 us/op); the minimum
    # read "faster than stock" while the median is slower. Stock: both read 1.7 (ratio over regexp).
    rows = m.compare(bimodal_run("S", 1.7, 1.7), bimodal_run("F", 1.1, 12.0))
    r = next(x for x in rows["p"] if x["name"] == "canvas2d")
    assert r["verdict"] == "GAP" and r["direction"] == "slower", r
    assert statistics.median(r["other_min"]) < statistics.median(r["stock_min"]), r    # the old (min) reading


def test_p_verdict_falls_back_to_the_minimum_without_median_reps():
    old = [{k: v for k, v in r.items() if k != "p_med"} for r in bimodal_run("F", 1.1, 12.0)]
    rows = m.compare(bimodal_run("S", 1.7, 1.7), old)
    r = next(x for x in rows["p"] if x["name"] == "canvas2d")
    assert r["verdict"] == "GAP" and r["direction"] == "faster"


def test_page_spec_carries_the_calibrated_repetition_counts():
    spec = json.loads(m.page_spec("F", None, n={"canvas2d": 8192}))
    assert spec["n"] == {"canvas2d": 8192}
    assert json.loads(m.page_spec("S"))["n"] is None


def test_calibration_is_the_first_stock_runs_counts():
    assert m.calibration({"p_n": {"canvas2d": 8192, "regexp": 65536}}) == {"canvas2d": 8192, "regexp": 65536}
    assert m.calibration({}) == {}
    assert m.calibration({"p_n": {"x": "bad", "y": 0, "z": 4}}) == {"z": 4}


# ---- release -5 review: calibration, privacy of the launch records, adapters ----

def _launch(tmp_path, arm, i, n, unmeasured=None):
    rec = {"arm": arm, "i": i}
    if unmeasured:
        rec["unmeasured"] = unmeasured
    else:
        rec["result"] = {"arm": arm, "p": {"regexp": 4.0}, "p_n": n}
    (tmp_path / f"launch-{arm}-{i:02d}.json").write_text(json.dumps(rec), encoding="utf-8")


def test_load_run_drops_a_launch_whose_n_differs_from_the_first_stock_launch(tmp_path):
    _launch(tmp_path, "S", 0, {"canvas2d": 8192})
    _launch(tmp_path, "F", 0, {"canvas2d": 8192})
    _launch(tmp_path, "F", 1, {"canvas2d": 65536})          # calibrated on its own: not comparable
    ok, bad = m.load_run(tmp_path)
    assert len(ok["F"]) == 1 and len(bad["F"]) == 1 and "differs" in bad["F"][0]


def test_load_run_without_a_measured_stock_launch_keeps_every_launch(tmp_path):
    _launch(tmp_path, "S", 0, None, unmeasured="session 1 is not Active")
    _launch(tmp_path, "F", 0, {"canvas2d": 8192})
    ok, bad = m.load_run(tmp_path)
    assert len(ok["F"]) == 1


def test_adapter_families_keep_gpu_vendors_only():
    got = m.adapter_families("Intel(R) Gpu 9000 (driver 1.2.3.4); Microsoft Remote Display Adapter; Parsec Virtual Display Adapter; NVIDIA Model 5")
    assert got == "Intel, NVIDIA" and "9000" not in got and "1.2.3.4" not in got
    assert "Parsec" not in got and "Microsoft" not in got   # remote-access software names are not a GPU vendor


def test_the_launch_record_never_carries_the_unmasked_renderer():
    res = {"arm": "S", "gl": "ANGLE (ExampleVendor, ExampleVendor Model 1 (0x0000ABCD) Direct3D11, D3D11-1.2.3.4)"}
    fam = m.renderer_note(res)
    assert "gl" not in res and fam == ("ExampleVendor / Direct3D11", False)


def test_compare_rows_carry_the_p75_ratios_beside_the_median():
    runs = bimodal_run("F", 1.1, 12.0)
    for r in runs:
        r["p_p75"] = {"regexp": 4.0, "json_parse": 8.0, "canvas2d": 20.0}
    rows = m.compare(bimodal_run("S", 1.7, 1.7), runs)
    r = next(x for x in rows["p"] if x["name"] == "canvas2d")
    assert statistics.median(r["other_p75"]) == 5.0 and statistics.median(r["other"]) == 3.0


def test_a_run_without_arm_s_is_refused():
    import argparse
    import pytest
    with pytest.raises(SystemExit) as e:
        m.run_cmd(argparse.Namespace(arms="F0,F"))
    assert "without arm S" in str(e.value)
