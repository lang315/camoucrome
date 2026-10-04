# Step 2 measurement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One command on the Windows host runs the fork and stock Chrome 154
through the same client and argv, headed and headless, across six probes, and
writes tables of every labelled difference, plus a committed 154 baseline.

**Architecture:** `scripts/step2_rows.py` is the pure half (rows, labels, argv
and version checks, run comparison, tables) and is unit-tested in CI.
`scripts/measure_step2.py` is the browser half and runs only on the host: it
launches both arms through `camoucrome.launch()` and turns each probe into rows.
`scripts/oracle_rules.py` takes `SHAPE_ONLY` and `flatten` out of
`verify_host_oracle.py` so both scripts share them. This narrows the spec on
purpose. The spec moves `KNOWN` and `KNOWN_PREFIX` as well, but this plan keeps
them in `verify_host_oracle.py`. They excuse artefacts of comparing the fork
against a *committed* baseline: the box has no mouse, no GPU and no HEVC
decoder, and the probe adds an init-script marker. When both arms run live on
the same host, those artefacts cannot occur. HEVC there is a real difference
and must show as `unexpected`.

**Tech Stack:** Python 3.12, patchright 1.62.3 (host client venv), pytest,
the `camoucrome` client, PowerShell on the host through the sshgate MCP.

**Spec:** `docs/superpowers/specs/2026-10-04-step2-measurement-design.md`

## Global Constraints

- Both arms go through the same `camoucrome.launch()` call. Only the executable, the config and what the config implies differ.
  - The fork arm passes the generated identity's `launch.window` and `launch.dpr`, because a real client does. Without them, `screen.*` and the window sizes contradict each other, and detectors would score that harness artefact as a fork difference.
  - The control passes neither, so it runs at stock defaults.
- Argv parity: the browser argv of the two arms may differ only in `--accept-lang=`, `--user-data-dir=`, `--window-size=` and `--force-device-scale-factor=` (all identity-derived), plus a planted RED arg on the fork arm. This widens the spec's allow-list (which named `--accept-lang=` only) for the reason above. Neither arm gets `--use-angle=swiftshader` or `--no-sandbox`.
- Both executables must report the pin's version (`upstream.env` `CHROMIUM_TAG`, today `154.0.8037.93`) or the run stops before measuring.
- Never `add_init_script` and never send `Runtime.enable`: read the page through the DOM (`#o` text, `document.body.innerText`) with patchright.
- A detector that does not settle scores `UNMEASURED`, never a difference.
- Screenshots and raw detector text stay in the run directory. Only `rows.json` and `tables.md` are committed.
- `scripts/test_*.py` run in CI (`pytest -q client/python/tests scripts/`) without patchright or a browser, so `step2_rows.py` and `oracle_rules.py` import nothing from patchright, and `measure_step2.py` imports patchright only inside `main()`.
- RED-first: no probe's "no difference" counts until the same probe was seen to report a planted difference.
- The host run holds the build lock (owner `step2`). No Chromium build is started by this plan.
- Branch `step2/measurement` (already holds the spec, `b2e88f6`). Git author `Lãng <30039912+lang315@users.noreply.github.com>`. Commit bodies end with the session's attribution lines.
- Host paths: client venv `D:\camou-win\client-venv\Scripts\python.exe`, tree `D:\camou-win\tree` (the client is `pip install -e` from it), fork `D:\camou-win\chromium\src\out\Release\chrome.exe`, stock `C:\Program Files\Google\Chrome\Application\chrome.exe`.

## File Structure

| File | Responsibility |
|---|---|
| `scripts/oracle_rules.py` (new) | `SHAPE_ONLY`, `flatten`: the oracle's identity- and machine-bound leaves, shared |
| `scripts/verify_host_oracle.py` (modify) | imports the two names instead of defining them |
| `scripts/step2_rows.py` (new) | pure: `label_rows`, `argv_problems`, `version_problems`, `network_rows`, `stability_rows`, `link_rows`, `parse_tabbed`, `parse_colon`, `line_diff`, `compare_runs`, `render_tables`, the `VOLATILE`/`EXPECTED` tables |
| `scripts/test_step2_rows.py` (new) | unit tests for all of the above |
| `scripts/measure_step2.py` (new) | host runner: arms, preconditions, six probes, `run`/`compare`/`tables` |
| `scripts/fixtures/step2/peet.json` (new) | one real `tls.peet.ws/api/all` response, for `network_rows` |
| `docs/superpowers/measurements/2026-10-step2-baseline.md` (new) | RED evidence, the baseline tables, findings |
| `docs/superpowers/measurements/step2-154/` (new) | the committed `rows.json` and `tables.md` of the baseline run |
| `docs/superpowers/plans/2026-10-02-long-term-roadmap.md` (modify) | step 2 status, backlog re-rank |

## Host procedure (used by Tasks 3–7)

Run every host command through the sshgate MCP (PowerShell). Bash on WSL
goes through a base64 script file (`/tmp/x.sh`) because PowerShell mangles
`$`, `$(...)` and quotes.

1. **Push and copy the branch.**
   - On the Mac: `git push -u origin step2/measurement`.
   - In WSL:
     ```bash
     R=/home/lang/actions-runner/_work/camoucrome/camoucrome
     git -C $R fetch -q origin step2/measurement
     git -C $R archive FETCH_HEAD > /tmp/step2-tree.tar
     git -C $R rev-parse FETCH_HEAD
     ```
   - On Windows:
     ```powershell
     tar -xf \\wsl.localhost\Ubuntu-24.04\tmp\step2-tree.tar -C D:\camou-win\tree
     Set-Content D:\camou-win\tree.commit <sha>
     ```
2. **Take the lock.**
   ```powershell
   wsl -u lang -e bash /home/lang/camoucrome-client/scripts/build_lock.sh acquire step2
   ```
   It must print that the lock was acquired. If another holder is named, stop and wait.
3. **Environment for every run.**
   ```powershell
   $env:CAMOU_CLIENT='D:\camou-win\tree'
   $env:CAMOU_FORK_EXE='D:\camou-win\chromium\src\out\Release\chrome.exe'
   $env:PLAYWRIGHT_NODEJS_PATH='D:\camou-win\client-venv\Lib\site-packages\patchright\driver\node.exe'
   $py='D:\camou-win\client-venv\Scripts\python.exe'
   cd D:\camou-win\tree\scripts
   ```
4. **Long runs go detached.** A full run is longer than one MCP call. Start it with `Invoke-CimMethod Win32_Process Create` of `powershell -ExecutionPolicy Bypass -File <ps1>`, where the `.ps1` sets the environment, runs the command and redirects output to `D:\camou-win\step2\<name>.log`. Then poll the log.
5. **Release the lock** when a task's host work ends:
   ```powershell
   wsl -u lang -e bash /home/lang/camoucrome-client/scripts/build_lock.sh release step2
   ```

