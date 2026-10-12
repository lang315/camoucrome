# Observer Intl counts via V8 runtime call stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The observer report gives per-site, per-entry-script counts of the Intl C++ built-ins (`Intl.DateTimeFormat`, `resolvedOptions`, the `supportedLocalesOf` family, `toLocale*`). The counts come from V8 runtime call stats (RCS), with no V8 patch.

**Architecture:**
- The observer out dirs set `v8_enable_runtime_call_stats = true`.
- An opt-in recording recipe adds the trace categories `v8,disabled-by-default-v8.runtime_stats`.
- V8 then attaches a `runtime-call-stats` dump to each top-level `V8.Execute` / `V8.RunMicrotasks` slice.
- `observe_report.py` sums the Intl counters of those dumps and attributes them to the slice's renderer site and entry script.
- `verify_observe.py` asserts exact counts. It also asserts a "blind" line when counting is off.

**Tech Stack:**
- Chromium 154.0.8037.93 GN args (V8);
- Python 3 (report must parse as 3.9 for the Windows host);
- pytest;
- content_shell with startup tracing on the WSL build box (`ssh buildpc` through sshgate);
- PowerShell for the Windows recon launcher.

**Spec:** `docs/superpowers/specs/2026-10-13-observer-intl-rcs-design.md` (approved 2026-10-13). It extends `docs/superpowers/specs/2026-10-06-tracking-observer-design.md`.

## Global Constraints

- No V8 patch and no change to `apply.sh`, `export.sh`, `check_checkout_sync.sh`, `rebuild_branch.sh`, `repin.py` or `upstream.env`.
- The GN arg goes only in observer out dirs (`out/Default` on the box, `out\Observe` on Windows), never in `settings/build-args.gn` or `settings/release-args.gn`.
- The default recording recipe stays byte-identical: `--trace-startup=-*,disabled-by-default-camou.observe`. The Intl recipe is opt-in: `--trace-startup=-*,disabled-by-default-camou.observe,v8,disabled-by-default-v8.runtime_stats`.
- Counted names: `^Builtin_(Intl|DateTimeFormat|NumberFormat|Collator|PluralRules|RelativeTimeFormat|ListFormat|DisplayNames|Segmenter|DurationFormat|Locale|V8BreakIterator)` or `^Builtin_\w+PrototypeToLocale`. Rows are per counter name, not family sums.
- The blind line is exactly `Intl: blind (no V8 runtime call stats in this trace)`. It is printed when no dump holds any counter. A trace with counters but no Intl call prints exactly `Intl: none called`.
- Landing order:
  1. Edit box `out/Default/args.gn`.
  2. Rebuild under lock `observe-D` and record the non-zero step count.
  3. Run the verify by hand: GREEN, then RED.
  4. Merge.

  `args.gn` is box-local, so the sync gate does not catch a wrong order.
- Box rules:
  - Every build takes `/home/lang/actions-runner/_work/camoucrome/camoucrome/scripts/build_lock.sh acquire|release observe-D`.
  - Message canvas (`chrome-build-observe-recon`) before taking the lock and after releasing it.
  - Never break another holder's lock.
  - Never touch `~/chromium-s2c`, `~/s2c-*` or `/tmp/s2c-*`.
  - No `git gc`, no `wsl --shutdown`.
  - Keep logs under `/home/lang/observe-D/`, because `/tmp` is wiped.
- Commit only API names, counts, hosts and cookie names. Never commit traces, netlogs, cookie values or account ids. Fixtures are hand-made in the shape of a real trace and carry no browsing data.
- The report must parse as Python 3.9: `test_report_parses_as_python_3_9`.
- Commits:
  - Use `git commit -F <file>`.
  - End the message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  - No session URLs anywhere pushed.
  - On the Mac: plain git commands only, no `cd X && git`.
- No merge to main without the owner's approval.
- Windows `out\Observe` is rebuilt only after canvas agrees and after the box is GREEN.

## Review Focus

1. **Dump exported as a JSON string, not a dict.** The JSON exporter can serialize a `legacy_json_value` annotation as a string. The parser must `json.loads` it. Task 2 has a test for it.
2. **Incomplete slice (`dur` = -1, or a `v8.run` cut off by a full buffer).** It must not attribute and must not crash. Task 2 has a test for it.
3. **An Intl slice in a renderer whose only observer events are worker events (empty `site`).** The site falls back to the event's origin, as in the per-site tables. With no observer event at all, the site is `(site unknown)`. Task 2 has a test for it.
4. **`v8` on but `runtime_stats` off.** The END lambda may attach an empty dump, so the report must say blind, not `none called`. Task 2 has a unit test for it. Task 3 has a box arm for it.
5. **A "blind" verify arm that measured nothing.** If `v8` tracing itself did not run, a blind result proves nothing. `blind_arm` requires more than 0 V8 entry slices. Task 3 has a test for it.

---

### Task 1: Box build with RCS, and capture of the real dump shape (controller, on the box)

The controller runs this task itself: it needs sshgate approvals, the build lock and canvas messages. No subagent.

**Files:** none in the repo. On the box:
- `~/chromium/src/out/Default/args.gn` (box-local)
- `/home/lang/observe-D/` (logs and scratch)

