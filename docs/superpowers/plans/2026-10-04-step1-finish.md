# Step 1 finish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close roadmap step 1. The work is:
- a named Windows verify set, seen RED against stock Chrome 154 and then GREEN
  against the fork's `chrome.exe` 154;
- the host oracle run on the host;
- the audio service measured, and the GPU-process closure recorded;
- the Windows font rows, plus a client-side fix if the `fonts:alias` finding is
  confirmed.

**Architecture:**
- One environment switch (`CAMOU_SHELL=chrome`) points every `lib_shell`
  default at `chrome`, so the existing verifies run unchanged on Windows.
- A runner (`scripts/windows_verify_set.py`) holds the set: each entry has an
  asserted row count and a RED kind. It runs in `red` mode (stock Chrome as
  `CAMOU_EXE`) and in `green` mode.
- New rows go into one existing script (audio) and one new script (fonts).
- The alias fix lives in each client's env builder. That is the one place
  every launch path goes through.

**Tech Stack:**
- Python 3.10+ (verify scripts, the Python client), Go (the client), Node 24
  (the client), patchright;
- PowerShell 5 on the Windows host, driven over the sshgate MCP: no newlines
  in a command, and commands are approved one by one by the owner.

**Spec:** `docs/superpowers/specs/2026-10-04-step1-finish-design.md`

## Global Constraints