---

### Task 1: Share the oracle's shape rules

**Files:**
- Create: `scripts/oracle_rules.py`
- Modify: `scripts/verify_host_oracle.py:29-37` (`SHAPE_ONLY`), `:100-106` (`flatten`)
- Test: `scripts/test_verify_host_oracle.py` (existing, must stay green); `scripts/test_step2_rows.py` (first test)

**Interfaces:**
- Produces: `oracle_rules.SHAPE_ONLY: set[str]` (the exact set now in `verify_host_oracle.py`), `oracle_rules.flatten(v, prefix="") -> dict[str, object]`.

- [ ] **Step 1: Write the failing test**

Create `scripts/test_step2_rows.py`:

```python
"""step2_rows and oracle_rules without a browser (roadmap step 2)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_oracle_rules_shared():
    import oracle_rules
    assert "screen.width" in oracle_rules.SHAPE_ONLY and "audioFp" in oracle_rules.SHAPE_ONLY
    assert oracle_rules.flatten({"a": {"b": 1, "c": [2]}, "d": None}) == {"a.b": 1, "a.c": [2], "d": None}
```

- [ ] **Step 2: Run it and see it fail**

Run: `python3 -m pytest -q scripts/test_step2_rows.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'oracle_rules'`.

- [ ] **Step 3: Move the two names**

Create `scripts/oracle_rules.py` with this docstring:

```python
"""The host oracle's comparison vocabulary, shared by verify_host_oracle.py
(the fork against the committed stock baseline) and step2_rows.py (the fork
against stock live, roadmap step 2). Pure: no browser, no host."""
```

Then add:

- `SHAPE_ONLY`: cut the whole assignment, with its comment line `# Values that legitimately follow the identity or the machine: compare type only.`, from `verify_host_oracle.py:29-37` and paste it byte for byte.
- `flatten`: cut the function from `verify_host_oracle.py:100-106` and paste it byte for byte.

In `verify_host_oracle.py`, put this after the `import capture_host_oracle as cap  # noqa: E402` line:

```python
from oracle_rules import SHAPE_ONLY, flatten  # noqa: E402
```

- [ ] **Step 4: Run both test files**

Run: `python3 -m pytest -q scripts/test_step2_rows.py scripts/test_verify_host_oracle.py`
Expected: all pass. `test_verify_host_oracle.py`'s count must be unchanged from before the move. Run it on `origin/main` first if the number is not known.

- [ ] **Step 5: Commit**

```bash
git add scripts/oracle_rules.py scripts/verify_host_oracle.py scripts/test_step2_rows.py
git commit -m "refactor(oracle): SHAPE_ONLY and flatten into oracle_rules for step 2"
```

---

### Task 2: The pure half, `step2_rows.py`

**Files:**
- Create: `scripts/step2_rows.py`, `scripts/fixtures/step2/peet.json`
- Test: `scripts/test_step2_rows.py`

**Interfaces:**
- Consumes: `oracle_rules.SHAPE_ONLY`, `oracle_rules.flatten`.
- Produces:
  - `MODES = ("headed", "headless")`, `ARMS = ("control", "fork")`
  - `VOLATILE: dict[str, str]` (row name or prefix to reason), `EXPECTED: dict[str, str]`, `ARGV_ALLOWED: tuple[str, ...]`, `VOLATILE_LINES: list[str]` (regexes)
  - `label_rows(control: dict, fork: dict) -> list[tuple[name, control_value, fork_value, label, reason]]`, where label is one of `expected|volatile|unexpected|unmeasured`
  - `argv_problems(control_argv: list[str], fork_argv: list[str], allowed=ARGV_ALLOWED) -> list[str]`
  - `version_problems(versions: dict[str, str], pin: str) -> list[str]`
  - `network_rows(data: dict) -> dict`, `stability_rows(a: dict, b: dict) -> dict`, `link_rows(a: dict, b: dict) -> dict`
  - `parse_tabbed(text) -> dict`, `parse_colon(text) -> dict`, `PARSERS = {"sannysoft": parse_tabbed, "creepjs": parse_colon}`
  - `line_diff(control_text, fork_text) -> (list[str], list[str])`
  - `compare_runs(doc_a: dict, doc_b: dict) -> list[tuple[path, a, b]]`
  - `render_tables(doc: dict, texts: dict[tuple[site, mode], tuple[str|None, str|None]]) -> str`
  - The run document `doc` is `{"run": str, "versions": {arm: str}, "argv": {arm: list}, "flags": dict, "rows": {probe: {arm: {mode: dict|None}}}, "errors": {"probe/arm/mode": str}}`.

- [ ] **Step 1: Capture the network fixture**

Run on the Mac:

```bash
mkdir -p scripts/fixtures/step2
curl -s --http2 https://tls.peet.ws/api/all | python3 -m json.tool > scripts/fixtures/step2/peet.json
python3 -c "import json;d=json.load(open('scripts/fixtures/step2/peet.json'));print(sorted(d), sorted(d.get('tls',{})), sorted(d.get('http2',{})))"
```

Expected:
- top-level keys include `http_version`, `tls`, `http2` and `user_agent`;
- `tls` has `ja3` and `ja4`;
- `http2` has `akamai_fingerprint` and `sent_frames`, where one frame has `frame_type == "HEADERS"` and a `headers` list of `"name: value"` strings.

If a name differs, use the fixture's name in `network_rows` and in its test below, and record the difference in the commit message. This fixture holds the Mac's IP address: replace the value of `ip` (and any `ip` inside `tcpip`) with `"0.0.0.0"` before committing.

- [ ] **Step 2: Write the failing tests**

Append to `scripts/test_step2_rows.py`:

```python
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


def test_argv_parity_flags_extra_arg():
    c = ["chrome.exe", "--no-first-run"]
    f = ["chrome.exe", "--no-first-run", "--use-angle=swiftshader"]
    assert r.argv_problems(c, f) == ["fork only: --use-angle=swiftshader"]


def test_argv_parity_refuses_unread_argv():
    assert r.argv_problems([], ["chrome.exe"]) == ["argv not read: control=0 fork=1 elements"]


def test_version_precondition():
    assert r.version_problems({"control": "154.0.8037.93", "fork": "154.0.8037.93"}, "154.0.8037.93") == []
    assert r.version_problems({"control": "156.0.1.1", "fork": "154.0.8037.93"}, "154.0.8037.93") == [
        "control is 156.0.1.1, the pin is 154.0.8037.93"]


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
```

- [ ] **Step 3: Run them and see them fail**

Run: `python3 -m pytest -q scripts/test_step2_rows.py`
Expected: `test_oracle_rules_shared` passes. Every other test fails with `ModuleNotFoundError: No module named 'step2_rows'`.