**Interfaces:**
- Produces, for Task 2: the confirmed JSON shape of an event carrying `runtime-call-stats`. The checks:
  - its `ph` value;
  - whether the dump is a dict or a JSON string;
  - that counter values are `[count, time]` lists;
  - the shape of `v8.run` events (`ph`, the key `args.fileName`).

  Record all four in the ledger. Task 2's code assumes: `ph == "X"`, the dump is a dict or a JSON string, values are `[count, time]`, and `v8.run` is `X` with `args.fileName`. If any of these differs, rule on the change to `intl_counts` and carry the ruling into Task 2's dispatch.

- [ ] **Step 1: Message canvas, check the lock.**

  - Send to `chrome-build-observe-recon`: "observe-D: taking the build lock for a V8-only rebuild of out/Default (adds v8_enable_runtime_call_stats = true). Expect 30-90 min."
  - Then run, through sshgate, in a base64 script:
    `/home/lang/actions-runner/_work/camoucrome/camoucrome/scripts/build_lock.sh status observe-D`

  Expected: free. If held, wait for the holder's release and do not break the lock.

- [ ] **Step 2: Write and ship the build script.**

  Write it with the Write tool, in the scratchpad, as `d-build.sh`. Send it base64-encoded. Compare the sha256 on both sides.

```bash
set -u
L=/home/lang/actions-runner/_work/camoucrome/camoucrome/scripts/build_lock.sh
D=/home/lang/observe-D
mkdir -p "$D"
cd ~/chromium/src
export PATH="$HOME/depot_tools:$PATH"
"$L" acquire observe-D || { echo "LOCK BUSY"; exit 1; }
trap '"$L" release observe-D' EXIT
cp out/Default/args.gn "$D/args.gn.before"
grep -q '^v8_enable_runtime_call_stats = true' out/Default/args.gn || \
  sed -i '/^camou_observe = true/a v8_enable_runtime_call_stats = true' out/Default/args.gn
diff "$D/args.gn.before" out/Default/args.gn
gn gen out/Default || exit 1
gn args out/Default --list=v8_enable_runtime_call_stats --short
start=$(date +%s)
autoninja -C out/Default chrome content_shell components_unittests
rc=$?
echo "build rc=$rc wall=$(( $(date +%s) - start ))s"
exit $rc
```

  Launch it detached:
  `nohup setsid bash /home/lang/observe-D/d-build.sh > /home/lang/observe-D/build.log 2>&1 < /dev/null &`

- [ ] **Step 3: Wait for the build, then gate it.**

  Expected in `build.log`:
  - the `diff` shows exactly one added line, `v8_enable_runtime_call_stats = true`;
  - `gn args` prints `v8_enable_runtime_call_stats = true`;
  - ninja reports a **non-zero** step count (`[N/N]`, N > 0);
  - `build rc=0`.

  Record N and the wall time in the ledger. A 0-step build means the arg did not take: stop and investigate.

- [ ] **Step 4: Run the sync gate.**

  Run `bash /home/lang/actions-runner/_work/camoucrome/camoucrome/scripts/check_checkout_sync.sh local /home/lang/chromium/src`.

  Expected: PASS (`rc=0`). Only `out/` changed, not the checkout.

- [ ] **Step 5: Capture the real dump shape (no page data: local probe only).**

  Write `d-shape.py` and ship it to `/home/lang/observe-D/`. Run it with cwd `/home/lang/camoucrome-verify` and that venv's python. That directory holds CI's copies of `verify_observe.py`, `lib_shell.py` and `observe_report.py`.

```python
import collections, json, sys
sys.path.insert(0, "/home/lang/camoucrome-verify")
import verify_observe as v
f = v.ON_FILTER + ",v8,disabled-by-default-v8.runtime_stats"
events, res, trace = v.run("probe.html", f)
print("res", res, "trace", trace)
rcs = [e for e in events or [] if "runtime-call-stats" in e.get("args", {})]
print("rcs events", len(rcs), collections.Counter((e.get("name"), e.get("ph")) for e in rcs))
for e in rcs[:2]:
    d = e["args"]["runtime-call-stats"]
    print("type", type(d).__name__, "keys", list(e), "dur" in e)
    d = json.loads(d) if isinstance(d, str) else d
    print("sample", list(d.items())[:3])
    print("builtins", sorted(k for k in d if k.startswith("Builtin_"))[:5])
runs = [e for e in events or [] if e.get("name") == "v8.run"]
print("v8.run", len(runs), collections.Counter(e.get("ph") for e in runs),
      [sorted(e.get("args", {})) for e in runs[:2]])
nonempty = sum(1 for e in rcs if (json.loads(e["args"]["runtime-call-stats"]) if isinstance(e["args"]["runtime-call-stats"], str) else e["args"]["runtime-call-stats"]))
print("non-empty dumps", nonempty)
```

  Expected: more than 0 rcs events, named `V8.Execute` and/or `V8.RunMicrotasks`, with non-empty dumps containing `Builtin_*` keys, and `v8.run` events with a `fileName` arg. Copy one `rcs` event's structure into the ledger: keys, `ph`, value type, two sample counters. Replace the URLs with `http://127.0.0.1:PORT`. If there are 0 rcs events, stop: the build or the category does not carry RCS, and the design needs a ruling.

