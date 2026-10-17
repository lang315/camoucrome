# Automated facebook recon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** one host command (`observe-auto.ps1`) runs facebook arm 1 and arm 3
unattended on the observer build and judges each arm: `PASS`, `FAIL` or
`UNMEASURED`. The plan also writes the 2026-10-17 manual-recon measurement doc.

**Architecture:**
- `observe-recon.ps1` gains an unattended mode: `-Wait`, `-FromProfile`,
  `-Out`, `-KillBelowGB`. It closes the browser with WM_CLOSE, runs an
  in-run memory watchdog and writes `run.json`.
- A new stdlib-only `scripts/observe_judge.py` reuses `observe_report.py`.
  It summarises an arm (names and counts only), builds a baseline, and judges
  an arm against that baseline.
- `scripts/windows/observe-auto.ps1` gates on three things: the owner's
  session is Active, no native build is running, and commit headroom is above
  the floor. It then runs each arm through `run-interactive.ps1` in session 1,
  judges it and cleans up. It takes no `build_lock`.

**Tech Stack:** Python 3.9-compatible stdlib (the host has Python 3.9.13),
pytest on the Mac and in CI, and Windows PowerShell 5.1 on the host via
sshgate.

**Spec:** `docs/superpowers/specs/2026-10-17-observe-auto-fb-design.md`

## Global Constraints

### Scope
- Arms 1 and 3 only, one load each, no input. Never scheduled, never
  repeated. Arm 2 (login) stays manual, by the owner.
- Tooling never types credentials and never reads cookie values.
- The backup profile `D:\camou-win\observe\backup\fb-login-20261017` is
  never written, never copied off the host, and never committed.
- Instagram, Threads, arm 4, scrolling and synthetic input are out of scope.

### Verdicts
- `UNMEASURED` exits 3, `FAIL` exits 1, `PASS` exits 0. `INFO` never fails.
- Any `UNMEASURED` check makes the arm `UNMEASURED`, never `PASS` or `FAIL`.
- Thresholds: the trace span is short when it is below the netlog span
  minus 5 s.
- Arm 3 is logged in only with the cookie names `c_user` and `xs`.
- The GPU line is `GPU process exited unexpectedly`
  (`content/browser/gpu/gpu_process_host.cc:1130`).

### Host safety (S5's conditions, 2026-10-17)
- No `build_lock`.
- Refuse while a Windows `ninja`/`siso` process runs.
- Refuse at launch below 8 GB commit headroom.
- Watchdog: poll every 5 s and force-stop below 4 GB.
- At most 10 host runs while another session's build holds the lock.

### Data handling
- Commit only API names, counts, group names, built-in names, hosts, cookie
  names, run times and hashes.
- Never commit traces, netlogs, `cookies.db`, profiles, cookie values,
  account ids, URL queries, script URLs, IPs, geo, or user names.

### Git and repo rules
- Commit messages go through `git commit -F <file>` and end with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. No session URL
  anywhere.
- Use plain `git -C <worktree>` commands: no `cd X && git`, no `$(...)`
  near git.
- No merge to main without the owner. The PR body carries evidence.
- Reply to the owner in the owner's language and give times in local time.

## Review Focus

1. A browser that was force-stopped writes no `trace.json`. The judge must
   print `UNMEASURED no trace`, not a traceback. Task 2 tests this.
2. `run.json` written by PowerShell may carry a UTF-8 BOM, and the judge must
   still parse it. Task 2 tests this.
3. Intl measured but empty on facebook (`{}`, not `None`) is not blind. A
   baseline that requires `intl` then gives `FAIL`. Task 2 tests this.
4. A missing `net.json` gives `UNMEASURED no netlog`. A missing baseline file
   is a usage error, exit 2, with a clear message. Task 2 tests both.
5. `summary` output must never contain a URL query, a script path or a
   cookie value, even when the trace holds them. Task 1 tests this.

---

## File structure

| Path | Responsibility |
|---|---|
| `scripts/observe_judge.py` (new) | `summarize`, `make_baseline`, `judge` and the CLI. Names and counts only. |
| `scripts/test_observe_judge.py` (new) | Unit tests with in-test fixtures. |
| `scripts/windows/observe-recon.ps1` (modify) | Unattended mode: `-Wait`, `-FromProfile`, `-Out`, `-KillBelowGB`, watchdog, `run.json`. Manual mode unchanged. |
| `scripts/windows/observe-auto.ps1` (new) | The one command: gates, per-arm launch, judge, cleanup, exit code. |
| `.github/workflows/build-verify.yml` (modify) | Add `scripts/test_observe_judge.py` to the pytest list. |
| `docs/observer/baselines/facebook-auto.json` (new, Task 7) | The calibrated baseline. |
| `docs/superpowers/measurements/2026-10-17-fb-observe-intl.md` (new, Task 8) | The manual recon of 2026-10-17. |
| `CLAUDE.md`, `docs/observer/README.md`, `docs/observer/followups.md`, `docs/superpowers/specs/2026-10-06-tracking-observer-design.md`, roadmap, memory (Task 9) | Tell every session about the relaxed rule. |

Host copies (Task 5) all live in `D:\camou-win\observe\`, byte-exact with the
branch: `recon.ps1`, `observe-auto.ps1`, `run-interactive.ps1`,
`observe_report.py`, `observe_judge.py`.

---

### Task 1: `observe_judge.py summarize`

**Files:**
- Create: `scripts/observe_judge.py`
- Test: `scripts/test_observe_judge.py`

**Interfaces:**
- Consumes these functions from `observe_report`:
  - `load_trace(path)`, `all_events(data)`, `events_of(data)`;
  - `surface_counts(events) -> {site: {(origin, script): Counter(api -> n)}}`;
  - `group_of(api) -> str`;
  - `intl_counts(events) -> {(site, script, builtin): n} | None`;
  - `load_requests(path) -> [(site, host, path, method)]`;
  - `load_cookie_names(db) -> [(host, name, expires, httponly)]`;
  - `_find(obj, key)`.
- Produces `summarize(arm_dir) -> dict`, which raises `MissingInput(what)`
  when `trace.json` or `net.json` is missing or unparseable. The dict keys:
  - `groups: {group: n}` and `members: {api: n}`, both on `SITE` only;
  - `intl: {builtin: n} | None`;
  - `cookies: ["host:name", ...]`;
  - `requests: {"total": n, "ajax_bz": n}`;
  - `coverage: {"trace_s": float, "net_s": float, "discarded": int | None}`;
  - `run: dict | None`.
- Also produces the constants `SITE = "https://facebook.com"`,
  `LOGGED_IN = ("c_user", "xs")` and `SLACK_S = 5`.

- [ ] **Step 1: Write the failing tests**

```python
"""observe_judge.py on hand-made fixtures shaped like the host's arm directories."""
import json
import pathlib
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import observe_judge as j  # noqa: E402

CAT = "disabled-by-default-camou.observe"
FB = "https://facebook.com"