- [ ] **Step 4: Write `scripts/step2_rows.py`**

```python
"""Roadmap step 2, the pure half: rows, their labels, the argv and version
preconditions, run-to-run comparison and the tables
(docs/superpowers/specs/2026-10-04-step2-measurement-design.md). No browser,
no host: test_step2_rows.py runs it in CI. measure_step2.py is the browser half."""
import collections
import json
import re

from oracle_rules import SHAPE_ONLY, flatten  # noqa: F401  (flatten is re-exported for measure_step2)

MODES = ("headed", "headless")
ARMS = ("control", "fork")
ABSENT = "<absent>"
UNMEASURED = "UNMEASURED"

# Row name (or dotted prefix) -> why it changes between runs of the same arm.
# Calibrated by the null runs of Task 7; every entry carries its reason.
VOLATILE = {
    "net.ja3": "Chrome permutes its TLS extension order per connection",
}
# Row name (or dotted prefix) -> why the fork's value differs from stock's by design.
EXPECTED = {
    "net.user_agent": "the identity's User-Agent",
    "link": "a record of what two profiles share, not a fork-vs-control finding",
}
# Oracle leaves compared by type only: a value difference is the identity's or the machine's.
SHAPE = {f"oracle.{k}": "identity- or machine-bound; compared by type" for k in SHAPE_ONLY}
# Identity-derived flags the client adds to the fork arm only (launcher.build_args).
ARGV_ALLOWED = ("--accept-lang=", "--user-data-dir=", "--window-size=", "--force-device-scale-factor=")
# Regexes over detector text lines that change between runs (clock, IP, session ids). Task 7 calibrates.
VOLATILE_LINES = []


def _reason(name, table):
    return next((why for k, why in table.items() if name == k or name.startswith(k + ".")), None)


def label_rows(control, fork):
    """Every row whose value differs between the arms, sorted by name, as
    (name, control value, fork value, label, reason). A row missing on one side
    reads ABSENT. A detector that did not settle is `unmeasured`, never a difference."""
    out = []
    for name in sorted(set(control) | set(fork)):
        c, f = control.get(name, ABSENT), fork.get(name, ABSENT)
        if c == f:
            continue
        site = ".".join(name.split(".")[:2])
        if UNMEASURED in (c, f) or UNMEASURED in (control.get(site), fork.get(site)):
            out.append((name, c, f, "unmeasured", "a detector page did not settle"))
        elif _reason(name, VOLATILE):
            out.append((name, c, f, "volatile", _reason(name, VOLATILE)))
        elif _reason(name, SHAPE):
            same = type(c) is type(f)
            out.append((name, c, f, "expected" if same else "unexpected", _reason(name, SHAPE) if same else "type changed"))
        elif _reason(name, EXPECTED):
            out.append((name, c, f, "expected", _reason(name, EXPECTED)))
        else:
            out.append((name, c, f, "unexpected", ""))
    return out


def argv_problems(control_argv, fork_argv, allowed=ARGV_ALLOWED):
    """Differences between the two browser argvs outside `allowed` prefixes.
    argv[0] (the executable) is not compared. An unread argv is a problem: an
    empty list would otherwise compare equal to nothing at all."""
    if not control_argv or not fork_argv:
        return [f"argv not read: control={len(control_argv)} fork={len(fork_argv)} elements"]
    keep = lambda argv: [a for a in argv[1:] if not a.startswith(tuple(allowed))]  # noqa: E731
    c, f = keep(control_argv), keep(fork_argv)
    return [f"control only: {a}" for a in c if a not in f] + [f"fork only: {a}" for a in f if a not in c]


def version_problems(versions, pin):
    return [f"{arm} is {v}, the pin is {pin}" for arm, v in versions.items() if v != pin]


def network_rows(data):
    """tls.peet.ws/api/all -> rows. Header NAMES in sent order; values the identity sets stay out."""
    tls, h2 = data.get("tls") or {}, data.get("http2") or {}
    headers = next((f.get("headers") for f in h2.get("sent_frames") or [] if f.get("frame_type") == "HEADERS"), None) or []
    return {"net.http_version": data.get("http_version"), "net.ja4": tls.get("ja4"), "net.ja3": tls.get("ja3"),
            "net.akamai": h2.get("akamai_fingerprint"), "net.h2_order": [h.split(": ", 1)[0] for h in headers],
            "net.user_agent": data.get("user_agent")}


def stability_rows(first, second):
    """Two flattened oracle reports from one profile, launched twice."""
    keys = set(first) | set(second)
    return {"stab.compared": len(keys), "stab.changed": sorted(k for k in keys if first.get(k, ABSENT) != second.get(k, ABSENT))}


def link_rows(a, b):
    """Two flattened oracle reports from two profiles of one arm: the leaves they share."""
    return {"link.total": len(set(a) | set(b)), "link.shared": sorted(k for k in a if k in b and a[k] == b[k])}


def parse_tabbed(text):
    """sannysoft: its result tables give one row per line, cells tab-separated."""
    out = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.split("\t")]
        if len(cells) >= 2 and cells[0]:
            out[cells[0]] = " | ".join(cells[1:])
    return out


def parse_colon(text):
    """CreepJS: "label: value" lines; the first occurrence of a label wins."""
    out = {}
    for line in text.splitlines():
        k, sep, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if sep and k and v and len(k) <= 40:
            out.setdefault(k, v)
    return out


PARSERS = {"sannysoft": parse_tabbed, "creepjs": parse_colon}


def line_diff(control_text, fork_text):
    """(lines only the control shows, lines only the fork shows), as multisets,
    stripped, blank and VOLATILE_LINES-matching lines dropped."""
    def lines(t):
        return collections.Counter(s for s in (x.strip() for x in t.splitlines())
                                   if s and not any(re.search(p, s) for p in VOLATILE_LINES))
    c, f = lines(control_text), lines(fork_text)
    return sorted((c - f).elements()), sorted((f - c).elements())


def compare_runs(a, b):
    """Every row on which two runs disagree, outside VOLATILE, as (probe/arm/mode/row, a, b)."""
    out = []
    for probe in sorted(set(a["rows"]) | set(b["rows"])):
        for arm in ARMS:
            for mode in MODES:
                ra = (a["rows"].get(probe) or {}).get(arm, {}).get(mode) or {}
                rb = (b["rows"].get(probe) or {}).get(arm, {}).get(mode) or {}
                for name in sorted(set(ra) | set(rb)):
                    va, vb = ra.get(name, ABSENT), rb.get(name, ABSENT)
                    if va != vb and not _reason(name, VOLATILE):
                        out.append((f"{probe}/{arm}/{mode}/{name}", va, vb))
    return out


def _cell(v):
    s = json.dumps(v, ensure_ascii=False)
    return (s if len(s) <= 80 else s[:77] + "...").replace("|", "\\|")


def render_tables(doc, texts):
    """tables.md: per probe and mode, every labelled difference; the fork's shared
    leaves for linkability; detector line diffs from `texts[(site, mode)]`."""
    out = ["# Step 2 tables", "",
           f"Run `{doc['run']}`; control {doc['versions'].get('control')}, fork {doc['versions'].get('fork')}; "
           f"flags {json.dumps(doc.get('flags', {}))}.", ""]
    for probe, arms in doc["rows"].items():
        for mode in MODES:
            out.append(f"## {probe} / {mode}")
            c, f = (arms.get("control") or {}).get(mode), (arms.get("fork") or {}).get(mode)
            if c is None or f is None:
                errs = [v for k, v in doc.get("errors", {}).items() if k.startswith(f"{probe}/") and k.endswith(f"/{mode}")]
                out += [f"UNMEASURED: {'; '.join(errs) or 'no rows'}", ""]
                continue
            rows = label_rows(c, f)
            counts = collections.Counter(r[3] for r in rows)
            out.append(f"{len(rows)} differing rows: " + ", ".join(f"{n} {k}" for k, n in sorted(counts.items())))
            if rows:
                out += ["", "| row | control | fork | label | reason |", "|---|---|---|---|---|"]
                out += [f"| {n} | {_cell(cv)} | {_cell(fv)} | {lab} | {why} |" for n, cv, fv, lab, why in rows]
            if probe == "linkability":
                out += ["", f"Leaves the two fork profiles share ({len(f.get('link.shared', []))} of {f.get('link.total')}):",
                        "", ", ".join(f"`{k}`" for k in f.get("link.shared", []))]
            out.append("")
    for (site, mode), (ct, ft) in sorted(texts.items()):
        out.append(f"## detector text {site} / {mode}")
        if ct is None or ft is None:
            out += ["UNMEASURED", ""]
            continue
        co, fo = line_diff(ct, ft)
        out += [f"control only ({len(co)}):", *[f"- `{_cell(s)}`" for s in co], f"fork only ({len(fo)}):", *[f"- `{_cell(s)}`" for s in fo], ""]
    return "\n".join(out) + "\n"
```

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest -q scripts/test_step2_rows.py && python3 -m pytest -q client/python/tests scripts/`
Expected: every `test_step2_rows.py` test passes, and the full CI pytest command passes with no new failures.

- [ ] **Step 6: Commit**

```bash
git add scripts/step2_rows.py scripts/test_step2_rows.py scripts/fixtures/step2/peet.json
git commit -m "feat(step2): rows, labels, argv/version preconditions, run compare, tables"
```

---

### Task 3: The runner, its preconditions and the oracle probe

**Files:**
- Create: `scripts/measure_step2.py`

**Interfaces:**
- Consumes: everything Task 2 produces; `capture_host_oracle.page()`; `windows_verify_set.pin_tag`, `STOCK_APP`; `camoucrome.launch`, `camoucrome.SEED_KEYS`, `camoucrome.profile_seeds`, `camoucrome.per_instance_config`, `camoucrome.probe.browser_argv`, `camoucrome.gen.generate`, `camoucrome.launcher.remove_dir`.
- Produces: the CLI below, `PROBES` (a dict from name to `fn(pw, arm, mode, run) -> dict`), and `run.dir/rows.json`, `run.dir/tables.md`, `run.dir/raw/`. Tasks 4–6 add one function each to `PROBES`.

- [ ] **Step 1: Confirm the planted flag on the 154 tree**

In WSL:

```bash
grep -n '^ *name: "WebShare"' ~/chromium/src/third_party/blink/renderer/platform/runtime_enabled_features.json5
```

Expected: one match. Then `--disable-blink-features=WebShare` removes `navigator.share` and `canShare`. If there is no match, find the runtime feature that gates `navigator.share` in `third_party/blink/renderer/modules/webshare/navigator_share.idl` (`RuntimeEnabled=`), and use that name in every later step.

- [ ] **Step 2: Write `scripts/measure_step2.py`**

```python
#!/usr/bin/env python3
"""Roadmap step 2: the fork and stock Chrome through the same client and argv,
headed and headless, every differing row labelled
(docs/superpowers/specs/2026-10-04-step2-measurement-design.md).

Run on the Windows host in the client venv, holding the build lock (owner step2):
  python measure_step2.py run [--only oracle,noise,...] [--modes headed,headless]
                              [--null] [--plant ARG] [--fresh-seeds] [--two-colour]
  python measure_step2.py compare RUN_A RUN_B
  python measure_step2.py tables RUN
--null puts the control executable, unconfigured, in the fork arm: the noise floor.
--plant adds ARG to the fork arm only (a RED). --fresh-seeds draws new seeds per
launch in the stability probe (its RED). --two-colour makes the fork arm's noise
page draw two colours (its RED). The fork is CAMOU_FORK_EXE; the control is the
stock chrome.exe under CAMOU_STOCK_APP (default: the Program Files install)."""
import argparse
import contextlib
import datetime
import http.server
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import capture_host_oracle as cap  # noqa: E402
import step2_rows as rows  # noqa: E402
from windows_verify_set import STOCK_APP, pin_tag  # noqa: E402