- [ ] **Step 6: Release.**

  The trap releases the lock when the build script exits. Confirm with `build_lock.sh status`. Message canvas: "observe-D: build done (N steps, T min), lock released; out/Default now has v8_enable_runtime_call_stats = true. CI will need the D branch merged before its verify_observe asserts Intl rows; main's verify_observe is unaffected by the arg."

---

### Task 2: Report: Intl section in `observe_report.py`

**Files:**
- Modify: `scripts/observe_report.py`
  - lines 1-11: docstring;
  - lines 46-48: `NOT_OBSERVABLE` first item;
  - lines 63-65: `events_of`;
  - lines 166-199: `render`;
  - lines 202-210: `main`.
- Test: `scripts/test_observe_report.py`

**Interfaces:**
- Consumes: Task 1's confirmed shape. If it differs from `X` + dict-or-string + `[count, time]` + `v8.run`/`fileName`, follow the ruling in the dispatch.
- Produces:
  - `observe_report.V8_ENTRY: tuple[str, ...]`, which is `("V8.Execute", "V8.RunMicrotasks")`.
  - `observe_report.all_events(data) -> list[dict]`
  - `observe_report.intl_counts(events: list[dict]) -> dict[tuple[str, str, str], int] | None`, keyed by `(site, script label, builtin name)`. It returns `None` when blind.
  - `observe_report.render(events, requests, cookies, buffer=None, intl=None) -> str`

- [ ] **Step 1: Write the failing tests.**

  Append them to `scripts/test_observe_report.py`.

```python
def x(name, ts, dur, pid=1, tid=1, cat="v8", **args):
    return {"name": name, "cat": cat, "ph": "X", "pid": pid, "tid": tid, "ts": ts, "dur": dur,
            "args": args}


def rcs(ts, dur, stats, **kw):
    return x("V8.Execute", ts, dur, **{"runtime-call-stats": stats}, **kw)


CTOR = "Builtin_DateTimeFormatConstructor"
RO = "Builtin_DateTimeFormatPrototypeResolvedOptions"
SLO = "Builtin_DateTimeFormatSupportedLocalesOf"
APP = "https://a.com/app.js"


def at(e, ts, **kw):
    return dict(e, ts=ts, **kw)


def test_intl_counts_sum_dumps_and_keep_only_intl_names():
    events = [x("v8.run", 0, 100, fileName=APP),
              rcs(10, 20, {CTOR: [2, 5.0], "Builtin_ArrayPrototypePush": [9, 1.0], "Runtime_X": [1, 0.1]}),
              rcs(40, 20, {CTOR: [1, 1.0], RO: [3, 2.0], "Builtin_NumberPrototypeToLocaleString": [1, 1.0]}),
              at(ev("Navigator.userAgent.get", "https://a.com", "https://a.com"), 200)]
    s, sc = "https://a.com", "a.com/app.js"
    assert r.intl_counts(events) == {(s, sc, CTOR): 3, (s, sc, RO): 3,
                                     (s, sc, "Builtin_NumberPrototypeToLocaleString"): 1}


def test_intl_counts_accept_a_dump_exported_as_a_json_string():
    events = [rcs(10, 20, json.dumps({SLO: [4, 1.0]})),
              ev("Navigator.userAgent.get", "https://a.com", "https://a.com")]
    assert r.intl_counts(events) == {("https://a.com", "(unknown)", SLO): 4}


def test_intl_script_falls_back_to_the_one_observer_script_in_the_slice():
    inside = at(ev("Navigator.userAgent.get", "https://n.com", "https://n.com", script=FBQ), 15)
    events = [x("v8.callFunction", 0, 100), rcs(10, 20, {RO: [1, 0.1]}), inside, inside]
    assert r.intl_counts(events) == {
        ("https://n.com", "connect.facebook.net/en_US/fbevents.js", RO): 1}
    other = dict(inside, args=dict(inside["args"], script="https://n.com/app.js"))
    events = [rcs(10, 20, {RO: [1, 0.1]}), inside, other]
    assert r.intl_counts(events) == {("https://n.com", "(unknown)", RO): 1}


def test_intl_v8_run_on_another_thread_or_cut_off_does_not_attribute():
    obs = ev("Screen.width.get", "https://a.com", "https://a.com")
    events = [x("v8.run", 0, 100, tid=2, fileName=APP), rcs(10, 20, {RO: [1, 0.1]}), obs]
    assert r.intl_counts(events) == {("https://a.com", "(unknown)", RO): 1}
    # an incomplete slice (the trace stopped inside it) is exported with dur -1
    events = [x("v8.run", 0, -1, fileName=APP), rcs(10, 20, {RO: [1, 0.1]}), obs]
    assert r.intl_counts(events) == {("https://a.com", "(unknown)", RO): 1}


def test_intl_site_comes_from_the_pid():
    events = [rcs(10, 20, {CTOR: [1, 0.1]}, pid=7)]
    assert r.intl_counts(events) == {("(site unknown)", "(unknown)", CTOR): 1}
    # a worker's events carry no site: its origin stands in, as in the per-site tables
    w = dict(ev("WorkerNavigator.hardwareConcurrency.get", "https://a.com", ""), pid=7)
    assert r.intl_counts(events + [w]) == {("https://a.com", "(unknown)", CTOR): 1}


def test_intl_blind_only_when_no_dump_holds_a_counter():
    assert r.intl_counts([ev("Screen.width.get", "o", "s")]) is None  # no V8 slices
    assert r.intl_counts([rcs(10, 20, {})]) is None  # v8 on, runtime_stats off
    assert r.intl_counts([rcs(10, 20, json.dumps({}))]) is None
    assert r.intl_counts([rcs(10, 20, {"Runtime_X": [1, 0.1]})]) == {}  # counting on, no Intl


def test_render_intl_section_states():
    assert "Intl: blind (no V8 runtime call stats in this trace)" in r.render([], [], [])
    assert "Intl: none called" in r.render([], [], [], intl={})
    out = r.render([], [], [], intl={("https://a.com", "a.com/app.js", CTOR): 3,
                                     ("https://a.com", "a.com/app.js", RO): 5})
    assert "## V8 built-ins (Intl)" in out
    assert "| site | script | builtin | calls |" in out
    assert (out.index(f"| https://a.com | a.com/app.js | {RO} | 5 |")
            < out.index(f"| https://a.com | a.com/app.js | {CTOR} | 3 |"))
    assert "v8.run" in out and "blind" not in out
    assert out.index("## V8 built-ins (Intl)") < out.index("## Not observable")
```

  Also strengthen the last line of `test_render_lists_counts_hosts_cookies_and_blind_spots` to:

```python
    assert "## Not observable" in out and "getTimezoneOffset" in out and "NoAllocDirectCall" not in out
```

- [ ] **Step 2: Run them and see them fail.**

  Run: `python3 -m pytest -q scripts/test_observe_report.py`

  Expected: the 7 new tests FAIL with `AttributeError: module 'observe_report' has no attribute 'intl_counts'`, or a `TypeError` on `intl=`. The existing tests PASS.

- [ ] **Step 3: Implement.**

  In `scripts/observe_report.py`, add the constants after `CATEGORY`:

```python
# V8 runtime call stats (docs/superpowers/specs/2026-10-13-observer-intl-rcs-design.md):
# each top-level V8 entry slice resets the counters at its start and carries their dump
# at its end; nested slices carry none, so summing the dumps counts each call once.
V8_ENTRY = ("V8.Execute", "V8.RunMicrotasks")
RCS_ARG = "runtime-call-stats"
INTL = re.compile(r"^Builtin_(Intl|DateTimeFormat|NumberFormat|Collator|PluralRules|RelativeTimeFormat"
                  r"|ListFormat|DisplayNames|Segmenter|DurationFormat|Locale|V8BreakIterator)"
                  r"|^Builtin_\w+PrototypeToLocale")
```

  Replace the first `NOT_OBSERVABLE` item (lines 47-48) with:

```python
    "V8 built-ins Date.prototype.getTimezoneOffset (a CSA builtin) and Math; Intl counts need "
    "the Intl recording recipe and an observer build with v8_enable_runtime_call_stats = true",
```

  Replace `events_of` (lines 63-65) with:

```python
def all_events(data):
    return data["traceEvents"] if isinstance(data, dict) else data


def events_of(data):
    return [e for e in all_events(data) if e.get("cat") == CATEGORY]
```

  Add these after `surface_counts`:

```python
def _dump(e):
    d = e.get("args", {}).get(RCS_ARG)
    if isinstance(d, str):  # a legacy JSON annotation can be exported as a string
        d = json.loads(d)
    return d if isinstance(d, dict) else None


def _inside(inner, outer):
    return (inner["pid"] == outer["pid"] and inner["tid"] == outer["tid"]
            and outer["ts"] <= inner["ts"] <= outer["ts"] + outer.get("dur", 0))


def _entry_script(s, runs, observe):
    """The Blink v8.run around the slice (classic script top level), else the one script
    of the observer events inside it; handlers, timers, promise jobs and modules have no
    entry script of their own."""
    run = next((r for r in runs if _inside(s, r)), None)
    if run:
        return script_label(run.get("args", {}).get("fileName"))
    scripts = {e.get("args", {}).get("script") for e in observe if _inside(e, s)}
    return script_label(scripts.pop()) if len(scripts) == 1 else "(unknown)"


def intl_counts(events):
    """(site, script label, builtin) -> calls; None when no dump holds any counter (the
    build lacks runtime call stats or the category was off: blind, not zero)."""
    slices = [(e, _dump(e)) for e in events if e.get("name") in V8_ENTRY]
    slices = [(e, d) for e, d in slices if d is not None]
    if not any(d for _, d in slices):
        return None
    observe = [e for e in events if e.get("cat") == CATEGORY]
    sites = collections.defaultdict(collections.Counter)
    for e in observe:
        a = e.get("args", {})
        if a.get("site") or a.get("origin"):
            sites[e["pid"]][a.get("site") or a.get("origin")] += 1
    runs = [e for e in events if e.get("name") == "v8.run"]
    counts = collections.Counter()
    for s, d in slices:
        hits = {name: v[0] for name, v in d.items() if INTL.match(name)}
        if not hits:
            continue
        top = sites[s["pid"]].most_common(1)
        site = top[0][0] if top else "(site unknown)"
        script = _entry_script(s, runs, observe)
        for name, n in hits.items():
            counts[(site, script, name)] += int(n)
    return dict(counts)
```

  In `render`, change the signature to `def render(events, requests, cookies, buffer=None, intl=None):`. Insert this just before `if cookies:`:

```python
    lines += ["## V8 built-ins (Intl)", ""]
    if intl is None:
        lines += ["Intl: blind (no V8 runtime call stats in this trace)", ""]
    elif not intl:
        lines += ["Intl: none called", ""]
    else:
        lines += ["| site | script | builtin | calls |", "|---|---|---|---|"]
        for (site, script, name), n in sorted(intl.items(), key=lambda kv: (kv[0][0], -kv[1], kv[0][1:])):
            lines.append(f"| {site} | {script} | {name} | {n} |")
        lines += ["", "script: the Blink v8.run entry script, else the one script of the observer "
                  "events in the same V8 slice, else (unknown). Event handlers, timers, promise "
                  "callbacks and module bodies have no entry script.", ""]
```

  In `main`, replace the print line with:

```python
    print(render(events_of(data), load_requests(a.netlog), cookies, buffer_note(data),
                 intl_counts(all_events(data))), end="")
```

  In the docstring, after the `TRACE comes from ...` sentence, add:
  "With the Intl recipe (adding `v8,disabled-by-default-v8.runtime_stats`) on a build with `v8_enable_runtime_call_stats = true`, the report also counts Intl built-ins."

- [ ] **Step 4: Run them and see them pass.**

  Run: `python3 -m pytest -q scripts/test_observe_report.py`

  Expected: all pass, including `test_report_parses_as_python_3_9`.

- [ ] **Step 5: Commit.**

  Message file text:
  `feat(observer): report Intl built-in counts from V8 runtime call stats` + blank line + Co-Authored-By line.

```bash
git add scripts/observe_report.py scripts/test_observe_report.py
git commit -F <scratchpad>/d-commit-report.txt
```

---

### Task 3: Verify: Intl rows and blind arms in `verify_observe.py`

**Files:**
- Modify: `scripts/verify_observe.py`
  - lines 1-11: docstring;
  - lines 24-29: filters;
  - lines 31-59: `PROBE` and `WORKER`;
  - lines 158-185: new helpers;
  - lines 187-260: `main`.
- Test: `scripts/test_verify_observe.py`

**Interfaces:**
- Consumes: `observe_report.intl_counts`, `observe_report.V8_ENTRY` and `observe_report.script_label` (Task 2).
- Produces:
  - `verify_observe.INTL_FILTER: str`
  - `verify_observe.NO_RCS_FILTER: str`
  - `verify_observe.INTL_ROWS: tuple[str, str, str]`
  - `verify_observe.intl_rows(ic, site, scripts, k, bump) -> list[tuple[bool, str]]`
  - `verify_observe.blind_arm(events) -> tuple[bool, int | None]`

- [ ] **Step 1: Write the failing tests.**

  Append them to `scripts/test_verify_observe.py`.

```python
def test_intl_rows_need_exact_counts_per_script():
    site, main, worker = "http://127.0.0.1", "127.0.0.1:9/probe.html", "127.0.0.1:9/worker.js"
    exact = {(site, s, n): 3 for s in (main, worker) for n in v.INTL_ROWS}
    assert all(ok for ok, _ in v.intl_rows(exact, site, (main, worker), 3, 0))
    assert len(v.intl_rows(exact, site, (main, worker), 3, 0)) == 6
    # --red bumps every expectation by one
    assert not any(ok for ok, _ in v.intl_rows(exact, site, (main, worker), 3, 1))
    short = dict(exact)
    short[(site, worker, v.INTL_ROWS[0])] = 2
    assert [ok for ok, _ in v.intl_rows(short, site, (main, worker), 3, 0)].count(False) == 1
    # a blind trace fails every row instead of raising
    assert not any(ok for ok, _ in v.intl_rows(None, site, (main, worker), 3, 0))


def test_blind_arm_needs_v8_slices_and_no_counters():
    ex = {"name": "V8.Execute", "cat": "v8", "ph": "X", "pid": 1, "tid": 1, "ts": 0, "dur": 1,
          "args": {}}
    assert v.blind_arm([ex]) == (True, 1)
    assert v.blind_arm([dict(ex, args={"runtime-call-stats": {}})]) == (True, 1)
    assert v.blind_arm([dict(ex, args={"runtime-call-stats": {"Runtime_X": [1, 0.1]}})]) == (False, 1)
    # no V8 slices: v8 tracing never ran, so "blind" would have measured nothing
    assert v.blind_arm([OTHER]) == (False, 0)
    assert v.blind_arm(None) == (False, None)


def test_intl_filters_extend_the_default_recipe():
    assert v.INTL_FILTER == "-*,disabled-by-default-camou.observe,v8,disabled-by-default-v8.runtime_stats"
    assert v.NO_RCS_FILTER == "-*,disabled-by-default-camou.observe,v8"
    assert "Intl.DateTimeFormat.supportedLocalesOf" in v.PROBE and "resolvedOptions" in v.WORKER
```

- [ ] **Step 2: Run them and see them fail.**

  Run: `python3 -m pytest -q scripts/test_verify_observe.py`

  Expected: the 3 new tests FAIL with `AttributeError` (`INTL_ROWS`, `blind_arm`, `INTL_FILTER`). The 2 existing tests PASS.