- No Chromium build. Everything runs against `D:\camou-win\chromium\src\out\Release\chrome.exe` 154.0.8037.93.
- Linux CI must not change: with `CAMOU_SHELL` unset, `lib_shell` produces the byte-identical argv that `scripts/test_lib_shell_launch.py` freezes.
- RED before GREEN for every set entry. A GREEN that has no RED is not counted.
- Report counts that were measured. Never edit an expected count to fit a run without a written reason in the commit message.
- The stock control is `C:\Program Files\Google\Chrome\Application\chrome.exe`, which must be 154.0.8037.93 (`upstream.env`'s tag). Google Update on the host is disabled until the 156 re-pin.
- Git author: "Lãng" `<30039912+lang315@users.noreply.github.com>`. Branch `step1/windows-verify-set`, cut from `origin/main`.
- Code comments, commit messages and docs are plain English prose, matching the surrounding files' density.
- On the host: never retry ssh password auth, never write a secret to a file, never touch `D:\camou-win\camoucrome`.

## File map

| File | Change |
|---|---|
| `scripts/lib_shell.py` | `_shell_target()` plus the module-level `SHELL`/`SHELL_FLAGS` rebinding under `CAMOU_SHELL=chrome` |
| `scripts/test_lib_shell_launch.py` | section 6: the switch, with Linux unchanged |
| `scripts/windows_verify_set.py` (new) | the set and its runner |
| `scripts/test_windows_verify_set.py` (new) | the runner's pure functions |
| `.github/workflows/build-verify.yml` | adds `scripts/test_windows_verify_set.py` to the pytest list |
| `scripts/verify_windows_sandbox_env.py` | rows A1 and A2 (audio service); EXPECTED 5 to 7 |
| `scripts/verify_fonts_ii.py` | Windows family names when `os.name == "nt"` |
| `scripts/verify_windows_fonts.py` (new) | F1, F2 (py, go, node) and F4 rows; F3 and F5 notes |
| `settings/launcher.json`, `client/python/camoucrome/launcher.py`, `client/go/camoucrome.go`, `client/node/index.js`, plus each client's tests | Task 6, only if F2 is RED: drop `fonts:alias`/`fonts:aliasLocal` when the claimed OS is the host's |
| `docs/superpowers/measurements/2026-10-04-windows-verify-set.md` (new), the roadmap, `docs/superpowers/specs/repin-runbook.md` | Task 7 |

---

### Task 1: `CAMOU_SHELL=chrome` switch in `lib_shell`

**Files:**
- Modify: `scripts/lib_shell.py` (after `CHROME_FLAGS`, about line 145)
- Test: `scripts/test_lib_shell_launch.py` (new section 6, before the final summary block)

**Interfaces:**
- Produces: `lib_shell._shell_target(environ, shell, chrome) -> (binary, flags)`. The module constants `SHELL` and `SHELL_FLAGS` are rebound from it at import. Later tasks rely on `lib_shell.SHELL == lib_shell.CHROME` being true exactly when the switch is on.

- [ ] **Step 1: Write the failing test.** Insert before the line `print()` that precedes the summary in `scripts/test_lib_shell_launch.py`:

```python
# 6. CAMOU_SHELL=chrome, the Windows switch. A Windows release out dir has no
#    content_shell, and most verifies call session()/launch() without shell=,
#    so the switch moves the DEFAULT binary and flags. Unset, nothing moves:
#    Linux CI keeps content_shell and section 1's frozen argv.
CS, CH = "/o/content_shell", "/o/chrome"
check("no CAMOU_SHELL keeps content_shell and its flags",
      lib_shell._shell_target({}, CS, CH) == (CS, ["--ozone-platform=headless"]),
      f"got {lib_shell._shell_target({}, CS, CH)}")
check("CAMOU_SHELL=chrome makes chrome the default, with logging to stderr",
      lib_shell._shell_target({"CAMOU_SHELL": "chrome"}, CS, CH)
      == (CH, ["--headless", "--no-first-run", "--no-default-browser-check",
               "--enable-logging=stderr"]),
      f"got {lib_shell._shell_target({'CAMOU_SHELL': 'chrome'}, CS, CH)}")
try:
    lib_shell._shell_target({"CAMOU_SHELL": "chrom"}, CS, CH)
    bad = None
except ValueError as e:
    bad = str(e)
check("an unknown CAMOU_SHELL value is refused, not ignored",
      bad is not None and "chrom" in bad, f"got {bad!r}")
```

- [ ] **Step 2: Run it and confirm it fails.**
  - Run: `python3 scripts/test_lib_shell_launch.py`
  - Expected: it exits 1 with `AttributeError: module 'lib_shell' has no attribute '_shell_target'`.

- [ ] **Step 3: Implement.** In `scripts/lib_shell.py`, directly after the `CHROME_FLAGS = [...]` line:

```python
def _shell_target(environ, shell, chrome):
    """(default binary, default flags) for an environment.

    CAMOU_SHELL=chrome is the Windows switch: a release out dir there has no
    content_shell, and most verifies call session()/launch() without shell=, so
    it moves the DEFAULT to chrome with CHROME_FLAGS. --enable-logging=stderr is
    added because chrome, unlike content_shell, keeps LOG(ERROR) off stderr
    without it, and the STDERR_LOG readers assert on the camoucfg: startup
    lines. Unset: content_shell and SHELL_FLAGS, the argv section 1 of
    test_lib_shell_launch.py freezes. Any other value is refused, so a typo
    cannot quietly measure content_shell.
    """
    value = environ.get("CAMOU_SHELL")
    if value is None:
        return shell, SHELL_FLAGS
    if value == "chrome":
        return chrome, CHROME_FLAGS + ["--enable-logging=stderr"]
    raise ValueError(f"CAMOU_SHELL={value!r}: the only value is 'chrome'")


SHELL, SHELL_FLAGS = _shell_target(os.environ, SHELL, CHROME)
```

- [ ] **Step 4: Run it and confirm it passes.**
  - Run: `python3 scripts/test_lib_shell_launch.py`
  - Expected: the last line is `N PASS`, with N three more than before the change, and no FAIL. Also run `CAMOU_SHELL=chrome python3 -c "import sys; sys.path.insert(0,'scripts'); import lib_shell; print(lib_shell.SHELL == lib_shell.CHROME, lib_shell.SHELL_FLAGS[-1])"` and expect `True --enable-logging=stderr`.

- [ ] **Step 5: Commit.**

```bash
git add scripts/lib_shell.py scripts/test_lib_shell_launch.py
git commit -m "feat(lib_shell): CAMOU_SHELL=chrome makes chrome the default binary"
```

---

### Task 2: the set and its runner

**Files:**
- Create: `scripts/windows_verify_set.py`
- Create: `scripts/test_windows_verify_set.py`
- Modify: `.github/workflows/build-verify.yml` (append `scripts/test_windows_verify_set.py` to the existing pytest command's file list, beside `scripts/test_build_lock.py`)

**Interfaces:**
- Consumes: `lib_shell` with Task 1's switch. The runner sets `CAMOU_SHELL=chrome` in each child's environment.
- Produces:
  - `SET`: a list of `Entry(script, rows, red)`, where `rows` is an int or the literal string `"ALL_PASS"`, and `red` is `"stock"` or `"own"`.
  - `count_rows(stdout) -> (passed, failed)`.
  - `judge(mode, entry, returncode, stdout) -> (ok: bool, why: str)`.
  - `stock_version(app_dir) -> str`.
  - `python windows_verify_set.py red|green [--only a,b]`.

- [ ] **Step 1: Write the failing tests** in `scripts/test_windows_verify_set.py`:

```python
"""The runner's pure parts, checkable anywhere. The browser runs happen on the
Windows host; these pin how their output is judged.

Run: python3 -m pytest -q scripts/test_windows_verify_set.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import windows_verify_set as w  # noqa: E402


def test_count_rows_reads_every_row_shape_the_set_prints():
    out = "\n".join([
        "PASS  K1 chunked",            # verify_sp1b / sp4a / generator style
        "FAIL  K2 sandboxed",
        "W1: PASS",                    # verify_windows_sandbox_env style
        "J3: FAIL",                    # verify_metric_jitter style
        "PASS  O1 generated Windows identity: no difference",  # host oracle
        "note: W1: sandboxed + config, main -> 3 (expect 3)",  # not a row
        "      ok   C5 stack timing: +7%",                      # driver detail, not a row
        "2 PASS 1 FAIL",                                        # a summary, not a row
    ])
    assert w.count_rows(out) == (3, 2)


@pytest.mark.parametrize("rc,out,ok", [
    (0, "PASS  a\nPASS  b\n2 PASS 0 FAIL", True),
    (0, "PASS  a\n1 PASS 0 FAIL", False),        # a row dropped out: count is asserted
    (1, "PASS  a\nFAIL  b", False),
    (0, "PASS  a\nFAIL  b", False),              # exit 0 with a FAIL row is not green
])
def test_green_needs_exit_0_and_the_asserted_count(rc, out, ok):
    e = w.Entry("verify_x.py", 2, "stock")
    assert w.judge("green", e, rc, out)[0] is ok


def test_green_all_pass_entry_needs_the_line():
    e = w.Entry("verify_sp6b_driver.py", "ALL_PASS", "stock")
    assert w.judge("green", e, 0, "PASS  py\nALL_PASS")[0] is True
    assert w.judge("green", e, 0, "PASS  py\nFAIL")[0] is False


def test_red_stock_entry_must_fail_and_say_so():
    e = w.Entry("verify_x.py", 2, "stock")
    assert w.judge("red", e, 1, "FAIL  a\nPASS  b")[0] is True
    assert w.judge("red", e, 0, "PASS  a\nPASS  b")[0] is False   # stock passed: measures nothing
    assert w.judge("red", e, 1, "Traceback ...")[0] is False      # a crash is not a RED


def test_red_own_entry_is_skipped_with_its_reason():
    e = w.Entry("verify_x.py", 2, "own")
    ok, why = w.judge("red", e, 0, "")
    assert ok is True and "own" in why


def test_stock_version_is_the_one_version_directory(tmp_path):
    (tmp_path / "154.0.8037.93").mkdir()
    (tmp_path / "SetupMetrics").mkdir()
    assert w.stock_version(tmp_path) == "154.0.8037.93"
    (tmp_path / "155.0.8100.1").mkdir()      # an update half-applied: refuse
    with pytest.raises(SystemExit):
        w.stock_version(tmp_path)


def test_every_entry_names_a_script_that_exists():
    here = os.path.dirname(os.path.abspath(__file__))
    missing = [e.script for e in w.SET if not os.path.exists(os.path.join(here, e.script))]
    assert missing == [] or missing == ["verify_windows_fonts.py"]  # Task 4 adds it
```

- [ ] **Step 2: Run them and confirm they fail.**
  - Run: `python3 -m pytest -q scripts/test_windows_verify_set.py`
  - Expected: a collection error, `ModuleNotFoundError: No module named 'windows_verify_set'`.

- [ ] **Step 3: Implement** `scripts/windows_verify_set.py`:

```python
#!/usr/bin/env python3
"""The named Windows verify set (roadmap step 1) and its runner.

Each entry is a verify script, the row count it must print (or the ALL_PASS line
for the one script whose verdict is a line), and its RED kind:
  stock  run against the host's stock chrome.exe (CAMOU_EXE), which is the same
         version on the same machine and ignores CAMOU_CONFIG, so the script
         must exit non-zero with at least one FAIL row
  own    stock passes these rows too (worker parity, fallback); the script's own
         control rows are its RED, so red mode skips it and says so
red first, then green; a GREEN counts only after its RED was seen.

Run on the Windows host from the tree's scripts directory, with the layout env
the client verifies need (CAMOU_OUT, CAMOU_CLIENT, CAMOU_VENV, the driver and
probe variables, PLAYWRIGHT_NODEJS_PATH):
  python windows_verify_set.py red      # CAMOU_EXE := the stock chrome.exe
  python windows_verify_set.py green
  python windows_verify_set.py green --only verify_sp2b.py,verify_sp4a.py
Each script's output is kept in <tempdir>/windows-verify-set/<mode>/<script>.log.
"""
import collections
import os
import pathlib
import re
import subprocess
import sys
import tempfile

Entry = collections.namedtuple("Entry", "script rows red")

# Row counts: the script's own EXPECTED where it asserts one, otherwise its row
# count read from the source (spec section 2). The driver's verdict is a line.
SET = [
    Entry("verify_windows_sandbox_env.py", 7, "stock"),
    Entry("verify_windows_client.py", 11, "stock"),
    Entry("verify_sp2b.py", 3, "stock"),
    Entry("verify_sp6b_launcher.py", 5, "stock"),
    Entry("verify_sp6b_driver.py", "ALL_PASS", "stock"),
    Entry("verify_crash_dumps.py", 2, "stock"),
    Entry("verify_sp6b_generator.py", 36, "stock"),
    Entry("verify_d_pointer_touch.py", 5, "stock"),
    Entry("verify_sp1b.py", 8, "stock"),
    Entry("verify_sp3b.py", 9, "stock"),
    Entry("verify_sp4a.py", 6, "stock"),
    Entry("verify_metric_jitter.py", 11, "stock"),
    Entry("verify_audio_ii.py", 4, "stock"),
    Entry("verify_ua_halfconfig_reject.py", 6, "stock"),
    Entry("verify_sp5b_domain.py", 4, "stock"),
    Entry("verify_webgl_pairing.py", 9, "stock"),
    Entry("verify_webgl_capability_identity.py", 13, "stock"),
    Entry("verify_navplatform_bucket.py", 7, "stock"),
    Entry("verify_fonts_ii.py", 6, "stock"),
    Entry("verify_windows_fonts.py", 5, "stock"),
    Entry("verify_host_oracle.py", 4, "stock"),
]

ROW = re.compile(r"^(?:(PASS|FAIL)\s+\S|\S+: (PASS|FAIL)\s*$)")
STOCK_APP = r"C:\Program Files\Google\Chrome\Application"


def count_rows(stdout):
    """(PASS rows, FAIL rows). A row is a line that starts with PASS/FAIL and a
    name, or `<id>: PASS|FAIL`. Summaries ("2 PASS 1 FAIL"), notes and the
    driver's indented detail lines are not rows."""
    passed = failed = 0
    for line in stdout.splitlines():
        m = ROW.match(line)
        if m:
            if (m.group(1) or m.group(2)) == "PASS":
                passed += 1
            else:
                failed += 1
    return passed, failed


def judge(mode, entry, returncode, stdout):
    passed, failed = count_rows(stdout)
    if mode == "red":
        if entry.red == "own":
            return True, "own RED: the script's control rows; not run against stock"
        ok = returncode != 0 and failed > 0
        return ok, f"rc={returncode} {passed} PASS {failed} FAIL (want rc!=0 and a FAIL row)"
    if entry.rows == "ALL_PASS":
        ok = returncode == 0 and "ALL_PASS" in stdout.splitlines()
        return ok, f"rc={returncode} ALL_PASS line {'present' if ok else 'missing'}"
    ok = returncode == 0 and failed == 0 and passed == entry.rows
    return ok, f"rc={returncode} {passed} PASS {failed} FAIL (want {entry.rows} PASS)"


def stock_version(app_dir):
    versions = [p.name for p in pathlib.Path(app_dir).iterdir()
                if p.is_dir() and re.fullmatch(r"\d+\.\d+\.\d+\.\d+", p.name)]
    if len(versions) != 1:
        sys.exit(f"stock Chrome under {app_dir} has {versions or 'no'} version directories; want exactly one")
    return versions[0]


def pin_tag(client):
    for line in (pathlib.Path(client) / "upstream.env").read_text().splitlines():
        if line.startswith("CHROMIUM_TAG="):
            return line.split("=", 1)[1].strip().strip('"')
    sys.exit("upstream.env has no CHROMIUM_TAG")


def main(argv):
    if len(argv) < 2 or argv[1] not in ("red", "green"):
        sys.exit(__doc__)
    mode = argv[1]
    only = argv[argv.index("--only") + 1].split(",") if "--only" in argv else None
    here = pathlib.Path(__file__).resolve().parent
    client = os.environ.get("CAMOU_CLIENT", str(here.parent))
    app = os.environ.get("CAMOU_STOCK_APP", STOCK_APP)
    have, want = stock_version(app), pin_tag(client)
    if have != want:
        sys.exit(f"stock Chrome is {have}, the pin is {want}: the control is not the pin's version")
    env = dict(os.environ, CAMOU_SHELL="chrome", CAMOU_STOCK_EXE=os.path.join(app, "chrome.exe"))
    if mode == "red":
        env["CAMOU_EXE"] = os.path.join(app, "chrome.exe")
    logs = pathlib.Path(tempfile.gettempdir()) / "windows-verify-set" / mode
    logs.mkdir(parents=True, exist_ok=True)
    print(f"mode={mode} stock={have} pin={want} exe={env.get('CAMOU_EXE', '(fork via CAMOU_OUT)')}")
    entries = [e for e in SET if only is None or e.script in only]
    good = 0
    for e in entries:
        if mode == "red" and e.red == "own":
            ok, why = judge(mode, e, 0, "")
        else:
            p = subprocess.run([sys.executable, str(here / e.script)], cwd=here, env=env,
                               capture_output=True, text=True, timeout=1800)
            (logs / f"{e.script}.log").write_text(p.stdout + "\n--- stderr ---\n" + p.stderr, encoding="utf-8")
            ok, why = judge(mode, e, p.returncode, p.stdout)
        good += ok
        print(f"{'OK  ' if ok else 'BAD '} {e.script}: {why}", flush=True)
    print(f"{good}/{len(entries)} entries OK ({mode})")
    return 0 if good == len(entries) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: Run the tests and confirm they pass.**
  - Run: `python3 -m pytest -q scripts/test_windows_verify_set.py`
  - Expected: `10 passed`.
  - Then check the tag line format with `grep -n CHROMIUM_TAG upstream.env`. If the variable has a different name, use that name in `pin_tag`. The test must still pass.

- [ ] **Step 5: Add the test to CI.** In `.github/workflows/build-verify.yml`, the pytest command lists `... scripts/test_package.py scripts/test_build_lock.py`; append ` scripts/test_windows_verify_set.py`.

- [ ] **Step 6: Commit.**

```bash
git add scripts/windows_verify_set.py scripts/test_windows_verify_set.py .github/workflows/build-verify.yml
git commit -m "feat(verify): the named Windows verify set and its red/green runner"
```

---

### Task 3: audio-service rows and Windows names for `verify_fonts_ii`

**Files:**
- Modify: `scripts/verify_windows_sandbox_env.py`
- Modify: `scripts/verify_fonts_ii.py:22-24`

**Interfaces:**
- Consumes: `lib_shell.session(config, expressions, shell=, extra_flags=, sandbox=)`, which returns `(values, err)`.
- Produces: the sandbox verify asserts `EXPECTED = 7` (W1–W5, A1, A2); `verify_fonts_ii.py` uses Windows host families when `os.name == "nt"`.

- [ ] **Step 1: Add A1 and A2** to `scripts/verify_windows_sandbox_env.py`. In the module docstring, after the W3 paragraph, add:

```
A1 and A2 are the audio service, the one other process type that reads the
config (media/audio/audio_manager_base.cc, windows-behaviour-ii): on Windows it
runs in a sandboxed utility process, so the same filter could strip
audio:sampleRate there. A1: under {"audio:sampleRate": 22050} a sandboxed
launch's AudioContext reports 22050. A2: with no config it reports anything
else, the device's own rate, so A1 cannot pass on a default.
```

Change `EXPECTED = 5  # W1, W2, W3, W4, W5` to `EXPECTED = 7  # W1-W5, A1, A2`. Before the `for n in notes:` loop, add:

```python
# A1/A2. The audio service. 22050 because no Windows output device reports it,
#     so A2 cannot equal it by accident.
RATE = 22050
AUDIO = "() => { const c = new AudioContext(); const r = c.sampleRate; c.close(); return r; }"
values, err = lib_shell.session(json.dumps({"audio:sampleRate": RATE}), [AUDIO],
                                shell=lib_shell.CHROME, extra_flags=lib_shell.CHROME_FLAGS,
                                sandbox=True)
a1 = None if err else values[0]
results["A1"] = a1 == RATE
notes.append(f"A1: sandboxed + audio:sampleRate, AudioContext.sampleRate -> {a1!r} "
             f"(expect {RATE}){'; ' + type(err).__name__ + ': ' + str(err) if err else ''}")
values, err = lib_shell.session(None, [AUDIO], shell=lib_shell.CHROME,
                                extra_flags=lib_shell.CHROME_FLAGS, sandbox=True)
a2 = None if err else values[0]
results["A2"] = a2 is not None and a2 != RATE
notes.append(f"A2: sandboxed, no config, AudioContext.sampleRate -> {a2!r} "
             f"(expect the device's own rate, not {RATE})")
```

Change the print loop's tuple from `("W1", "W2", "W3", "W4", "W5")` to `("W1", "W2", "W3", "W4", "W5", "A1", "A2")`.

- [ ] **Step 2: Check it locally without a browser.**
  - Run: `python3 -c "import ast,sys; ast.parse(open('scripts/verify_windows_sandbox_env.py').read())"`
  - Expected: no output. The browser run is Task 5, where it must be seen RED (stock: A1 FAIL) before GREEN.

- [ ] **Step 3: Windows names in `verify_fonts_ii.py`.** Replace lines 19–24 (the comment and the three constants) with:

```python
# A font the host actually has (fc-list on the WSL box; the installed set on the
# Windows host), so local() can resolve it and the leak is observable -- the
# cross-method tell is not "structurally blind" when the probe font is
# host-present. HOST_SERIF must not be the host's default sans-serif (F-DIRECT
# confound); on Windows neither Verdana nor Georgia is a generic default
# (Arial, Times New Roman and Consolas are).
if os.name == "nt":
    HOST_FONT, HOST_FONT_PS, HOST_SERIF = "Verdana", "Verdana", "Georgia"
else:
    HOST_FONT = "DejaVu Sans"
    HOST_FONT_PS = "DejaVuSans"      # its PostScript name (resolves too)
    HOST_SERIF = "DejaVu Serif"      # not the box sans-serif default (F-DIRECT confound)
```

  Add `import os` beside the existing imports if it is missing. Then read the rest of `verify_fonts_ii.py`. If any other line hardcodes `DejaVu` (rather than using the three constants), route it through the constants in the same commit.

- [ ] **Step 4: Check that Linux is unchanged.**
  - Run: `python3 -c "import ast; ast.parse(open('scripts/verify_fonts_ii.py').read())"` and `grep -n DejaVu scripts/verify_fonts_ii.py`.
  - Expected: `DejaVu` appears only in the `else:` branch and in comments.

- [ ] **Step 5: Commit.**

```bash
git add scripts/verify_windows_sandbox_env.py scripts/verify_fonts_ii.py
git commit -m "feat(verify): audio-service rows under the sandbox; Windows host fonts for fonts_ii"
```

---

### Task 4: `verify_windows_fonts.py`

**Files:**
- Create: `scripts/verify_windows_fonts.py`

**Interfaces:**
- Consumes:
  - `lib_shell.CHROME` and `lib_shell.layout()`;
  - `camoucrome.gen` (the `python -m camoucrome.gen --os windows --seed N` JSON on stdout has a `config` field) and `camoucrome.launch`;
  - from `scripts/verify_windows_client.py`: `PROBES` (dict `"G"`/`"N"` to argv lists) and `read_probe(cmd, url, config_file) -> (argv, main, worker, err)`. Import them; do not copy them. `read_probe` reads `#o` as JSON with keys `main` and `worker`.
- Produces: rows F1, F2-py, F2-go, F2-node and F4 (`EXPECTED = 5`), and printed notes F3 and F5. The final line is `N PASS M FAIL`. It exits 0 only when all 5 rows pass.

- [ ] **Step 1: Read the two files this builds on.** These are `scripts/verify_windows_client.py` (how `read_probe` and `PROBES` serve a page and read `#o`) and `scripts/verify_host_oracle.py:226-270` (how O3 drives `camoucrome.launch` in a subprocess). Check that `verify_windows_client.py` guards `main()` under `if __name__ == "__main__":` so that importing it runs no browser. If it does not, add the guard in this task's commit.

- [ ] **Step 2: Write the script.**
  - The page writes `#o` with JSON `{main: R, worker: R}`, where `R` maps each probed family to its 100 px `measureText` width of `TEXT`. The window uses a 2D canvas. The worker uses `OffscreenCanvas` and posts back its own `R`.
  - A family's width is measured as `100px "<family>", monospace`. It is also measured against `serif`, and the family counts as resolved when its width differs from the bare fallback's in at least one of the two. This is the same two-fallback rule as `verify_sp4_fonts.py`; read that file for the pattern.
  - `document.fonts.check()` is not used. It returns true for a family no `@font-face` names, so it says nothing about a system font.

```python
#!/usr/bin/env python3
"""Windows: what a page can learn about the host's fonts under a Windows claim.

Spec: docs/superpowers/specs/2026-10-04-step1-finish-design.md section 5. The
host has 118 families; the claimed families.Windows.list (116) is all present,
and the host adds ROG Fonts and AniMe Matrix - MB_EN (ASUS) -- fonts that
identify this machine.

F1     ROG Fonts is invisible to measureText in a window and a worker under a
       generated Windows identity, AND visible to stock (in the same row, so F1
       cannot pass on a font the host lacks)
F2-*   claimed families the host has (Arial, Segoe UI, Times New Roman, Verdana)
       measure exactly as stock, through the Python, Go and Node clients. Read
       from fonts-iii-alias.patch: gen --os windows emits fonts:alias (Arial ->
       Liberation Sans), and GetFontPlatformData returns the alias target's
       lookup with no fallback, so on a Windows host these families would stop
       resolving. These rows measure that.
F4     per-character system fallback (CJK, Thai, emoji in a family nobody has)
       measures as stock: the fallback is the host's real one, which is what a
       Windows host claiming Windows should show. fonts:list does not filter it
       (no patch touches PlatformFallbackFontForCharacter).
F3     note: claimed families stock cannot resolve on this host (a real device
       would have them, so each is a tell)
F5     note: whether two generated identities claim different font lists

RED: windows_verify_set.py red runs this with CAMOU_EXE = the stock chrome.exe;
stock sees ROG Fonts, so F1 fails.
"""
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_shell import CHROME as EXE, layout  # noqa: E402

HOME, PY, NODE, CLIENT, FONTS_DIR = layout()
import verify_windows_client as vwc  # noqa: E402  (PROBES, read_probe)

STOCK = os.environ.get("CAMOU_STOCK_EXE", r"C:\Program Files\Google\Chrome\Application\chrome.exe")
HOST_ONLY = "ROG Fonts"
REAL = ["Arial", "Segoe UI", "Times New Roman", "Verdana"]
TEXT = "mmmmmmmmmmlli WWW 0123456789"
FALLBACK_TEXT = "\u6f22\u5b57\u304b\u306a \u0e44\u0e17\u0e22 \U0001F600"
EXPECTED = 5

PAGE = """<!doctype html><title>fonts</title><script>
const FAMS = %s, TEXT = %s, FB = %s;
function measure(ctx) {
  const w = (font, t) => { ctx.font = font; return ctx.measureText(t).width; };
  const out = {};
  for (const f of FAMS) out[f] = [w('100px "' + f + '", monospace', TEXT), w('100px "' + f + '", serif', TEXT)];
  out.__mono = w('100px monospace', TEXT); out.__serif = w('100px serif', TEXT);
  out.__fallback = w('100px "Camoucrome No Such Family"', FB);
  return out;
}
const SRC = 'const FAMS=' + JSON.stringify(FAMS) + ',TEXT=' + JSON.stringify(TEXT) + ',FB=' + JSON.stringify(FB) + ';' +
  measure.toString() + 'self.postMessage(measure(new OffscreenCanvas(10,10).getContext("2d")));';
const wk = new Worker(URL.createObjectURL(new Blob([SRC], {type: 'text/javascript'})));
wk.onmessage = e => { const o = document.createElement('pre'); o.id = 'o';
  o.textContent = JSON.stringify({main: measure(document.createElement('canvas').getContext('2d')), worker: e.data});
  document.body.appendChild(o); };
</script>""" % (json.dumps([HOST_ONLY] + REAL), json.dumps(TEXT), json.dumps(FALLBACK_TEXT))


def resolved(r, fam):
    mono, serif = r[fam]
    return mono != r["__mono"] or serif != r["__serif"]


def identity(seed):
    g = subprocess.run([PY, "-m", "camoucrome.gen", "--os", "windows", "--seed", str(seed)],
                       capture_output=True, text=True, timeout=120)
    if g.returncode != 0:
        sys.exit(g.stderr[-500:])
    return json.loads(g.stdout)["config"]


def python_read(url, exe, config):
    """{main, worker} through camoucrome.launch() in a subprocess, sandboxed."""
    script = f"""
import json, sys
sys.path.insert(0, {json.dumps(str(CLIENT / "client" / "python"))})
from camoucrome import launch
from patchright.sync_api import sync_playwright
with sync_playwright() as pw:
    ctx = launch(pw, {json.dumps(exe)}, config={json.dumps(config)!s}, headless=True)
    page = ctx.new_page(); page.goto({json.dumps(url)})
    page.wait_for_selector("#o", state="attached", timeout=30000)
    print(page.locator("#o").text_content())
    ctx.close()
"""
    p = subprocess.run([PY, "-c", script], capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        return None, p.stderr[-600:]
    return json.loads(p.stdout.strip().splitlines()[-1]), None


def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), type("H", (http.server.BaseHTTPRequestHandler,), {
        "do_GET": lambda s: (s.send_response(200), s.send_header("Content-Type", "text/html; charset=utf-8"),
                             s.end_headers(), s.wfile.write(PAGE.encode())),
        "log_message": lambda *a: None}))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/"
    cfg = identity(1)
    results, notes = {}, []
    fork, err = python_read(url, EXE, cfg)
    stock, serr = python_read(url, STOCK, None)
    if fork is None or stock is None:
        print("note: launch failed:", (err or serr or "").replace("\n", " | "))
        fork, stock = fork or {"main": None, "worker": None}, stock or {"main": None, "worker": None}
    fm, fw, sm = fork["main"], fork["worker"], stock["main"]
    results["F1 ROG Fonts hidden in window and worker under the identity, visible to stock"] = (
        fm is not None and fw is not None and sm is not None
        and not resolved(fm, HOST_ONLY) and not resolved(fw, HOST_ONLY) and resolved(sm, HOST_ONLY))
    real_equal = lambda r: r is not None and sm is not None and all(r[f] == sm[f] for f in REAL)
    results["F2-py claimed host families measure as stock (Python client)"] = real_equal(fm)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(cfg, f)
        cfg_file = f.name
    try:
        for k, label in (("G", "go"), ("N", "node")):
            _argv, main_r, _worker_r, perr = vwc.read_probe(vwc.PROBES[k], url, cfg_file)
            if perr:
                notes.append(f"F2-{label}: {str(perr)[:300]}")
            results[f"F2-{label} claimed host families measure as stock ({label} client)"] = real_equal(main_r)
    finally:
        os.unlink(cfg_file)
    results["F4 per-character system fallback measures as stock"] = (
        fm is not None and sm is not None and fm["__fallback"] == sm["__fallback"])
    srv.shutdown()
    if fm is not None and sm is not None:
        notes.append("F2 widths fork/stock: " + "; ".join(f"{x}={fm[x][0]:.2f}/{sm[x][0]:.2f}" for x in REAL))
    claimed = cfg.get("fonts:list") or []
    notes.append(f"F3: the identity claims {len(claimed)} families; measuring which stock lacks is "
                 f"settings/fonts.json vs the host's installed list, read 2026-10-04: 0 missing")
    other = identity(2).get("fonts:list") or []
    notes.append(f"F5: seeds 1 and 2 claim {'the SAME' if sorted(other) == sorted(claimed) else 'different'} "
                 f"font lists ({len(claimed)} vs {len(other)}) -- the SAME list on every profile is a "
                 f"cross-profile finding for backlog item 2, not a failure here")
    for k, v in results.items():
        print(("PASS " if v else "FAIL ") + " " + k)
    for n in notes:
        print("note:", n[:900])
    if len(results) != EXPECTED:
        sys.exit(f"expected {EXPECTED} rows, built {len(results)}")
    n = sum(results.values())
    print(f"{n} PASS {len(results) - n} FAIL")
    sys.exit(0 if n == len(results) else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Fit it to the real interfaces.** Read `verify_windows_client.py`'s `read_probe` and `PROBES` and check the call above against them: its exact return tuple, and whether the probes need `--sandbox --strict` or an extra flag. Adjust the call to match without changing what the rows assert. If `read_probe` returns the parsed `#o` under different names, unpack accordingly. Run `python3 -c "import ast; ast.parse(open('scripts/verify_windows_fonts.py').read())"` and expect no output.

- [ ] **Step 4: Commit.**

```bash
git add scripts/verify_windows_fonts.py scripts/verify_windows_client.py
git commit -m "feat(verify): Windows font rows -- host-only font hidden, claimed fonts real, fallback real"
```

---

### Task 5: the first host run, RED then GREEN (controller, inline, over sshgate)

Not a subagent task: every command needs the owner's approval in sshgate. Commands are PowerShell, one line each.

- [ ] **Step 1: Ship the branch's scripts to the host's tree.**
  - Use the 2026-10-04 method: in WSL, `git -C $R fetch -q origin step1/windows-verify-set` and `git -C $R archive FETCH_HEAD -o /home/lang/tree-set.tar`.
  - Copy the tar over `\\wsl.localhost\Ubuntu-24.04\home\lang\` and untar it in place into `D:\camou-win\tree`.
  - Compare the sha256 on both sides, and write the branch head into `D:\camou-win\tree.commit`.
  - Run `git diff --diff-filter=DR babbd2f FETCH_HEAD` first; it must be empty.

- [ ] **Step 2: Write `D:\camou-win\set-env.ps1`** (box only, not in the repo). It holds the environment from memory `windows-native-build`:
  - `CAMOU_OUT=D:\camou-win\chromium\src\out\Release`;
  - `CAMOU_CLIENT=D:\camou-win\tree`;
  - `CAMOU_VENV`, `CAMOU_VENV_STOCK=D:\camou-win\client-venv`;
  - `CAMOU_DRIVER`, `CAMOU_DRIVER_STOCK`;
  - `CAMOU_GO_PROBE=D:\camou-win\probes\green\camoucrome-probe.exe`;
  - `PLAYWRIGHT_NODEJS_PATH=D:\camou-win\driver-patchright\node.exe`;
  - PATH += `C:\Program Files\Git\usr\bin`.

  Rebuild the Go probe from the tree's `client/go` first (`go build -o D:\camou-win\probes\green\camoucrome-probe.exe ./cmd/camoucrome-probe`), because #17 changed `client/go` after the probe was built.

- [ ] **Step 3: RED.**
  - Start it detached through `Win32_Process Create`, so a long run survives the ssh call: `D:\camou-win\client-venv\Scripts\python.exe D:\camou-win\tree\scripts\windows_verify_set.py red`, with output to `D:\camou-win\set-red.log`.
  - Poll the log. Expected: `N/N entries OK (red)`.
  - Handle any `BAD` entry by its cause, never by editing a count:
    - The script passed under stock: read its rows. If they are parity or fallback rows that stock legitimately passes, reclassify it as `own` in `SET`, naming its control rows in the commit message. If it measures nothing the fork does, remove it from the set with the reason.
    - The script errored instead of failing (a crash or a missing dependency): fix the harness cause and re-run the RED.

- [ ] **Step 4: GREEN.**
  - Run `windows_verify_set.py green` the same way, with output to `D:\camou-win\set-green1.log`.
  - Expected: `N/N entries OK (green)`, except the F2 rows of `verify_windows_fonts.py` if the alias finding holds. Those prove the finding and are handled by Task 6.
  - Any other `BAD`: read its log in `%TEMP%\windows-verify-set\green\` and fix the cause. If it is a real fork defect that needs C++, record it with its output as a finding and take the entry out of the set for this step, with the reason. If a script's row count differs from `SET` and the script asserts no count, read its source, set the measured count, and write why in the commit message.

- [ ] **Step 5: Run `verify_sp6b_driver.py` alone when the host is idle** if it went BAD on C5 timing (it is load-sensitive). Record the idle result beside the loaded one.

- [ ] **Step 6: Commit** any `SET` or script corrections with the measured reason, and keep both logs (copy them back to the scratchpad) for Task 7.

---

### Task 6: drop `fonts:alias` when the claimed OS is the host's (only if F2 was RED in Task 5)

**Files:**
- Modify: `settings/launcher.json` (the `launch` object: new key `native_fonts`)
- Modify: `client/python/camoucrome/launcher.py` (`build_env`)
- Modify: `client/go/camoucrome.go` (`BuildEnv`)
- Modify: `client/node/index.js` (`buildEnv`)
- Test: `client/python/tests/test_launcher.py`, `client/go/camoucrome_test.go`, `client/node/test/launcher.test.js`

**Interfaces:**
- Consumes: each client's existing `claimed_os` / `claimedOS` / `claimedOs`.
- Produces: one rule, with the contract in `settings/launcher.json`:
  - The rule: when the claimed OS equals the host OS, the config that reaches `CAMOU_CONFIG` carries no `fonts:alias` and no `fonts:aliasLocal`.
  - The host OS is Python `sys.platform` mapped `win32` → `Windows`, `darwin` → `macOS`, `linux` → `Linux`. Go maps `runtime.GOOS` (`windows`, `darwin`, `linux`) to the same names. Node maps `process.platform` (`win32`, `darwin`, `linux`) to the same names.
  - Each builder takes an optional host-OS override so tests can pin it: Python `build_env(..., host_os=None)`, Go `buildEnvFor(o, base, hostOS string)` called by `BuildEnv`, Node `buildEnv({..., hostOs})`.

- [ ] **Step 1: Contract.** In `settings/launcher.json` under `launch`, beside `fontconfig`, add:

```json
"native_fonts": {
 "drop": ["fonts:alias", "fonts:aliasLocal"],
 "why": "On a host whose OS is the claimed OS, the claimed families are the host's real ones. fonts:alias redirects them to the OFL bundle (Arial -> Liberation Sans), and FontCache::GetFontPlatformData returns the alias target's lookup with no fallback, so on Windows -- where the bundle is not installed -- a generated Windows identity lost its real Arial (measured 2026-10-04, verify_windows_fonts.py F2 RED). The launcher drops both keys from the config before it is encoded when the claimed OS (derive.cc ClaimedOs over the effective keys) equals the host OS. A claimed family the host lacks then shows as missing, which F3 counts."
}
```

- [ ] **Step 2: Failing tests, one per client.**
  - Python: `test_native_host_drops_font_aliases` builds `build_env(config={"ua:platform": "Windows", "fonts:alias": {"Arial": "Liberation Sans"}, "fonts:aliasLocal": {"ArialMT": "Liberation Sans"}, "fonts:list": ["Arial"]}, host_os="Windows", base={})`. It decodes the `CAMOU_CONFIG*` value the way the existing tests in `test_launcher.py` do, and asserts that `fonts:list` is kept while neither alias key is present. The same call with `host_os="Linux"` keeps both alias keys. A third assert compares the contract's `drop` list to `launcher.NATIVE_FONTS_DROP`.
  - Go and Node: the same three asserts, in each file's existing style (the Go contract test `TestFontconfigFollowsTheClaimedOS` and the Node launcher tests show how each reads `settings/launcher.json`).
  - Run each and confirm it fails: `python -m pytest -q client/python/tests/test_launcher.py -k native`, `go test ./... -run Native` in `client/go`, and `node --test client/node/test/` with the new test named.

- [ ] **Step 3: Implement.** In Python, in `launcher.py` beside `FONTCONFIG_FILES`:

```python
NATIVE_FONTS_DROP = ("fonts:alias", "fonts:aliasLocal")
HOST_OS = {"win32": "Windows", "darwin": "macOS", "linux": "Linux"}.get(sys.platform)


def native_config(config, preset=None, host_os=None):
    """config without fonts:alias / fonts:aliasLocal when the claimed OS is the
    host's (contract launch.native_fonts): those families are real there, and
    an alias to the uninstalled bundle would hide them."""
    host_os = HOST_OS if host_os is None else host_os
    if config is None or claimed_os(config, preset) != host_os:
        return config
    c = json.loads(config) if isinstance(config, str) else dict(config)
    return {k: v for k, v in c.items() if k not in NATIVE_FONTS_DROP}
```

  In `build_env`:
  - add the parameter `host_os=None`;
  - after `effective_keys(config, preset)`, add `config = native_config(config, preset, host_os)`;
  - import `sys` and `json` if they are missing.

  Go and Node get the same rule in their builders, written in each file's idiom:
  - **Go:** `buildEnvFor` filters a `map[string]any` copy, or a JSON string after unmarshalling it.
  - **Node:** `buildEnv` takes `hostOs` in its options object, defaulting from `process.platform`.

- [ ] **Step 4: Run all three suites and confirm they pass.**
  - Python: `python -m pytest -q client/python/tests`.
  - Go: `cd client/go && go test ./...`.
  - Node: `node --test client/node/test/`.

  Each passes, with the new tests included. Restore `client/python/camoucrome.egg-info/PKG-INFO` with `git checkout --` if pip touched it.

- [ ] **Step 5: Commit.**

```bash
git add settings/launcher.json client/
git commit -m "fix(client): drop font aliases when the claimed OS is the host's"
```

- [ ] **Step 6: Back on the host** (controller, inline):
  - ship the tree again (Task 5 Step 1) and rebuild the Go probe;
  - run `windows_verify_set.py green --only verify_windows_fonts.py`; the F2-py, F2-go and F2-node rows must be GREEN now;
  - then run the whole set in green twice more (`set-green2.log`, `set-green3.log`). Each must read `N/N entries OK (green)`.

---

### Task 7: documentation (controller, inline)

**Files:**
- Create: `docs/superpowers/measurements/2026-10-04-windows-verify-set.md`
- Modify: `docs/superpowers/plans/2026-10-02-long-term-roadmap.md` (step 1 status; backlog items 2 and 6 if the oracle or the fonts added evidence; step 0 status line "done except CI" is now done, because `build-verify` was green on main at `571ee2a`)
- Modify: `docs/superpowers/specs/repin-runbook.md` §7 (re-enable Google Update at the 156 re-pin: `Enable-ScheduledTask` for the `GoogleUpdaterTaskSystem*` task and `Set-Service -StartupType Automatic` for the two `GoogleUpdater*` services)

- [ ] **Step 1: Write the measurement doc.** It records:
  - the preconditions: the host version, the updater state and the tree stamp;
  - the set table, with entry, criterion, RED result, GREEN results ×3 and count;
  - every reclassification or removal and its reason;
  - the host oracle's O1–O4 and its DIFF lines verbatim;
  - A1 and A2;
  - the GPU-process closure with its path list (spec section 4);
  - F1–F5 with the widths, and the alias finding and its fix;
  - the change-loop criterion (spec section 6);
  - what this does not establish.

  Each number is quoted from the logs, never retyped from memory.

- [ ] **Step 2: Update the roadmap.**
  - Step 1 is marked done, or the exact residue is named.
  - Step 0's status line is updated.
  - New evidence goes under backlog item 2 (WebGPU/GPU DIFFs, the same font list on every profile) and item 6.

- [ ] **Step 3: Add the runbook's §7 re-enable step.**

- [ ] **Step 4: Commit.**
  - Push the branch.
  - Open a PR whose body carries the RED and GREEN summaries (the `N/N entries OK` lines and the per-entry `OK`/`BAD` lines) and the unit test output.
  - Merge only when the owner asks.