PROBES = {}  # name -> fn(pw, arm, mode, run) -> {row: value}; filled below


class Arm:
    """`ident` is a whole camoucrome.gen result ({"config", "launch": {"window", "dpr"}}) or None (stock)."""
    def __init__(self, name, exe, ident, args=()):
        self.name, self.exe, self.ident, self.args = name, exe, ident, list(args)

    @property
    def config(self):
        return self.ident["config"] if self.ident else None

    def without_seeds(self):
        from camoucrome import SEED_KEYS
        return {k: v for k, v in self.config.items() if k not in SEED_KEYS}


def identity(seed):
    """The whole generated identity: the config AND the launch window/dpr a client passes with it."""
    from camoucrome.gen import generate
    return generate("windows", seed=seed)


def exe_version(path):
    p = subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"(Get-Item -LiteralPath '{path}').VersionInfo.ProductVersion"],
                       capture_output=True, text=True, timeout=60)
    return p.stdout.strip()


@contextlib.contextmanager
def serve(body):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}/"
    finally:
        srv.shutdown()


@contextlib.contextmanager
def opened(pw, arm, mode, user_data_dir=None, config="arm", ident=None):
    """`ident` overrides the arm's identity (linkability's second profile); `config`
    overrides only the config (stability's seeds), keeping the identity's window/dpr."""
    from camoucrome import launch
    ident = ident or arm.ident
    lo = ident["launch"] if ident else {}
    ctx = launch(pw, arm.exe, config=(ident["config"] if ident else None) if config == "arm" else config,
                 headless=mode == "headless", user_data_dir=user_data_dir, args=arm.args,
                 window=tuple(lo["window"]) if lo.get("window") else None, dpr=lo.get("dpr"))
    try:
        yield ctx
    finally:
        ctx.close()