def ev(name, ts=1_000_000, site=FB, origin="https://www.facebook.com",
       script="https://static.xx.fbcdn.net/rsrc.php/v4/a.js?_nc_x=SECRETQ"):
    return {"name": name, "cat": CAT, "ph": "I", "pid": 1, "tid": 1, "ts": ts,
            "args": {"origin": origin, "site": site, "script": script}}


def rcs(ts, stats):
    return {"name": "V8.Execute", "cat": "v8", "ph": "X", "pid": 1, "tid": 1, "ts": ts,
            "dur": 10, "args": {"runtime-call-stats": stats}}


def make_arm(tmp_path, events=None, discarded=0, buffer_stats=True, net_span_ms=30_000,
             cookies=(("datr", "SECRETVAL"),), run=None, bom=False, trace=True, net=True):
    d = tmp_path / "arm"
    d.mkdir(parents=True, exist_ok=True)
    if events is None:
        events = [ev("Navigator.userAgent.get"), ev("Navigator.userAgent.get", ts=31_000_000),
                  ev("HTMLCanvasElement.toDataURL"),
                  rcs(2_000_000, {"DateTimeFormatConstructor": [4, 1.0]})]
    if trace:
        data = {"traceEvents": events}
        if buffer_stats:
            data["metadata"] = {"trace_processor_stats": {"traced_buf": [
                {"buffer_size": 1, "chunks_discarded": discarded}]}}
        (d / "trace.json").write_text(json.dumps(data))
    if net:
        start = {"type": 7, "phase": 1, "time": "1000", "params": {
            "url": "https://www.facebook.com/ajax/bz?__a=1&fb_dtsg=SECRETQ", "method": "POST",
            "network_isolation_key": "https://facebook.com https://facebook.com",
            "site_for_cookies": ""}}
        end = dict(start, phase=2, time=str(1000 + net_span_ms))
        (d / "net.json").write_text(json.dumps({
            "constants": {"logEventTypes": {"URL_REQUEST_START_JOB": 7},
                          "logEventPhase": {"PHASE_BEGIN": 1, "PHASE_END": 2}},
            "events": [start, end]}))
    con = sqlite3.connect(d / "cookies.db")
    con.execute("create table cookies (host_key text, name text, value text, "
                "encrypted_value blob, expires_utc integer, is_httponly integer)")
    for name, value in cookies:
        con.execute("insert into cookies values ('.facebook.com', ?, ?, x'00', 1, 1)", (name, value))
    con.commit()
    con.close()
    if run is None:
        run = {"session": 1, "session_state": "Active", "report_rc": 0, "left": 0,
               "low_memory_kill": False, "gpu_exit_lines": 0}
    if run != "absent":
        (d / "run.json").write_text(("\ufeff" if bom else "") + json.dumps(run), encoding="utf-8")
    return d


def test_summary_counts_groups_members_intl_requests_cookies(tmp_path):
    s = j.summarize(make_arm(tmp_path))
    assert s["members"] == {"Navigator.userAgent.get": 2, "HTMLCanvasElement.toDataURL": 1}
    assert s["groups"] == {"navigator": 2, "canvas": 1, "intl": 4}
    assert s["intl"] == {"DateTimeFormatConstructor": 4}
    assert s["requests"] == {"total": 1, "ajax_bz": 1}
    assert s["cookies"] == [".facebook.com:datr"]
    assert s["coverage"] == {"trace_s": 30.0, "net_s": 30.0, "discarded": 0}
    assert s["run"]["session"] == 1


def test_summary_counts_only_the_facebook_site(tmp_path):
    events = [ev("Screen.width.get", site="https://google.com"), ev("Navigator.platform.get")]
    s = j.summarize(make_arm(tmp_path, events=events))
    assert s["members"] == {"Navigator.platform.get": 1}


def test_summary_never_carries_queries_script_paths_or_cookie_values(tmp_path):
    out = json.dumps(j.summarize(make_arm(tmp_path)))
    for leak in ("SECRETQ", "SECRETVAL", "fbcdn", "rsrc.php", "?", "fb_dtsg"):
        assert leak not in out, leak


def test_summary_intl_none_when_blind(tmp_path):
    s = j.summarize(make_arm(tmp_path, events=[ev("Navigator.userAgent.get")]))
    assert s["intl"] is None and "intl" not in s["groups"]


def test_summary_reads_a_bom_run_json(tmp_path):
    assert j.summarize(make_arm(tmp_path, bom=True))["run"]["session_state"] == "Active"


def test_summary_missing_trace_or_netlog_raises_missing_input(tmp_path):
    with pytest.raises(j.MissingInput, match="trace"):
        j.summarize(make_arm(tmp_path / "a", trace=False))
    with pytest.raises(j.MissingInput, match="netlog"):
        j.summarize(make_arm(tmp_path / "b", net=False))


def test_judge_parses_as_python_3_9():
    """The Windows host runs Python 3.9.13."""
    import ast
    ast.parse(pathlib.Path(j.__file__).read_text(), feature_version=(3, 9))
```

- [ ] **Step 2: Run the tests and check that they fail**

Run: `python3 -m pytest -q scripts/test_observe_judge.py`
Expected: an error at collection, `ModuleNotFoundError: No module named 'observe_judge'`.

- [ ] **Step 3: Write `scripts/observe_judge.py`, summary part**

```python
"""Summarise and judge an unattended observer recon arm (names and counts only).

  python observe_judge.py summary ARM_DIR
  python observe_judge.py baseline --arm N DIR [--arm N DIR ...] -o FILE
  python observe_judge.py judge --baseline FILE --arm N DIR [--summary-out FILE]

judge exits 0 PASS, 1 FAIL, 3 UNMEASURED; 2 is a usage error.
"""
import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import observe_report as r  # noqa: E402

SITE = "https://facebook.com"
LOGGED_IN = ("c_user", "xs")
SLACK_S = 5


class MissingInput(Exception):
    pass


def _json(path):
    with open(path, encoding="utf-8-sig") as f:  # PowerShell may write a BOM
        return json.load(f)


def coverage(data, net):
    evs = [e for e in r.all_events(data) if e.get("ph") != "M" and e.get("ts", 0) > 0]
    trace_s = (max(e["ts"] for e in evs) - min(e["ts"] for e in evs)) / 1e6 if evs else 0.0
    times = [int(e["time"]) for e in net.get("events", []) if "time" in e]
    net_s = (max(times) - min(times)) / 1e3 if times else 0.0
    meta = data.get("metadata", {}) if isinstance(data, dict) else {}
    bufs = r._find(meta, "traced_buf")
    discarded = sum(b.get("chunks_discarded", 0) for b in bufs) if bufs else None
    return {"trace_s": round(trace_s, 1), "net_s": round(net_s, 1), "discarded": discarded}