- [ ] **Step 3: Implement.**

  After `ON_FILTER = "-*," + CATEGORY`, add:

```python
# Intl recipe (docs/observer/README.md): V8 entry slices plus runtime call stats; and the
# same with the stats category left off, which must read as blind, not as zero calls
INTL_FILTER = ON_FILTER + ",v8,disabled-by-default-v8.runtime_stats"
NO_RCS_FILTER = ON_FILTER + ",v8"
INTL_ROWS = ("Builtin_DateTimeFormatConstructor", "Builtin_DateTimeFormatPrototypeResolvedOptions",
             "Builtin_DateTimeFormatSupportedLocalesOf")
```

  In `PROBE`, insert these lines after the first `for` loop's closing `}` (the one that reads `document.cookie; document.title;`) and before `const gl = ...`:

```javascript
  const dtfs = [];
  for (let i = 0; i < K; i++) { dtfs.push(new Intl.DateTimeFormat()); Intl.DateTimeFormat.supportedLocalesOf(['en']); }
  for (const d of dtfs) d.resolvedOptions();
```

  Replace `WORKER` with:

```python
WORKER = ("const d = []; for (let i = 0; i < %(k)d; i++) { navigator.hardwareConcurrency; "
          "d.push(new Intl.DateTimeFormat()); Intl.DateTimeFormat.supportedLocalesOf(['en']); } "
          "for (const f of d) f.resolvedOptions(); postMessage('w');")
```

  After `hot_rows`, add:

```python
def intl_rows(ic, site, scripts, k, bump):
    """Exact counts of the probe's three Intl built-ins per entry script (main, worker)."""
    rows = []
    for script in scripts:
        for name in INTL_ROWS:
            got = (ic or {}).get((site, script, name), 0)
            rows.append((got == k + bump, f"{name} site={site} script={script}: {got} (want {k + bump})"))
    return rows


def blind_arm(events):
    """(ok, V8 entry slices): v8 traced without runtime_stats must report blind, and V8
    slices must be present, or the arm measured nothing."""
    if events is None:
        return False, None
    n = sum(e.get("name") in observe_report.V8_ENTRY for e in events)
    return observe_report.intl_counts(events) is None and n > 0, n
```

  In `main`:

  1. In the `--timing` branch, replace the loop with:

```python
        for label, cats in (("off", "blink,loading"), ("on", ON_FILTER), ("intl", INTL_FILTER)):
            _, res, trace = run("timing.html", cats)
            size = os.path.getsize(trace) if os.path.exists(trace) else None
            print(f"timing {label}: {res} trace_bytes={size}")
```

  2. Change the probe run to `events, res, trace = run("probe.html", INTL_FILTER)`.
  3. After the `Document.title` row (`rows.append((title == 0 + bump, ...))`), add:

```python
    label = observe_report.script_label
    rows += intl_rows(observe_report.intl_counts(events), top,
                      (label(probe), label(f"{main_origin}/worker.js")), K, bump)
```

  4. After the existing off-arm `rows.append(...)`, add:

```python
    rows.append(((off_events is not None and observe_report.intl_counts(off_events) is None) == (not red),
                 "off arm: report says Intl blind (want blind)"))
    nr_events, _, _ = run("probe.html", NO_RCS_FILTER)
    nr_ok, nr_slices = blind_arm(nr_events)
    rows.append((nr_ok == (not red), f"v8 on, runtime_stats off: Intl blind with {nr_slices} V8 entry "
                 "slices (want blind, >0 slices)"))
```

  5. In the module docstring:
     - replace the `on` line with `on     Intl recipe: every row below must match exactly (probe page with its worker and Intl calls, then the hot page for V8 fast API calls)`;
     - add after the `off` lines: `  no-rcs v8 traced without runtime_stats: the report must say Intl blind, with V8 slices present`;
     - change the `--timing` line to `  --timing  prints call timings and trace sizes with the category off, on, and on with the Intl recipe (numbers, no verdict)`.

- [ ] **Step 4: Run them and see them pass.**

  Run: `python3 -m pytest -q scripts/test_verify_observe.py scripts/test_observe_report.py`

  Expected: all pass.

- [ ] **Step 5: Commit.**

  Message: `test(observer): verify Intl counts and the blind arms` + Co-Authored-By.

```bash
git add scripts/verify_observe.py scripts/test_verify_observe.py
git commit -F <scratchpad>/d-commit-verify.txt
```

---

### Task 4: Box evidence: GREEN, RED and timing on the RCS build (controller, on the box)

The controller runs this task. It needs no lock: the task builds nothing, and verifies are not builds. It must not run while CI or another session runs content_shell verifies, so check `pgrep -f content_shell` first.

**Files:** none in the repo. Scratch is `/home/lang/observe-D/verify/`.

**Interfaces:**
- Consumes: Task 1's box build, plus the Task 2 and Task 3 files at branch HEAD.
- Produces, for Task 5 and the PR body:
  - the GREEN tally line;
  - the RED tally line;
  - the three timing lines with trace sizes.