def first_page(ctx):
    return ctx.pages[0] if ctx.pages else ctx.new_page()


def read_oracle(ctx, url):
    page = first_page(ctx)
    page.goto(url, wait_until="load")
    page.wait_for_function("document.getElementById('o').textContent !== ''", timeout=90000)
    return rows.flatten(json.loads(page.locator("#o").text_content()))


def probe_oracle(pw, arm, mode, run):
    with serve(cap.page().encode()) as url, opened(pw, arm, mode) as ctx:
        return {f"oracle.{k}": v for k, v in read_oracle(ctx, url).items()}


PROBES["oracle"] = probe_oracle


def argv_of(pw, arm):
    from camoucrome.probe import browser_argv
    with opened(pw, arm, "headless") as ctx:
        first_page(ctx).goto("about:blank")
        return browser_argv(arm.exe)


def run_cmd(a):
    from patchright.sync_api import sync_playwright
    client = os.environ.get("CAMOU_CLIENT", str(HERE.parent))
    stock = os.path.join(os.environ.get("CAMOU_STOCK_APP", STOCK_APP), "chrome.exe")
    fork_exe = stock if a.null else os.environ["CAMOU_FORK_EXE"]
    control = Arm("control", stock, None)  # stock: no config, no window/dpr (its defaults)
    fork = Arm("fork", fork_exe, None if a.null else identity(1), [a.plant] if a.plant else [])
    pin = pin_tag(client)
    versions = {"control": exe_version(control.exe), "fork": exe_version(fork.exe)}
    bad = rows.version_problems(versions, pin)
    if bad:
        sys.exit("precondition: " + "; ".join(bad))
    run_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + ("-null" if a.null else "") + ("-plant" if a.plant else "")
    out_dir = pathlib.Path(a.out or tempfile.gettempdir()) / "step2" / run_id
    (out_dir / "raw").mkdir(parents=True)
    run = argparse.Namespace(dir=out_dir, fresh_seeds=a.fresh_seeds, two_colour=a.two_colour)
    doc = {"run": run_id, "versions": versions, "argv": {}, "errors": {},
           "flags": {k: v for k, v in vars(a).items() if k in ("null", "plant", "fresh_seeds", "two_colour") and v},
           "rows": {}}
    with sync_playwright() as pw:
        doc["argv"] = {"control": argv_of(pw, control), "fork": argv_of(pw, fork)}
        bad = rows.argv_problems(doc["argv"]["control"], doc["argv"]["fork"],
                                 rows.ARGV_ALLOWED + ((a.plant,) if a.plant else ()))
        if bad:
            sys.exit("precondition, argv parity: " + "; ".join(bad))
        for probe in a.only.split(","):
            for mode in a.modes.split(","):
                for arm in (control, fork):
                    cell = doc["rows"].setdefault(probe, {}).setdefault(arm.name, {})
                    t0 = time.monotonic()
                    try:
                        cell[mode] = PROBES[probe](pw, arm, mode, run)
                    except Exception as exc:  # noqa: BLE001 - a failed cell is UNMEASURED, recorded
                        cell[mode] = None
                        doc["errors"][f"{probe}/{arm.name}/{mode}"] = f"{type(exc).__name__}: {str(exc)[:300]}"
                    print(f"{probe}/{arm.name}/{mode}: {'ok' if cell[mode] is not None else 'ERROR'} "
                          f"{time.monotonic() - t0:.0f}s", flush=True)
    (out_dir / "rows.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    write_tables(out_dir)
    print(f"run {out_dir}; {len(doc['errors'])} errors")
    return 1 if doc["errors"] else 0


def write_tables(out_dir):
    doc = json.loads((out_dir / "rows.json").read_text(encoding="utf-8"))
    texts = {}
    for site in rows.PARSERS.keys() | {"browserscan", "pixelscan"}:
        for mode in rows.MODES:
            got = [out_dir / "raw" / f"{site}-{arm}-{mode}.txt" for arm in rows.ARMS]
            if any(p.exists() for p in got):
                texts[(site, mode)] = tuple(p.read_text(encoding="utf-8") if p.exists() else None for p in got)
    (out_dir / "tables.md").write_text(rows.render_tables(doc, texts), encoding="utf-8")


def compare_cmd(a):
    docs = [json.loads((pathlib.Path(p) / "rows.json").read_text(encoding="utf-8")) for p in (a.run_a, a.run_b)]
    diffs = rows.compare_runs(*docs)
    for path, va, vb in diffs:
        print(f"DISAGREE {path}: {json.dumps(va)[:120]} vs {json.dumps(vb)[:120]}")
    print(f"{len(diffs)} rows disagree outside VOLATILE")
    return 1 if diffs else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--only", default=",".join(PROBES))
    r.add_argument("--modes", default=",".join(rows.MODES))
    r.add_argument("--out")
    r.add_argument("--null", action="store_true")
    r.add_argument("--plant")
    r.add_argument("--fresh-seeds", action="store_true")
    r.add_argument("--two-colour", action="store_true")
    c = sub.add_parser("compare")
    c.add_argument("run_a")
    c.add_argument("run_b")
    t = sub.add_parser("tables")
    t.add_argument("run_dir")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return run_cmd(a)
    if a.cmd == "compare":
        return compare_cmd(a)
    write_tables(pathlib.Path(a.run_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

A note on `--only`: its default lists every probe registered at import. Tasks 4–6 register theirs at module level, above `main`, so the default grows with them.

- [ ] **Step 3: Check the import is CI-safe**

Run: `python3 -c "import sys; sys.path.insert(0,'scripts'); import measure_step2; print(sorted(measure_step2.PROBES))"` then `python3 -m pytest -q client/python/tests scripts/`
Expected:
- The first prints `['oracle']`, and patchright is not imported.
- pytest passes.

- [ ] **Step 4: Commit and copy to the host**

```bash
git add scripts/measure_step2.py
git commit -m "feat(step2): measure_step2 runner, preconditions, oracle probe"
```

Then follow Host procedure steps 1–3.

- [ ] **Step 5: Precondition REDs on the host**

The two checks below are exit-code and message checks; neither launches a probe.

1. Version.

   ```powershell
   $env:CAMOU_FORK_EXE='D:\camou-win\chromium\src\out\Release\chrome.exe'
   & $py measure_step2.py run --only oracle --modes headless --out D:\camou-win\step2
   ```

   Read the first line. Then make the fork arm's version wrong on purpose: copy any exe whose `ProductVersion` is not the pin's to `D:\camou-win\step2\notpin.exe`. `powershell.exe` from `C:\Windows\System32\WindowsPowerShell\v1.0` works. Run again with `$env:CAMOU_FORK_EXE='D:\camou-win\step2\notpin.exe'`.

   Expected:
   - `sys.exit` with `precondition: fork is 10.0.…, the pin is 154.0.8037.93`, exit code 1;
   - no `rows.json` written.

2. Argv. Run with `--plant --use-angle=swiftshader` but temporarily drop `a.plant` from the allowed tuple, by editing the host copy only, and restore it after.

   Expected: `precondition, argv parity: fork only: --use-angle=swiftshader`.

   Restore the host copy from the tar.

- [ ] **Step 6: Oracle null run and planted RED on the host**

Runs inside the lock, detached (Host procedure step 4), one log each:

```powershell
& $py measure_step2.py run --only oracle --null --out D:\camou-win\step2
& $py measure_step2.py run --only oracle --null --plant=--disable-blink-features=WebShare --out D:\camou-win\step2
& $py measure_step2.py run --only oracle --out D:\camou-win\step2
```

Expected:
- **Null run:** `tables.md` shows, for both modes, 0 `unexpected` rows. Any row that does show is a same-binary difference between two launches. Record it in the ledger as a VOLATILE candidate for Task 7, with its value pair.
- **Planted run:** at least `oracle.nav.share` and `oracle.nav.canShare` show as `unexpected` (`"function"` against `"<absent>"` or `undefined`), in both modes.
- **Fork run:** no errors. In the **headed** column, the `oracle.gpu.*` leaves are present on both arms (no SwiftShader). In the headless column `requestAdapter()` may be null on both arms, because Chrome's own headless path self-adds SwiftShader (`settings/launcher.json`, `headless_self_added`). An equal null there is not a failure. Every `unexpected` row is written to the ledger as a finding. Do not fix anything in this plan.

If the window-key leaves (`oracle.windowKeys`, `oracle.windowNames`, `oracle.protoCounts.Window`) are equal across the fork run, rule 2 is measured on `chrome.exe`. Note it for the measurement doc.

- [ ] **Step 7: Release the lock** (Host procedure step 5).

---

### Task 4: Noise and network probes

**Files:**
- Modify: `scripts/measure_step2.py`. Add both probes after `PROBES["oracle"] = probe_oracle`.

**Interfaces:**
- Consumes: `opened`, `serve`, `first_page`, `rows.network_rows`.
- Produces: `PROBES["noise"]` rows `noise.canvas2d`, `noise.webgl`; `PROBES["network"]` rows from `rows.network_rows`.

- [ ] **Step 1: Confirm the TLS RED flag**

In WSL:

```bash
grep -rn '"ssl-version-max"' ~/chromium/src/components ~/chromium/src/chrome/common | head -3
```

Expected: one definition. If it is absent, use `--cipher-suite-blacklist=0x1301`. It changes the ClientHello's cipher list and so `ja4`. Grep `"cipher-suite-blacklist"` to confirm it the same way.

- [ ] **Step 2: Add the probes**

```python
NOISE_PAGE = b"""<!doctype html><title>noise</title><pre id="o"></pre><script>
const two=location.search.includes('two');
const distinct=d=>{const s=new Set();for(let i=0;i<d.length;i+=4)s.add(d[i]+','+d[i+1]+','+d[i+2]+','+d[i+3]);return s.size};
const c=document.createElement('canvas');c.width=c.height=64;const x=c.getContext('2d');
x.fillStyle='rgb(10,20,30)';x.fillRect(0,0,64,64);if(two){x.fillStyle='rgb(200,100,50)';x.fillRect(0,0,32,64)}
const out={canvas2d:distinct(x.getImageData(0,0,64,64).data)};
const g=document.createElement('canvas');g.width=g.height=64;const gl=g.getContext('webgl');
if(gl){gl.clearColor(10/255,20/255,30/255,1);gl.clear(gl.COLOR_BUFFER_BIT);if(two){gl.enable(gl.SCISSOR_TEST);gl.scissor(0,0,32,64);gl.clearColor(200/255,100/255,50/255,1);gl.clear(gl.COLOR_BUFFER_BIT)}
const p=new Uint8Array(64*64*4);gl.readPixels(0,0,64,64,gl.RGBA,gl.UNSIGNED_BYTE,p);out.webgl=distinct(p)}else out.webgl='no context';
document.getElementById('o').textContent=JSON.stringify(out);
</script>"""


def probe_noise(pw, arm, mode, run):
    """Solid fills read back: the control reads 1 colour; a fork reading more is a farbling tell."""
    two = "?two" if run.two_colour and arm.name == "fork" else ""
    with serve(NOISE_PAGE) as url, opened(pw, arm, mode) as ctx:
        page = first_page(ctx)
        page.goto(url + two, wait_until="load")
        page.wait_for_function("document.getElementById('o').textContent !== ''", timeout=30000)
        got = json.loads(page.locator("#o").text_content())
    return {"noise.canvas2d": got["canvas2d"], "noise.webgl": got["webgl"]}


PEET = "https://tls.peet.ws/api/all"


def probe_network(pw, arm, mode, run):
    """JA4, HTTP/2 SETTINGS and header order as a third party sees them (spec: the external echo service)."""
    with opened(pw, arm, mode) as ctx:
        page = first_page(ctx)
        page.goto(PEET, wait_until="load", timeout=60000)
        data = json.loads(page.evaluate("(document.querySelector('pre') || document.body).textContent"))
    (run.dir / "raw" / f"network-{arm.name}-{mode}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    return rows.network_rows(data)


PROBES["noise"] = probe_noise
PROBES["network"] = probe_network
```

- [ ] **Step 3: CI-safe import check**

Run: `python3 -c "import sys; sys.path.insert(0,'scripts'); import measure_step2; print(sorted(measure_step2.PROBES))"` and `python3 -m pytest -q client/python/tests scripts/`
Expected: `['network', 'noise', 'oracle']`; pytest passes.

- [ ] **Step 4: Commit and copy to the host** (Host procedure 1–3).

```bash
git add scripts/measure_step2.py
git commit -m "feat(step2): noise readback and network fingerprint probes"
```

- [ ] **Step 5: RED, then the fork, on the host**

```powershell
& $py measure_step2.py run --only noise,network --null --out D:\camou-win\step2
& $py measure_step2.py run --only noise,network --null --two-colour --plant=--ssl-version-max=tls1.2 --out D:\camou-win\step2
& $py measure_step2.py run --only noise,network --out D:\camou-win\step2
```

Expected:
- **Null run:**
  - `noise.canvas2d` and `noise.webgl` are `1` on both arms and show no difference;
  - `net.ja4` and `net.akamai` are equal;
  - at most `net.ja3` shows, labelled `volatile`.
- **Planted run:** the fork arm reads `noise.canvas2d: 2` and `noise.webgl: 2` (`unexpected`), and `net.ja4` differs (`unexpected`). If either noise row reads 1 under `--two-colour`, the probe cannot see a difference: stop and fix the page before reading any fork result.
- **Fork run:**
  - noise rows other than `1` are findings;
  - `net.ja4`, `net.akamai` and `net.h2_order` are expected equal to the control;
  - `net.user_agent` is `expected`.

  Record all of it in the ledger.

- [ ] **Step 6: Release the lock.**

---

### Task 5: Stability and linkability probes

**Files:**
- Modify: `scripts/measure_step2.py`. Add after the network probe.

**Interfaces:**
- Consumes: `read_oracle`, `serve`, `opened`, `identity`, `Arm.without_seeds`, `rows.stability_rows`, `rows.link_rows`, `camoucrome.profile_seeds`, `camoucrome.per_instance_config`, `camoucrome.launcher.remove_dir`.
- Produces: `PROBES["stability"]` rows `stab.compared` and `stab.changed`; `PROBES["linkability"]` rows `link.total` and `link.shared`.

- [ ] **Step 1: Add the probes**

```python
def probe_stability(pw, arm, mode, run):
    """One profile launched twice. Fork seeds come from the profile (profile_seeds),
    or fresh per launch under --fresh-seeds (the RED). The generated identity carries
    its own seeds, so they are dropped first or the RED could not change anything."""
    from camoucrome import per_instance_config, profile_seeds
    from camoucrome.launcher import remove_dir
    udd = tempfile.mkdtemp(prefix="camoucrome-step2-stab-")
    try:
        reports = []
        for _ in (1, 2):
            cfg = None if arm.config is None else {
                **arm.without_seeds(), **(per_instance_config() if run.fresh_seeds else profile_seeds(udd))}
            with serve(cap.page().encode()) as url, opened(pw, arm, mode, user_data_dir=udd, config=cfg) as ctx:
                report = read_oracle(ctx, url)
                # The oracle page keeps only deviceId LENGTHS, so mediaDevices:seed would be
                # invisible here. The ids themselves need the grant: without it Chrome lists
                # one entry per kind with an empty id.
                ctx.grant_permissions(["camera", "microphone"], origin=url)
                report["mediaDevices.ids"] = first_page(ctx).evaluate(
                    "navigator.mediaDevices.enumerateDevices().then(ds => ds.map(d => d.kind + ':' + d.deviceId + '/' + d.groupId))")
                reports.append(report)
    finally:
        remove_dir(udd)
    return rows.stability_rows(*reports)


def probe_linkability(pw, arm, mode, run):
    """Two profiles of one arm: fork identities from seeds 1 and 2, or two stock profiles."""
    reports = []
    for seed in (1, 2):
        ident = None if arm.ident is None else identity(seed)
        with serve(cap.page().encode()) as url, opened(pw, arm, mode, ident=ident) as ctx:
            reports.append(read_oracle(ctx, url))
    return rows.link_rows(*reports)


PROBES["stability"] = probe_stability
PROBES["linkability"] = probe_linkability
```

- [ ] **Step 2: CI-safe import check.** Same commands as Task 4 Step 3. Expected: `['linkability', 'network', 'noise', 'oracle', 'stability']`.

- [ ] **Step 3: Commit and copy to the host.**

```bash
git add scripts/measure_step2.py
git commit -m "feat(step2): relaunch stability and cross-profile linkability probes"
```

- [ ] **Step 4: RED, then the fork, on the host**

```powershell
& $py measure_step2.py run --only stability,linkability --null --out D:\camou-win\step2
& $py measure_step2.py run --only stability --fresh-seeds --out D:\camou-win\step2
& $py measure_step2.py run --only stability,linkability --out D:\camou-win\step2
```

Expected:
- **Null run:**
  - `stab.changed` is the same list on both arms. The leaves in it are a stock launch-to-launch volatility list: copy them into the ledger as VOLATILE candidates for Task 7.
  - The control's `link.shared` holds nearly every leaf. That presence is what makes the fork's shorter list mean something.
- **`--fresh-seeds` run:** the fork's `stab.changed` contains `canvas.text` or `canvas.shape` and `audioFp` (stability leaves carry no `oracle.` prefix), beyond the control's list. That is the stability RED.
  - It also contains `mediaDevices.ids`, **if** the control's ids are non-empty after the grant.
  - If every id is empty on the host, which happens when it has no camera or microphone and output devices stay hidden, the probe cannot see device IDs. Then the measurement doc says so, rather than claiming device-ID stability.
- **Fork run:**
  - the fork's `stab.changed` equals the control's (no canvas, audio or device-ID leaf);
  - `link.shared` is the linkability table, and it is expected to include `fonts.*` (the known 119-family list).

  Record both in the ledger.

- [ ] **Step 5: Release the lock.**

---

### Task 6: Public detectors

**Files:**
- Modify: `scripts/measure_step2.py`. Add after the linkability probe.

**Interfaces:**
- Consumes: `opened`, `first_page`, `rows.PARSERS`.
- Produces: `PROBES["detectors"]` rows: `det.<site>` = `"ok"` or `"UNMEASURED"`, plus `det.<site>.<key>` from the parsers; raw text and screenshots in `run.dir/raw/<site>-<arm>-<mode>.txt|png`.

- [ ] **Step 1: Add the probe**

```python
DETECTORS = {"sannysoft": "https://bot.sannysoft.com/", "creepjs": "https://abrahamjuliot.github.io/creepjs/",
             "browserscan": "https://www.browserscan.net/", "pixelscan": "https://pixelscan.net/"}


def settle(page, first_ms=10000, step_ms=3000, timeout_s=120):
    """The page's text once two reads 3 s apart agree, or None at the timeout."""
    page.wait_for_timeout(first_ms)
    prev, deadline = None, time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        text = page.evaluate("document.body.innerText")
        # Settled = no line changed outside VOLATILE_LINES: a page with a ticking
        # clock never reads byte-equal twice, and would otherwise never settle.
        if prev is not None and rows.line_diff(prev, text) == ([], []):
            return text
        prev = text
        page.wait_for_timeout(step_ms)
    return None


def probe_detectors(pw, arm, mode, run):
    out = {}
    for site, url in DETECTORS.items():
        with opened(pw, arm, mode) as ctx:
            page = first_page(ctx)
            try:
                page.goto(url, wait_until="load", timeout=60000)
                text = settle(page)
            except Exception:  # noqa: BLE001 - a page that does not load is not measured
                text = None
            if text is None:
                out[f"det.{site}"] = rows.UNMEASURED
                continue
            stem = run.dir / "raw" / f"{site}-{arm.name}-{mode}"
            stem.with_suffix(".txt").write_text(text, encoding="utf-8")
            page.screenshot(path=str(stem.with_suffix(".png")), full_page=True)
            out[f"det.{site}"] = "ok"
            out.update({f"det.{site}.{k}": v for k, v in rows.PARSERS.get(site, lambda t: {})(text).items()})
    return out


PROBES["detectors"] = probe_detectors
```

- [ ] **Step 2: CI-safe import check.** Same commands. Expected: six probe names.

- [ ] **Step 3: Commit and copy to the host.**

```bash
git add scripts/measure_step2.py
git commit -m "feat(step2): public detector probe (text diff, sannysoft and CreepJS rows)"
```

- [ ] **Step 4: Parser check on real text**

Run the null run first, then the planted RED:

```powershell
& $py measure_step2.py run --only detectors --null --out D:\camou-win\step2
& $py measure_step2.py run --only detectors --null --plant=--disable-blink-features=WebShare --out D:\camou-win\step2
```

After the null run, open `raw\sannysoft-control-headless.txt` and `raw\creepjs-control-headless.txt` and check that `rows.json` holds at least 10 `det.sannysoft.*` and 10 `det.creepjs.*` rows.

If a parser yields fewer rows, the page's text does not have the shape its docstring assumed. Copy 30 representative lines of that text into a new test in `scripts/test_step2_rows.py`, see it fail against the parser, fix the parser in `step2_rows.py`, see it pass, and commit (`fix(step2): <site> parser on the real page text`).

Expected:
- **Null run:** every detector `det.<site>` is `ok` on both arms, or `UNMEASURED` with the reason in the log. Differing rows and text lines are run-to-run volatility. List them in the ledger as VOLATILE and `VOLATILE_LINES` candidates.
- **Planted run:** at least one detector row or text line differs beyond the null run's set. CreepJS and sannysoft both enumerate navigator features. If none differs, the detector layer cannot see this difference. Record that per site; it does not block the task.

Then run the fork and record its differing rows:

```powershell
& $py measure_step2.py run --only detectors --out D:\camou-win\step2
```

- [ ] **Step 5: Release the lock.**

---

### Task 7: Volatile calibration, the baseline, the docs

**Files:**
- Modify: `scripts/step2_rows.py` (`VOLATILE`, `VOLATILE_LINES`), `scripts/test_step2_rows.py`
- Create: `docs/superpowers/measurements/2026-10-step2-baseline.md`, `docs/superpowers/measurements/step2-154/rows.json`, `docs/superpowers/measurements/step2-154/tables.md`
- Modify: `docs/superpowers/plans/2026-10-02-long-term-roadmap.md` (step 2 status), `README.md` (only if it states what is measured against detectors)

- [ ] **Step 1: Two full null runs**

```powershell
& $py measure_step2.py run --null --out D:\camou-win\step2
& $py measure_step2.py run --null --out D:\camou-win\step2
& $py measure_step2.py compare <null1> <null2>
```

Every `DISAGREE` line is a candidate. Together with the Task 3–6 candidates in the ledger, these are the rows that change between runs of the same binary.

- [ ] **Step 2: Add each to `VOLATILE` with its reason, test first**

For every candidate, add a test that pins it. For example, if `oracle.storage.usage` turned out volatile:

```python
def test_storage_usage_is_volatile():
    assert r.label_rows({"oracle.storage.usage": 1}, {"oracle.storage.usage": 2})[0][3] == "volatile"
```

See each new test fail. Add the entry to `VOLATILE`, with a reason that names what was measured (`"changed between two null runs on 2026-10-xx: 0 vs 4096"`). See the tests pass.

Detector text lines that changed between the null runs go into `VOLATILE_LINES` as anchored regexes, each with a test in the shape of `test_line_diff_is_a_multiset_diff`. Never add a fork-only difference to either list.

Commit:

```bash
git add scripts/step2_rows.py scripts/test_step2_rows.py
git commit -m "feat(step2): volatile rows from two null runs"
```

- [ ] **Step 3: Copy the calibrated tree to the host, then two full fork runs**

```powershell
& $py measure_step2.py run --out D:\camou-win\step2
& $py measure_step2.py run --out D:\camou-win\step2
& $py measure_step2.py compare <run1> <run2>
```

Expected: `0 rows disagree outside VOLATILE`. If rows disagree, decide per row:
- the row also changes between null runs: back to Step 2;
- a fork-only flake: run a third time and record which value repeats;
- otherwise it is a finding, a fork row that is not stable across runs. Record it, and keep it out of `VOLATILE`.

The roadmap's done criterion is met when compare prints 0.

- [ ] **Step 4: Commit the baseline**

Copy `rows.json` and `tables.md` of the second fork run from the host into `docs/superpowers/measurements/step2-154/`, through the WSL `/tmp` path in reverse:

```powershell
Copy-Item <run>\rows.json,<run>\tables.md \\wsl.localhost\Ubuntu-24.04\tmp\
```

Then `scp buildpc:/tmp/rows.json` (and `tables.md`) to the Mac, or use the sshgate MCP to print and Write them. Never copy `raw\`.

Scrub the host's public IP before committing. Detector rows and lines can carry it: Pixelscan and CreepJS show location. Read the IP from the run's `raw\network-control-headless.json` (`ip`, minus any `:port`). Replace every occurrence in both files with `0.0.0.0`. Then `grep -c` the IP in both files and confirm 0.

Write `docs/superpowers/measurements/2026-10-step2-baseline.md` in the style of `2026-10-04-safe-browsing.md`:
- the arms, versions and argv;
- the precondition REDs (Task 3 Step 5);
- the RED table, one row per probe, with the run id and the observed values;
- the volatile list with reasons;
- the compare result;
- every `unexpected` row of the baseline as a finding, with a proposed backlog rank;
- the headed-in-SSH caveat for screen rows;
- whether rule 2's window keys are now measured;
- the linkability list.

Update the roadmap's Step 2:
- a `**Status 2026-10-xx: done.**` paragraph with evidence links;
- re-rank the backlog from the findings, adding new items in their ranked place;
- say what the 156 re-pin must recapture (this baseline, on 156).

```bash
git add docs/superpowers/measurements/2026-10-step2-baseline.md docs/superpowers/measurements/step2-154 docs/superpowers/plans/2026-10-02-long-term-roadmap.md
git commit -m "docs(step2): 154 baseline, RED evidence, findings and backlog re-rank"
```

- [ ] **Step 5: Release the lock**, and run the CI pytest command once more: `python3 -m pytest -q client/python/tests scripts/`.