def summarize(arm_dir):
    d = pathlib.Path(arm_dir)
    try:
        data = _json(d / "trace.json")
    except (OSError, ValueError) as e:
        raise MissingInput(f"no trace ({type(e).__name__})")
    try:
        net = _json(d / "net.json")
    except (OSError, ValueError) as e:
        raise MissingInput(f"no netlog ({type(e).__name__})")
    members = collections.Counter()
    for per_script in r.surface_counts(r.events_of(data)).get(SITE, {}).values():
        members.update(per_script)
    groups = collections.Counter()
    for api, n in members.items():
        groups[r.group_of(api)] += n
    intl = r.intl_counts(r.all_events(data))
    if intl is not None:
        per = collections.Counter()
        for (site, _script, builtin), n in intl.items():
            if site == SITE:
                per[builtin] += n
        intl = dict(per)
        if intl:
            groups["intl"] = sum(intl.values())
    reqs = r.load_requests(d / "net.json")
    db = d / "cookies.db"
    cookies = sorted(f"{h}:{n}" for h, n, *_ in r.load_cookie_names(db)) if db.exists() else []
    run = _json(d / "run.json") if (d / "run.json").exists() else None
    return {"groups": dict(groups), "members": dict(members), "intl": intl, "cookies": cookies,
            "requests": {"total": len(reqs), "ajax_bz": sum("/ajax/bz" in p for _s, _h, p, _m in reqs)},
            "coverage": coverage(data, net), "run": run}
```

`load_requests` re-reads `net.json`. Put this comment above `reqs = ...`:
`# shortcut: the netlog is parsed twice (arm 3's is ~110 MB, a few seconds); pass the parsed dict if runs get slow`

- [ ] **Step 4: Run the tests and check that they pass**

Run: `python3 -m pytest -q scripts/test_observe_judge.py`
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```
git -C <wt> add scripts/observe_judge.py scripts/test_observe_judge.py
git -C <wt> commit -F <msg>   # "feat(observer): observe_judge summary (names and counts only)"
```

---

### Task 2: `make_baseline`, `judge` and the CLI

**Files:**
- Modify: `scripts/observe_judge.py`
- Modify: `scripts/test_observe_judge.py`

**Interfaces:**
- Consumes `summarize`, `MissingInput`, `LOGGED_IN` and `SLACK_S` from
  Task 1.
- Produces:
  - `unmeasured(s, arm) -> [str]`;
  - `make_baseline({arm: [summary, ...]}) -> {"<arm>": {"required": [group], "runs": [{"groups", "intl", "requests"}]}}`;
  - `judge(arm_dir, arm, base) -> (verdict, rows)`, where `rows` is a list of
    `(level, text)` pairs and the verdict is one of
    `"PASS" | "FAIL" | "UNMEASURED"`;
  - `EXIT = {"PASS": 0, "FAIL": 1, "UNMEASURED": 3}`;
  - `main(argv)`.

- [ ] **Step 1: Write the failing tests** (append them to `scripts/test_observe_judge.py`)

```python
BASE = {"1": {"required": ["navigator", "canvas", "intl"], "runs": [
    {"groups": {"navigator": 2, "canvas": 1, "intl": 4}, "intl": {}, "requests": {}}]}}


def verdict(tmp_path, arm=1, base=BASE, **kw):
    return j.judge(make_arm(tmp_path, **kw), arm, base)


def test_pass_when_measured_and_every_required_group_seen(tmp_path):
    v, rows = verdict(tmp_path)
    assert v == "PASS"
    assert ("PASS", "canvas 1") in rows


@pytest.mark.parametrize("kw,why", [
    ({"run": "absent"}, "run.json missing"),
    ({"run": {"session": 0, "session_state": "Active", "report_rc": 0, "left": 0}}, "session=0"),
    ({"run": {"session": 1, "session_state": "Disc", "report_rc": 0, "left": 0}}, "session_state=Disc"),
    ({"run": {"session": 1, "session_state": "Active", "report_rc": 1, "left": 0}}, "report_rc=1"),
    ({"run": {"session": 1, "session_state": "Active", "report_rc": 0, "left": 3}}, "left=3"),
    ({"run": {"session": 1, "session_state": "Active", "report_rc": 0, "left": 0,
              "low_memory_kill": True}}, "low-memory"),
    ({"run": {"session": 1, "session_state": "Active", "report_rc": 0, "left": 0,
              "gpu_exit_lines": 1}}, "gpu-crash"),
    ({"discarded": 7}, "buffer full"),
    ({"buffer_stats": False}, "buffer stats missing"),
    ({"net_span_ms": 60_000}, "trace short"),
    ({"events": [ev("Navigator.userAgent.get")]}, "intl blind"),
    ({"trace": False}, "no trace"),
    ({"net": False}, "no netlog"),
])
def test_unmeasured_causes(tmp_path, kw, why):
    v, rows = verdict(tmp_path, **kw)
    assert v == "UNMEASURED"
    assert any(level == "UNMEASURED" and why in text for level, text in rows), rows


def test_arm3_without_login_cookies_is_session_expired(tmp_path):
    v, rows = verdict(tmp_path, arm=3, base={})
    assert v == "UNMEASURED"
    assert any("session expired" in t and "-Arm 2" in t for _l, t in rows)
    v, _ = verdict(tmp_path / "x", arm=3, base={},
                   cookies=(("c_user", "1"), ("xs", "2"), ("datr", "3")))
    assert v == "PASS"


def test_fail_when_a_required_group_is_gone(tmp_path):
    base = {"1": {"required": ["navigator", "webgpu"], "runs": []}}
    v, rows = verdict(tmp_path, base=base)
    assert v == "FAIL" and ("FAIL", "webgpu 0") in rows


def test_intl_measured_but_empty_fails_a_required_intl(tmp_path):
    events = [ev("Navigator.userAgent.get"), ev("HTMLCanvasElement.toDataURL"),
              ev("Navigator.userAgent.get", ts=31_000_000),
              rcs(2_000_000, {"ArrayPrototypePush": [1, 1.0]})]
    v, rows = verdict(tmp_path, events=events)
    assert v == "FAIL" and ("FAIL", "intl 0") in rows


def test_unmeasured_wins_over_fail(tmp_path):
    base = {"1": {"required": ["webgpu"], "runs": []}}
    assert verdict(tmp_path, base=base, discarded=1)[0] == "UNMEASURED"


def test_drift_and_new_groups_are_info_only(tmp_path):
    base = {"1": {"required": ["navigator"], "runs": [{"groups": {"navigator": 50}}]}}
    v, rows = verdict(tmp_path, base=base)
    assert v == "PASS"
    assert ("INFO", "navigator 2 vs baseline [50]") in rows
    assert ("INFO", "new group canvas 1") in rows


def test_empty_baseline_requires_nothing(tmp_path):
    assert verdict(tmp_path, base={})[0] == "PASS"


def test_baseline_requires_groups_seen_in_every_run(tmp_path):
    a = {"groups": {"navigator": 2, "canvas": 1}, "intl": {}, "requests": {"total": 1}}
    b = {"groups": {"navigator": 5, "audio": 9}, "intl": {}, "requests": {"total": 2}}
    base = j.make_baseline({1: [a, b]})
    assert base["1"]["required"] == ["navigator"]
    assert [x["groups"] for x in base["1"]["runs"]] == [a["groups"], b["groups"]]


def test_cli_exit_codes_and_usage_errors(tmp_path, capsys):
    arm = make_arm(tmp_path / "a")
    bfile = tmp_path / "b.json"
    bfile.write_text(json.dumps(BASE))
    assert j.main(["judge", "--baseline", str(bfile), "--arm", "1", str(arm)]) == 0
    assert "arm1 PASS" in capsys.readouterr().out
    bfile.write_text(json.dumps({"1": {"required": ["webgpu"], "runs": []}}))
    assert j.main(["judge", "--baseline", str(bfile), "--arm", "1", str(arm)]) == 1
    assert j.main(["judge", "--baseline", str(tmp_path / "none.json"), "--arm", "1", str(arm)]) == 2
    out = tmp_path / "base.json"
    assert j.main(["baseline", "--arm", "1", str(arm), "-o", str(out)]) == 0
    assert json.loads(out.read_text())["1"]["required"] == ["canvas", "intl", "navigator"]
    so = tmp_path / "s.json"
    j.main(["judge", "--baseline", str(out), "--arm", "1", str(arm), "--summary-out", str(so)])
    assert json.loads(so.read_text())["groups"]["canvas"] == 1
```