- [ ] **Step 1: Stage a private verify dir.** Do not touch `/home/lang/camoucrome-verify`, which belongs to CI.

  - Base64 a script that does `mkdir -p /home/lang/observe-D/verify && cp /home/lang/camoucrome-verify/*.py /home/lang/observe-D/verify/`.
  - Write the branch's `scripts/observe_report.py` and `scripts/verify_observe.py` there through sshgate `stdin` (`cat > path`). Pass the file contents as stdin, one call per file.
  - Compare the sha256 against the Mac's `shasum -a 256`.

- [ ] **Step 2: GREEN.**

  Run: `cd /home/lang/observe-D/verify && /home/lang/camoucrome-verify/venv/bin/python3 verify_observe.py > /home/lang/observe-D/green.log 2>&1; tail -30 /home/lang/observe-D/green.log`

  Expected: `25/25 PASS`. The 6 Intl rows read `... : 3 (want 3)`. Both blind rows PASS, and the no-rcs arm shows more than 0 slices.

  If an Intl row reads 0 while other rows pass, the parser's shape or attribution is wrong. In that case:
  1. Dump the `(site, script, name)` keys of `intl_counts`.
  2. Rule on the fix.
  3. Fix it in Task 2's code with a fixture test.
  4. Re-run.

- [ ] **Step 3: RED.**

  Run: `... verify_observe.py --red > /home/lang/observe-D/red.log 2>&1; tail -3 /home/lang/observe-D/red.log`

  Expected: `0/25 PASS (RED mode: expected failures)`. A GREEN run is trusted only after this.

- [ ] **Step 4: Timing and size.**

  Run: `... verify_observe.py --timing`, three times.

  Record each run's `timing off|on|intl` lines (ms and `trace_bytes`) in the ledger.

  The spec measures trace size on the verify probe. This plan measures it on `timing.html`, through the same `run()`. The comparison is the same (default recipe against Intl recipe, same page), so `--timing` gives both numbers in one command.

- [ ] **Step 5: Unit tests on the box venv.**

  Run `/home/lang/camoucrome-verify/venv/bin/python3 -m pytest -q test_observe_report.py test_verify_observe.py`. Copy both test files into the private dir first. Expected: all pass.

---

### Task 5: Docs and the Windows launcher switch

**Files:**
- Modify: `docs/observer/README.md`
  - "Build" (lines 9-16);
  - after "Run" (after line 31): an Intl recipe;
  - line 47: row count;
  - "What it cannot see": the first bullet;
  - "Detectability": an Intl row.
- Modify: `docs/observer/followups.md`
  - "Out of scope for phase 1": the phase 2 bullet;
  - "Open": a Windows rebuild bullet.
- Modify: `docs/superpowers/specs/2026-10-06-tracking-observer-design.md`
  - "Not observable": the first bullet.
- Modify: `docs/superpowers/specs/repin-runbook.md`
  - step 6 (line 323).
- Modify: `scripts/windows/observe-recon.ps1`
  - lines 1-11: usage and param;
  - lines 96-101: argv.

**Interfaces:**
- Consumes: Task 1's step count and wall time; Task 4's tallies and timing lines.

- [ ] **Step 1: README.**

  In "Build", replace the arg block and its first sentence with:

```markdown
Add to the out dir's `args.gn` (never to `settings/build-args.gn`):

    camou_observe = true
    v8_enable_runtime_call_stats = true

The second arg compiles in V8's runtime call stats, which the Intl recipe below
reads; it rebuilds V8, not Blink (box, 2026-10-13: <N> steps, <T> min).
```

  After the paragraph on the `-*,` prefix, add:

```markdown
**Intl recipe.** To also count Intl built-ins (`new Intl.DateTimeFormat`,
`resolvedOptions`, the `supportedLocalesOf` family, `toLocale*`), record with

    --trace-startup=-*,disabled-by-default-camou.observe,v8,disabled-by-default-v8.runtime_stats

The report's "V8 built-ins (Intl)" section then lists calls per site, entry
script and built-in. The entry script is the Blink `v8.run` script around the
V8 slice, else the one script of the observer events inside that slice, else
`(unknown)`: event handlers, timers, promise callbacks and module bodies have
no entry script of their own. Without the recipe, or on a build without the
arg, the section says `Intl: blind`, never zero. The recipe is opt-in because
`v8` is a busy default category and the call stats time every built-in call
(see Detectability). On Windows: `observe-recon.ps1 ... -Intl`.
```

  Change the verify row-count sentence to:
  "`verify_observe.py` has 25 rows, including a hot loop of 100 000 `fillRect` calls and `lineWidth` sets that V8 runs on its fast API path, three Intl built-ins counted on the page and in its worker, and two arms that must report Intl blind."

  Replace the first "What it cannot see" bullet with:
  `- V8 built-ins \`Date.prototype.getTimezoneOffset\` (a CSA builtin) and \`Math\`; Intl only with the Intl recipe.`

  Under "Detectability", after the existing numbers, add a short paragraph with Task 4's three `--timing` runs. Give the `ua_200k_ms`, `todataurl_300_ms` and `trace_bytes` ranges for `on` against `intl`.