- [ ] **Step 2: Run the tests and check that they fail**

Run: `python3 -m pytest -q scripts/test_observe_judge.py`
Expected: the new tests fail with `AttributeError: module 'observe_judge' has no attribute 'judge'`, and the first 7 pass.

- [ ] **Step 3: Implement** (append to `scripts/observe_judge.py`)

```python
EXIT = {"PASS": 0, "FAIL": 1, "UNMEASURED": 3}
EXPIRED = ("session expired: log in with recon.ps1 -Site facebook -Arm 2 -Intl "
           "and refresh the backup")


def unmeasured(s, arm):
    run = s["run"]
    if run is None:
        return ["run.json missing"]
    why = []
    if run.get("session") != 1:
        why.append(f"session={run.get('session')}")
    if run.get("session_state") != "Active":
        why.append(f"session_state={run.get('session_state')}")
    if run.get("report_rc") != 0:
        why.append(f"report_rc={run.get('report_rc')}")
    if run.get("left"):
        why.append(f"left={run.get('left')}")
    if run.get("low_memory_kill"):
        why.append("low-memory")
    if run.get("gpu_exit_lines"):
        why.append(f"gpu-crash lines={run.get('gpu_exit_lines')}")
    c = s["coverage"]
    if c["discarded"] is None:
        why.append("buffer stats missing")
    elif c["discarded"]:
        why.append(f"buffer full ({c['discarded']} chunks discarded)")
    if c["trace_s"] < c["net_s"] - SLACK_S:
        why.append(f"trace short ({c['trace_s']} s of {c['net_s']} s)")
    if s["intl"] is None:
        why.append("intl blind")
    if arm == 3 and not all(f".facebook.com:{n}" in s["cookies"] for n in LOGGED_IN):
        why.append(EXPIRED)
    return why


def make_baseline(by_arm):
    out = {}
    for arm, sums in by_arm.items():
        seen = [{g for g, n in s["groups"].items() if n > 0} for s in sums]
        out[str(arm)] = {"required": sorted(set.intersection(*seen)) if seen else [],
                         "runs": [{k: s.get(k) for k in ("groups", "intl", "requests")} for s in sums]}
    return out


def judge(arm_dir, arm, base, summary_out=None):
    try:
        s = summarize(arm_dir)
    except MissingInput as e:
        return "UNMEASURED", [("UNMEASURED", str(e))]
    if summary_out:
        pathlib.Path(summary_out).write_text(json.dumps(s, indent=1, sort_keys=True))
    ref = base.get(str(arm), {})
    req, runs = ref.get("required", []), ref.get("runs", [])
    rows = [("UNMEASURED", w) for w in unmeasured(s, arm)]
    for g in req:
        n = s["groups"].get(g, 0)
        rows.append(("PASS" if n > 0 else "FAIL", f"{g} {n}"))
    for g in req:
        rows.append(("INFO", f"{g} {s['groups'].get(g, 0)} vs baseline "
                             f"{[x.get('groups', {}).get(g, 0) for x in runs]}"))
    for g in sorted(set(s["groups"]) - set(req)):
        rows.append(("INFO", f"new group {g} {s['groups'][g]}"))
    known = set().union(*[set((x.get("intl") or {})) for x in runs]) if runs else set()
    for b in sorted(set(s["intl"] or {}) - known):
        rows.append(("INFO", f"new intl builtin {b} {s['intl'][b]}"))
    rows.append(("INFO", f"requests {s['requests']['total']} ajax_bz {s['requests']['ajax_bz']}"))
    levels = {lvl for lvl, _ in rows}
    v = "UNMEASURED" if "UNMEASURED" in levels else "FAIL" if "FAIL" in levels else "PASS"
    return v, rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("summary")
    p.add_argument("arm_dir")
    p = sub.add_parser("baseline")
    p.add_argument("--arm", nargs=2, action="append", metavar=("N", "DIR"), required=True)
    p.add_argument("-o", required=True)
    p = sub.add_parser("judge")
    p.add_argument("--baseline", required=True)
    p.add_argument("--arm", nargs=2, metavar=("N", "DIR"), required=True)
    p.add_argument("--summary-out")
    a = ap.parse_args(argv)
    if a.cmd == "summary":
        print(json.dumps(summarize(a.arm_dir), indent=1, sort_keys=True))
        return 0
    if a.cmd == "baseline":
        by_arm = collections.defaultdict(list)
        for n, d in a.arm:
            by_arm[int(n)].append(summarize(d))
        pathlib.Path(a.o).write_text(json.dumps(make_baseline(by_arm), indent=1, sort_keys=True))
        return 0
    try:
        base = _json(a.baseline)
    except (OSError, ValueError) as e:
        print(f"usage error: baseline {a.baseline}: {e}", file=sys.stderr)
        return 2
    arm = int(a.arm[0])
    v, rows = judge(a.arm[1], arm, base, a.summary_out)
    for level, text in rows:
        print(f"{level} arm{arm} {text}")
    print(f"arm{arm} {v}")
    return EXIT[v]


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and check that they pass**

Run: `python3 -m pytest -q scripts/test_observe_judge.py`
Expected: `29 passed` (7 + 13 parametrized + 9).

- [ ] **Step 5: Add the test file to CI's pytest list, then run the whole suite**

In `.github/workflows/build-verify.yml`, insert
`scripts/test_observe_judge.py` after `scripts/test_observe_report.py` on the
pytest line.

Run: `python3 -m pytest -q scripts client/python/tests 2>&1 | tail -1`
Expected: `N passed` with 0 failed. Note N.

- [ ] **Step 6: Commit** (message: `feat(observer): observe_judge baseline and judge; CI runs its tests`)

---

### Task 3: unattended mode in `observe-recon.ps1`

**Files:**
- Modify: `scripts/windows/observe-recon.ps1`

**Interfaces:**
- Produces new parameters: `-Wait <int>` (0 means manual),
  `-FromProfile <dir>`, `-Out <dir>`, `-KillBelowGB <double, default 4>`.
- Unattended mode writes `<Out>\arm<N>\run.json` with these keys:
  - `session`, `session_state`;
  - `wait_s`, `closed`, `left`;
  - `low_memory_kill`;
  - `headroom_launch_gb`, `headroom_min_gb`;
  - `wsl_build`;
  - `gpu_exit_lines`;
  - `report_rc`;
  - `started`, `ended`.

  It prints `CLOSED=<n> LEFT=<n>`.
- Manual mode (`-Wait` absent) is byte-for-byte the old behaviour on the
  same inputs.

PowerShell has no unit harness here. The test is the host run in Task 6.
This task's own gate: the parser accepts the file on the host, and a diff
review shows that manual mode is unchanged.

- [ ] **Step 1: Edit the param block** (lines 1-12)

```powershell
# Recon launcher for the camoucrome observer build. Headed, no CDP.
# Usage: recon.ps1 -Site facebook|instagram|threads -Arm 1|2|3|4 [-Force] [-Intl]
#        recon.ps1 -PostOnly -Dir <arm dir> -Profile <profile dir>
# Unattended (observe-auto.ps1): -Wait <s> -Out <run dir> [-FromProfile <dir>] [-KillBelowGB <n>]
param(
  [ValidateSet('facebook','instagram','threads')][string]$Site,
  [ValidateSet(1,2,3,4)][int]$Arm,
  [switch]$Force,
  [switch]$Intl,
  [switch]$PostOnly,
  [string]$Dir,
  [string]$Profile,
  [int]$Wait = 0,
  [string]$FromProfile,
  [string]$Out,
  [double]$KillBelowGB = 4
)
```

- [ ] **Step 2: Record the report's exit code in `Invoke-Post`**

After the line `& $Py @pa | Out-File -Encoding utf8 $rep`, add
`$script:ReportRc = $LASTEXITCODE`. Keep the existing `Write-Host "report exit=$LASTEXITCODE -> $rep"` line.

- [ ] **Step 3: Run layout under `-Out`**

Replace lines 67-68, the two `$Dir =` / `$Profile =` assignments, with:

```powershell
if ($Out) {
  if (-not $Wait) { throw '-Out is for unattended runs; pass -Wait' }
  if ($Arm -eq 3 -and -not $FromProfile) { throw 'unattended arm 3 needs -FromProfile' }
  $Dir     = Join-Path $Out "arm$Arm"
  $Profile = Join-Path $Out "profile-arm$Arm"
  if ((Test-Path $Dir) -or (Test-Path $Profile)) { throw "$Dir or $Profile exists; -Out wants a fresh run dir" }
} else {
  $Dir     = Join-Path $Root "$Site\arm$Arm"
  $Profile = Join-Path $Root "$Site\profile-arm$Arm"
}
```

Then wrap the existing arm-3 reuse block (`if ($Arm -eq 3) { ... } elseif ... { throw ... }`) in `if (-not $Out) { ... }`.

- [ ] **Step 4: Copy the backup, add logging, and define the headroom helper**

Insert this just before `$what = @{`:

```powershell
function Get-HeadroomGB { [math]::Round((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory / 1MB, 2) }
if ($FromProfile) {
  if (-not (Test-Path $FromProfile)) { throw "missing -FromProfile $FromProfile" }
  robocopy $FromProfile $Profile /E /COPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy $FromProfile failed rc=$LASTEXITCODE" }
}
```

After the `$fl = @(...)` block, add:

```powershell
# unattended runs log to <profile>\chrome_debug.log so a GPU process crash is countable
if ($Wait) { $fl += @('--enable-logging', '--v=0') }
```

- [ ] **Step 5: Unattended close plus watchdog**

Replace the line `while (Get-Mine) { Start-Sleep -Seconds 2 }` with:

```powershell
$started = Get-Date
$hLaunch = Get-HeadroomGB; $hMin = $hLaunch; $lowKill = $false; $closed = 0
if ($Wait) {
  # wait $Wait s, polling commit headroom every 5 s (S5: WSL's VM peaks mid-build)
  while (((Get-Date) - $started).TotalSeconds -lt $Wait -and (Get-Mine)) {
    Start-Sleep -Seconds 5
    $h = Get-HeadroomGB; if ($h -lt $hMin) { $hMin = $h }
    if ($h -lt $KillBelowGB) { $lowKill = $true; break }
  }
  if ($lowKill) {
    Write-Host "low-memory: headroom $hMin GB < $KillBelowGB GB; force-stopping"
    Get-Mine | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  } else {
    foreach ($id in @(Get-Mine).ProcessId) {
      $q = Get-Process -Id $id -ErrorAction SilentlyContinue
      if ($q -and $q.MainWindowHandle -ne 0) { [void]$q.CloseMainWindow(); $closed++ }
    }
  }
  for ($i = 0; $i -lt 60 -and (Get-Mine); $i++) { Start-Sleep -Seconds 1 }
  $left = @(Get-Mine).Count
  if ($left) { Get-Mine | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }
  Write-Host "CLOSED=$closed LEFT=$left"
} else {
  while (Get-Mine) { Start-Sleep -Seconds 2 }
}
```

- [ ] **Step 6: Write `run.json` after post-processing**

After the final `Invoke-Post $Dir $Profile`, append:

```powershell
if ($Wait) {
  $me = (quser 2>$null) | Where-Object { $_ -match '^>' }
  $state = if ($me -match '\s(Active|Disc)\s') { $Matches[1] } else { 'unknown' }
  $dbg = Join-Path $Profile 'chrome_debug.log'
  $gpu = if (Test-Path $dbg) { @(Select-String -Path $dbg -Pattern 'GPU process exited unexpectedly').Count } else { 0 }
  $lock = (wsl -d Ubuntu-24.04 -u lang -- bash /home/lang/actions-runner/_work/camoucrome/camoucrome/scripts/build_lock.sh status observe-auto 2>&1) -join ' '
  $run = [ordered]@{
    session = (Get-Process -Id $PID).SessionId; session_state = $state
    wait_s = $Wait; closed = $closed; left = $left; low_memory_kill = $lowKill
    headroom_launch_gb = $hLaunch; headroom_min_gb = $hMin; wsl_build = ($lock -notmatch '^\s*free')
    gpu_exit_lines = $gpu; report_rc = $script:ReportRc
    started = $started.ToString('yyyy-MM-dd HH:mm:ss'); ended = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
  }
  [IO.File]::WriteAllText((Join-Path $Dir 'run.json'), ($run | ConvertTo-Json))
}
```

- [ ] **Step 7: Review the diff for manual-mode drift**

Run: `git -C <wt> diff -- scripts/windows/observe-recon.ps1`
Expected: every changed line is in the param block, under `if ($Out)`,
`if ($FromProfile)`, `if ($Wait)` or `$script:ReportRc`. The `else` branch
of Step 3 keeps the old layout, and the `else` branch of Step 5 keeps the
old wait loop.

- [ ] **Step 8: Commit** (message: `feat(observer): unattended mode for observe-recon.ps1 (WM_CLOSE, watchdog, run.json)`)

---

### Task 4: `observe-auto.ps1`

**Files:**
- Create: `scripts/windows/observe-auto.ps1`

**Interfaces:**
- Consumes `recon.ps1`'s unattended mode (Task 3), `observe_judge.py judge`
  (Task 2), and `run-interactive.ps1`
  (`-Name`, `-Log`, `-Command`, `-Remove`).
- Produces exit code 0, 1 or 3 (the worst arm), one judge line per check,
  and a final `RESULT <verdict> <run dir>` line.

- [ ] **Step 1: Write the script**

```powershell
# Unattended facebook recon: arm 1 (logged out) and arm 3 (backed-up login), one load each,
# no input, never scheduled or repeated. Takes no build_lock; gates on the owner's Active
# session, no native build, and commit headroom (S5, 2026-10-17). Exit 0 PASS, 1 FAIL, 3 UNMEASURED.
param(
  [string]$Backup = 'D:\camou-win\observe\backup\fb-login-20261017',
  [string]$Baseline = 'D:\camou-win\observe\baseline-facebook.json',
  [double]$MinHeadroomGB = 8,
  [double]$KillBelowGB = 4,
  [int[]]$Arms = @(1, 3),
  [switch]$NoIntl,
  [string]$FromProfileOverride
)
$ErrorActionPreference = 'Stop'
$Root = 'D:\camou-win\observe'
$Ri = Join-Path $Root 'run-interactive.ps1'
$Wait = @{ 1 = 30; 3 = 120 }
$Limit = @{ 1 = 5; 3 = 8 }

function Get-Gate {
  if (-not ((quser 2>$null) | Where-Object { $_ -match '\sActive\s' })) { return 'no active session' }
  $nb = @(Get-Process ninja, siso -ErrorAction SilentlyContinue)
  if ($nb.Count) { return "native build running ($($nb[0].ProcessName))" }
  $h = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory / 1MB, 2)
  if ($h -lt $MinHeadroomGB) { return "low-memory $h GB < $MinHeadroomGB GB" }
  return $null
}

$run = Join-Path $Root ('auto\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force $run | Out-Null
$env:PYTHONUTF8 = '1'
$worst = 0
try {
  foreach ($a in $Arms) {
    $why = Get-Gate
    if ($why) { "UNMEASURED arm$a $why"; $worst = [math]::Max($worst, 3); continue }
    $cmd = "& $Root\recon.ps1 -Site facebook -Arm $a -Wait $($Wait[$a]) -Out $run -KillBelowGB $KillBelowGB"
    if (-not $NoIntl) { $cmd += ' -Intl' }
    if ($a -eq 3) { $cmd += ' -FromProfile ' + $(if ($FromProfileOverride) { $FromProfileOverride } else { $Backup }) }
    $log = Join-Path $run "arm$a.log"
    $name = "observe-auto-arm$a"
    powershell -NoProfile -ExecutionPolicy Bypass -File $Ri -Name $name -Log $log -Command $cmd | Out-Null
    $until = (Get-Date).AddMinutes($Limit[$a])
    while ((Get-Date) -lt $until -and -not ((Test-Path $log) -and (Select-String -Path $log -Pattern '^EXIT=' -Quiet))) { Start-Sleep -Seconds 3 }
    if (-not (Select-String -Path $log -Pattern '^EXIT=' -Quiet -ErrorAction SilentlyContinue)) {
      "UNMEASURED arm$a timeout after $($Limit[$a]) min"
      Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains("$run\profile-arm$a") } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    }
    powershell -NoProfile -ExecutionPolicy Bypass -File $Ri -Name $name -Remove | Out-Null
    Get-Content $log -ErrorAction SilentlyContinue | Select-String 'SESSION=|CLOSED=|low-memory|report exit' | ForEach-Object { $_.Line }
    python (Join-Path $Root 'observe_judge.py') judge --baseline $Baseline --arm $a (Join-Path $run "arm$a") --summary-out (Join-Path $run "arm$a\summary.json")
    $worst = [math]::Max($worst, $LASTEXITCODE)
  }
} finally {
  Get-ScheduledTask -TaskName 'camou-observe-auto-*' -ErrorAction SilentlyContinue | Unregister-ScheduledTask -Confirm:$false
  Remove-Item (Join-Path $run 'profile-arm*') -Recurse -Force -ErrorAction SilentlyContinue
  Get-ChildItem $run -Recurse -Filter 'cookies.db' -ErrorAction SilentlyContinue | Remove-Item -Force
}
"RESULT $(@{0 = 'PASS'; 1 = 'FAIL'; 2 = 'UNMEASURED'; 3 = 'UNMEASURED'}[[int]$worst]) $run"
exit $worst
```

`-NoIntl` and `-FromProfileOverride` exist only for the RED rows in Task 6.
`-MinHeadroomGB` and `-KillBelowGB` serve the planted-floor REDs.

The judge's usage error is exit 2, and it maps to `UNMEASURED` in `RESULT`.
`[math]::Max` with 3 still wins.

- [ ] **Step 2: Commit** (message: `feat(observer): observe-auto.ps1, the one unattended facebook recon command`)

---

### Task 5: install on the host and parse-check

**Files:** none in the repo. Host: `D:\camou-win\observe\`.

**Interfaces:** consumes the pushed branch head `<sha>`.

- [ ] **Step 1: Push the branch**

Run: `git -C <wt> push -u origin e-fb-auto`, then `git -C <wt> rev-parse HEAD`, and note `<sha>`.

- [ ] **Step 2: Compute the local hashes**

Run:
`shasum -a 256 scripts/windows/observe-recon.ps1 scripts/windows/observe-auto.ps1 scripts/windows/run-interactive.ps1 scripts/observe_report.py scripts/observe_judge.py`

- [ ] **Step 3: Fetch the files to the host, back up the old copies, and check hashes, parser and Python version** (sshgate `buildpc`, one line)

```powershell
$ErrorActionPreference='Stop'; $o='D:\camou-win\observe'; $b='https://raw.githubusercontent.com/lang315/camoucrome/<sha>/scripts'; if (Test-Path "$o\recon.ps1") { Copy-Item "$o\recon.ps1" "$o\recon-1017.ps1" -Force }; @{ 'recon.ps1'='windows/observe-recon.ps1'; 'observe-auto.ps1'='windows/observe-auto.ps1'; 'run-interactive.ps1'='windows/run-interactive.ps1'; 'observe_report.py'='observe_report.py'; 'observe_judge.py'='observe_judge.py' }.GetEnumerator() | ForEach-Object { Invoke-WebRequest -UseBasicParsing "$b/$($_.Value)" -OutFile "$o\$($_.Key)" }; Get-FileHash "$o\recon.ps1","$o\observe-auto.ps1","$o\run-interactive.ps1","$o\observe_report.py","$o\observe_judge.py" -Algorithm SHA256 | ForEach-Object { $_.Hash.ToLower()+'  '+$_.Path }; foreach ($f in 'recon.ps1','observe-auto.ps1') { $e=$null; [void][System.Management.Automation.Language.Parser]::ParseFile("$o\$f",[ref]$null,[ref]$e); "$f parse errors: $($e.Count)" }; python --version; python "$o\observe_judge.py" -h | Select-Object -First 1
```

Expected:
- the five hashes equal Step 2;
- `parse errors: 0` for both scripts;
- `Python 3.9.13`;
- a `usage:` line.

- [ ] **Step 4: Write an empty calibration baseline on the host**

Run on the host:
`[IO.File]::WriteAllText('D:\camou-win\observe\baseline-facebook.json','{}')`

---

### Task 6: host RED rows, then the first GREEN

Each row is one host run. Count the runs: S5's cap is 10 while its build
holds the lock. This task uses at most 6.

Before you start, tell S5: "observe-auto host tests starting, about 6 runs,
no build_lock". Check that S5 is not in its Windows step.

Run each command on the host as
`powershell -NoProfile -ExecutionPolicy Bypass -File D:\camou-win\observe\observe-auto.ps1 <args>`.

Rows 1 and 2 never launch Chrome and do not count toward the cap.

- [ ] **Row 1: headroom gate.** Args: `-MinHeadroomGB 1000 -Arms 1`.
  Expected: `UNMEASURED arm1 low-memory ... < 1000 GB`, then
  `RESULT UNMEASURED`, exit 3.

- [ ] **Row 2: native-build gate.** First run
  `Copy-Item C:\Windows\System32\PING.EXE $env:TEMP\ninja.exe; $p = Start-Process $env:TEMP\ninja.exe -ArgumentList '-n','90','127.0.0.1' -PassThru -WindowStyle Hidden`.
  Then run with args `-Arms 1`, then `Stop-Process -Id $p.Id`.
  Expected: `UNMEASURED arm1 native build running (ninja)`, exit 3.

- [ ] **Row 3: blind, plus the watchdog** (counts as 1 run).
  Args: `-Arms 1 -NoIntl -KillBelowGB 1000`.
  Expected:
  - the wrapper echoes the log line `low-memory: headroom ... < 1000 GB`;
    `run.json`'s `started` is at most about 10 s before the kill;
  - the judge prints `UNMEASURED arm1 no trace`, because a force-stopped
    browser writes none and the judge stops at the missing trace. If a trace
    did get written, it prints `UNMEASURED arm1 low-memory` and
    `UNMEASURED arm1 intl blind` instead;
  - exit 3.

  If the watchdog row does not appear, the watchdog is broken. Fix it under
  systematic-debugging before going on.

- [ ] **Row 4: expired session** (1 run).
  First run `New-Item -ItemType Directory -Force D:\camou-win\observe\auto-red-empty | Out-Null`.
  Then args: `-Arms 3 -FromProfileOverride D:\camou-win\observe\auto-red-empty`.
  Expected: `UNMEASURED arm3 session expired: log in with recon.ps1 -Site facebook -Arm 2 -Intl and refresh the backup`, exit 3.
  Afterwards remove `auto-red-empty`.

- [ ] **Row 5: GPU signal RED** (1 run, session 0).
  Run recon directly from the sshgate shell, which is session 0, with no
  task wrapper:
  `& D:\camou-win\observe\recon.ps1 -Site facebook -Arm 1 -Intl -Wait 30 -Out D:\camou-win\observe\auto\red-gpu-s0`

  Session 0 cannot WM_CLOSE (2026-10-07), so `LEFT` is above 0 and the
  browser is force-stopped. That is fine: this row reads only the debug log.

  Then run on the host:
  `@(Select-String -Path D:\camou-win\observe\auto\red-gpu-s0\profile-arm1\chrome_debug.log -Pattern 'GPU process exited unexpectedly').Count`
  - **Count ≥ 1:** the signal is real. Keep `gpu_exit_lines`, and record
    the count.
  - **Count 0:** `Ruling: no GPU exit line in session 0; the --enable-logging
    flag and gpu_exit_lines are dropped`. Remove Task 3 Step 4's
    `--enable-logging` lines and the `gpu_exit_lines` key, and remove the
    judge's GPU check and its test. That is a re-entry into Task 2 Step 1
    and Task 3: commit, push, then re-run Task 5. The README says the
    session gate is the only guard.

  Delete `auto\red-gpu-s0\profile-arm1` afterwards. It contains no login,
  but it is a profile.

- [ ] **Row 6: the planted FAIL** waits for Task 7. Its baseline needs real
  groups.

- [ ] **First GREEN = calibration run 1** (1 run). Args: none, so both arms run.
  Expected:
  - `RESULT PASS`;
  - both arms `arm1 PASS` and `arm3 PASS` against `{}`;
  - `CLOSED=1 LEFT=0` for each;
  - `SESSION=1` for each.

  Note the run directory.

---

### Task 7: calibrate and commit the baseline, plus the planted FAIL

**Files:**
- Create: `docs/observer/baselines/facebook-auto.json`

- [ ] **Step 1: Calibration run 2** (1 run). Run `observe-auto.ps1` with no args.
  Expected: `RESULT PASS`. Note the run directory.

- [ ] **Step 2: Build the baseline on the host**

```powershell
$env:PYTHONUTF8='1'; $o='D:\camou-win\observe'; python "$o\observe_judge.py" baseline --arm 1 <run1>\arm1 --arm 1 <run2>\arm1 --arm 3 <run1>\arm3 --arm 3 <run2>\arm3 -o "$o\baseline-facebook.json"; Get-Content "$o\baseline-facebook.json"
```

Expected: JSON with `"1"` and `"3"`. Each has a non-empty `required` list,
and it should include `intl` and `navigator`.

- [ ] **Step 3: Sanity check against the manual 10-17 arm 3**

Run on the host:
`python "$o\observe_judge.py" summary "$o\facebook\arm3"`

Expected: every name in the baseline's `"3".required` has a count above 0
in that summary's `groups`. If one does not, stop and investigate. Do not
commit the baseline.

- [ ] **Step 4: Null test, without a new run**

Re-judge each calibration arm against the new baseline:
`python "$o\observe_judge.py" judge --baseline "$o\baseline-facebook.json" --arm 1 <run1>\arm1`

Do the same for `<run2>\arm1`, `<run1>\arm3` and `<run2>\arm3`.
Expected: `arm1 PASS` and `arm3 PASS`, four times.

- [ ] **Step 5: Planted FAIL (Task 6 Row 6), without a new run**

Copy the baseline to `$o\baseline-red.json`. Add `"webgpu"` to `"1".required`
in the copy (the 10-17 runs read no webgpu). Then run:
`python "$o\observe_judge.py" judge --baseline "$o\baseline-red.json" --arm 1 <run1>\arm1`

Expected: `FAIL arm1 webgpu 0`, then `arm1 FAIL`, exit 1. Delete
`baseline-red.json` afterwards.

- [ ] **Step 6: Commit the baseline to the repo**

Fetch `baseline-facebook.json` to the Mac by printing it through sshgate.
It is small, names and counts only. Write it to
`docs/observer/baselines/facebook-auto.json` with the Write tool.

Grep it: `grep -nE '\?|[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+|c_user|xs|http' docs/observer/baselines/facebook-auto.json`
Expected: no output. The baseline holds groups, Intl built-ins and request
counts only, no cookies and no URLs.

Commit with the message:
`feat(observer): calibrated facebook baseline for observe-auto (2 runs, 2026-10-17)`

- [ ] **Step 7: Tell S5 the run count used**, and say that host tests are done.

---

### Task 8: the 2026-10-17 measurement doc

**Files:**
- Create: `docs/superpowers/measurements/2026-10-17-fb-observe-intl.md`
- Modify: `docs/superpowers/measurements/2026-10-07-fb-observe.md` (one pointer line at the end)

- [ ] **Step 1: Pull the manual-arm summaries**

On the host, run `observe_judge.py summary` for each of
`D:\camou-win\observe\facebook\arm1`, `arm2` and `arm3`. Print the output
through sshgate; each summary is small.

These manual arms have no `run.json`, so `run` is `null`. Their coverage
(`trace_s`/`net_s`) and `discarded` come from the summary.

For hosts, read each manual `report.md`'s `Requests:` tables on the host,
keeping only the host and count columns.

- [ ] **Step 2: Write the doc**

Follow the spec §1 headings: Build and launch, Coverage, Per-arm tables
side by side with the 10-07 doc §3 tables, Intl, Requests and cookies,
Findings and limits.

- Copy the 10-07 numbers from `2026-10-07-fb-observe.md` §3, and mark
  which of them were lower bounds.
- State that the owner closed nothing: tooling WM_CLOSEd every arm. Arm 1
  closed at 30 s. Arm 2 closed at 10:18:42 and arm 3 at 10:22:01 ICT, after
  the owner said each was done.
- State that arm 3 includes owner scrolling, and that the automated arm 3
  (Task 7 baseline) does not.
- Name the calibration runs' directories and verdicts as the first
  automated results.

- [ ] **Step 3: Pointer line in the 10-07 doc**

Append to the end of `2026-10-07-fb-observe.md`:
`A re-run on 2026-10-17 with exact fast-call counts and Intl built-ins, in session 1, is in \`2026-10-17-fb-observe-intl.md\`.`

- [ ] **Step 4: Privacy grep, red first**

Plant the line `PLANT 203.0.113.9 c_user=123 ?q=1` in the new doc. Then run:
`grep -nE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+|\?[a-z_]+=|c_user=|xs=' docs/superpowers/measurements/2026-10-17-fb-observe-intl.md`,
then grep the same file for the host's location, time zone, ISP and account
names. Those terms are kept in an uncommitted file, never in the repo.

Expected: the plant line is found. Remove the plant and run the grep again.
Expected: no output. A version like `154.0.8037.93` is fine; inspect any hit
by eye.

- [ ] **Step 5: Commit** (message: `docs(observer): facebook re-run 2026-10-17, exact counts and Intl`)

---

### Task 9: rule and documentation updates

**Files:**
- Modify:
  - `CLAUDE.md` (Build & verify, after the "Windows host runs" bullet);
  - `docs/superpowers/specs/2026-10-06-tracking-observer-design.md` (Recon, after the 2026-10-07 exception line);
  - `docs/observer/README.md` (a new section, plus the host-copies paragraph);
  - `docs/observer/followups.md`;
  - `docs/superpowers/plans/2026-10-02-long-term-roadmap.md` (the tracking-observer line).
- Memory: `/Users/lang/.claude/projects/-Users-lang-GolandProjects-github-com-lang315-camoucrome/memory/`.

- [ ] **Step 1: CLAUDE.md bullet**

```markdown
- **Automated facebook recon** (owner, 2026-10-17) runs only through
  `scripts/windows/observe-auto.ps1` on the host. It runs arm 1 (logged out)
  and arm 3 (the backed-up login at
  `D:\camou-win\observe\backup\fb-login-20261017`), one load each, with no
  input. Never schedule it or loop it. Arm 2, the login, stays manual by
  the owner, and tooling never types credentials.
  - The backup is never read for values, never copied off the host and
    never committed.
  - The command needs the owner's session Active. It takes no
    `build_lock`, and it refuses below 8 GB commit headroom or while a
    native Windows build runs.
  - A verdict is `PASS`, `FAIL` (a baseline group is gone) or `UNMEASURED`
    (it did not measure, including an expired login). See
    `docs/observer/README.md`.
```

- [ ] **Step 2: Spec Recon line**

After the `Owner-approved exception (2026-10-07)` bullet, add:

```markdown
- Owner-approved exception (2026-10-17): `observe-auto.ps1` may run arm 1
  and arm 3 unattended, in the owner's Active session 1, one load each, no
  input and no CDP. Arm 3 restores a backed-up logged-in profile. Never
  scheduled or repeated. Design: `2026-10-17-observe-auto-fb-design.md`.
```

- [ ] **Step 3: README section "Unattended recon (facebook)"**

The section covers:
- the command and its exit codes;
- the verdict table (copy the spec §3 table);
- what `run.json` holds;
- how to refresh an expired backup: the owner runs
  `recon.ps1 -Site facebook -Arm 2 -Intl`, then robocopies
  `facebook\profile-arm2` over the backup;
- how to recalibrate the baseline (spec §6);
- the GPU-signal ruling from Task 6 Row 5;
- the host copies and their SHA256 from Task 5.

Also edit the existing "byte-exact copies" sentence so that it lists the
five host files.

- [ ] **Step 4: followups.md**
  - Delete the open item "Rebuild the Windows `out\Observe` with
    `v8_enable_runtime_call_stats = true`": it was done 2026-10-13 and used
    2026-10-17.
  - Under "After the facebook recon", replace the Instagram/Threads line
    with: "Instagram/Threads recon dropped by the owner (2026-10-17);
    facebook re-run with exact counts and Intl in
    `2026-10-17-fb-observe-intl.md`; unattended re-runs via
    `observe-auto.ps1`."
  - Replace the "lower bounds ... re-run arms" line with a pointer to the
    same doc.

- [ ] **Step 5: Roadmap line**

In the `**Tracking observer (2026-10-07):**` line, change
"fast-call counting and the instagram/threads recon are pending" to:
"fast-call counting and V8/Intl shipped (2026-10-09, 2026-10-17); the
facebook recon is re-runnable unattended (`observe-auto.ps1`, 2026-10-17);
instagram/threads dropped by the owner".

- [ ] **Step 6: Memory.** Write `observe-auto-2026-10-17.md` with these
  points:
  - the rule change;
  - the backup path;
  - the command;
  - S5's conditions;
  - the baseline path.

  Add one line to `MEMORY.md`.

- [ ] **Step 7: Run the whole suite, then commit**

Run: `python3 -m pytest -q scripts client/python/tests 2>&1 | tail -1`
Expected: `N passed`, where N is the Task 2 count.

Commit with the message:
`docs: automated facebook recon rule for every session (CLAUDE.md, spec, README, followups, roadmap)`

---

### Task 10: final review and PR

- [ ] **Step 1:** Run the final whole-branch review as `executing-plans` describes.
- [ ] **Step 2:** Push, and open a PR against `main`. The body carries:
  - the pytest count;
  - Task 5's hashes, parse checks and Python version;
  - every Task 6 and Task 7 row's output lines (verdict lines only, no
    paths beyond `D:\camou-win\observe\auto\<ts>`);
  - the GPU ruling;
  - the baseline's required groups;
  - the privacy-grep evidence.

  Do not merge. Tell the owner, in the owner's language with local times, and tell S5.