- [ ] **Step 2: followups.md.**

  - Remove the phase 2 bullet from "Out of scope for phase 1".
  - Add to "Open": `- **Rebuild the Windows \`out\Observe\` with \`v8_enable_runtime_call_stats = true\`** (and copy \`scripts/windows/observe-recon.ps1\` to \`D:\camou-win\observe\recon.ps1\`) before an Intl recon arm; needs canvas's agreement for the native build window.`
  - Skip that second bullet if Task 6 completed.

- [ ] **Step 3: Phase-1 spec.**

  In "Not observable", replace the first bullet's text with:

```markdown
- V8 built-ins: `Date.prototype.getTimezoneOffset` (a CSA builtin, `TFJ` in
  `v8/src/builtins/builtins-definitions.h`) and `Math` stay blind. `Intl.*`
  is counted since 2026-10-13 through V8 runtime call stats
  (`docs/superpowers/specs/2026-10-13-observer-intl-rcs-design.md`).
```

- [ ] **Step 4: Re-pin runbook, step 6.**

  Append to the step-6 bullet:
  "then append the observer args from `docs/observer/README.md` (`camou_observe = true`, `v8_enable_runtime_call_stats = true`): CI's `out/Default` is an observer build, and its `verify_observe.py` fails its Intl rows without the second arg."

- [ ] **Step 5: observe-recon.ps1.**

  - Change the usage line to `# Usage: recon.ps1 -Site facebook|instagram|threads -Arm 1|2|3|4 [-Force] [-Intl]`.
  - Add `[switch]$Intl,` after `[switch]$Force,`.
  - Replace the hardcoded `'--trace-startup=-*,disabled-by-default-camou.observe',` element in `$fl` with `"--trace-startup=$cats",`.
  - Precede the `$fl = @(` line with:

```powershell
# -Intl adds V8 entry slices and runtime call stats (needs v8_enable_runtime_call_stats = true)
$cats = '-*,disabled-by-default-camou.observe'
if ($Intl) { $cats += ',v8,disabled-by-default-v8.runtime_stats' }
```

  Check: `grep -n "trace-startup=" scripts/windows/observe-recon.ps1` shows one line, `"--trace-startup=$cats",`.

  The README says the `.ps1` files are byte-exact copies of the host's. Add "(`observe-recon.ps1` gained `-Intl` on 2026-10-13; the host copy is updated with the `out\Observe` rebuild)" to that README sentence, unless Task 6 completed.

- [ ] **Step 6: Re-run the tests and commit.**

  Run `python3 -m pytest -q scripts/test_observe_report.py scripts/test_verify_observe.py`. Expected: all pass.

  Message: `docs(observer): Intl recipe, RCS build arg, and the re-pin step` + Co-Authored-By.

```bash
git add docs/observer/README.md docs/observer/followups.md docs/superpowers/specs/2026-10-06-tracking-observer-design.md docs/superpowers/specs/repin-runbook.md scripts/windows/observe-recon.ps1
git commit -F <scratchpad>/d-commit-docs.txt
```

---

### Task 6 (conditional): Windows `out\Observe` rebuild (controller)

Run this task only if canvas agrees to a native build window tonight and Task 4 is GREEN. Otherwise skip it and leave Task 5's followups bullet in place.

- [ ] **Step 1: Ask canvas.**

  Ask whether the native Windows tree may build now under `build_lock.sh` owner `observe-D-win`. Wait for a yes.

- [ ] **Step 2: Edit `D:\camou-win\chromium\src\out\Observe\args.gn`.**

  Add `v8_enable_runtime_call_stats = true` after `camou_observe = true`. Run `gn gen`, then build `chrome` detached (memory `windows-native-build.md`: launch via Win32_Process). Record the non-zero steps and the wall time.

- [ ] **Step 3: Copy the launcher and the report.**

  Copy `scripts/windows/observe-recon.ps1` to `D:\camou-win\observe\recon.ps1` and `scripts/observe_report.py` to `D:\camou-win\observe\observe_report.py`. Compare the sha256 against the repo.

- [ ] **Step 4: Smoke test.**

  Do not touch Meta sites. Launch `out\Observe\chrome.exe` with the Intl recipe on `about:blank`, then on a local `data:` page that calls `new Intl.DateTimeFormat().resolvedOptions()` once. Close it normally. Run the report.

  Expected: the Intl section lists `Builtin_DateTimeFormatConstructor` and `Builtin_DateTimeFormatPrototypeResolvedOptions`, each with count 1.

- [ ] **Step 5: Release the lock and message canvas.** Then drop the conditional sentences from Task 5's README and followups, and amend that commit with `--fixup` + autosquash.

---

### Task 7: PR (controller)

- [ ] **Step 1:** `git push -u origin observer-d-intl-rcs`.
- [ ] **Step 2:** Run `gh pr create`.
  - Title: `observer: Intl built-in counts via V8 runtime call stats (phase 2)`.
  - The body carries the evidence:
    - Task 1's args diff, step count, wall time and sync gate rc;
    - Task 4's GREEN `25/25 PASS` tail and RED `0/25` tail;
    - the timing lines;
    - the pytest lines;
    - Task 6's result, or "Windows rebuild: not done, followups bullet".
  - Note the landing-order fact: box `out/Default` already has the arg, so CI's verify passes after merge.
  - End the body with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- [ ] **Step 3:** Do not merge. Report the PR URL to the owner. Merging needs their approval.
