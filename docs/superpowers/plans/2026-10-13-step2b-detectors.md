# Step 2b Implementation Plan: more detectors, the session-0 fix, and the Windows fork at main

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure the Windows fork at main against stock Chrome on 20 public detector pages, plus step 2's five probes, in the owner's interactive session. Every host harness gets a GPU-crash gate, so a session-0 artefact can no longer pass as a finding.

**Architecture:**
- **Gate module.** `scripts/gpu_gate.py` holds a pure parser for `chrome://gpu`'s crash count, readers for a Playwright context or a DevTools port, and a session-id precondition.
- **Gate wiring.** Every host launch path calls it: `lib_shell`, `measure_step2.opened()`, `verify_s3_host`, `verify_host_oracle` and `winhost`.
- **Interactive launch.** `scripts/windows/run-interactive.ps1` starts a host-native runner in session 1. `winhost.py` wraps each of its own launches in a temporary task.
- **Detectors.** `measure_step2.DETECTORS` grows to 20 sites. `step2_rows` gains verdict parsers, a verdict table and `scrub()`.

**Tech Stack:** Python 3.12 (host client venv: patchright 1.62.3, playwright 1.55.0), Python 3 on the Mac (pytest only), PowerShell 5.1 on the host, Git Bash for `apply.sh`, siso/autoninja for the native build.

**Spec:** `docs/superpowers/specs/2026-10-13-step2b-detectors-design.md` (approved 2026-10-13).

## Global Constraints

- Pin: `154.0.8037.93`. Control: `C:\Program Files\Google\Chrome\Application\chrome.exe`, held at the pin. Fork: `D:\camou-win\chromium\src\out\Release\chrome.exe`.
- **Commit hygiene.**
  - Commit only scrubbed rows and tables, counts, API names, hosts and cookie names.
  - Never commit raw detector text, screenshots, IP addresses, city, region, coordinates, ISP, ASN, visitor or event ids, device labels or account ids.
  - Raw captures stay on the host under `D:\camou-win\cn\step2b`.
- **Lock and canvas.**
  - Every Chromium build and every host Chrome run holds `scripts/build_lock.sh`.
  - The call from the host is `wsl -d Ubuntu-24.04 -u lang -- bash /home/lang/actions-runner/_work/camoucrome/camoucrome/scripts/build_lock.sh acquire|release|status <owner>`.
  - Message canvas (`chrome-build-observe-recon`) before acquiring and after releasing.
  - Never break another holder's lock. Builds run one at a time.
- **Off limits:** `D:\camou-win\camoucrome`, `observe-backup`, `~/chromium-s2c`, `~/s2c-*`, `/tmp/s2c-*`. No `git gc` or prune. No `wsl --shutdown`. Keep `CamouWslKeepAlive`.
- **Host transport.** Send files with sshgate as base64 through `[IO.File]::WriteAllBytes(path, [Convert]::FromBase64String('...'))`. sshgate `stdin` hung twice on 2026-10-13. Read UTF-8 files with `Get-Content -Encoding UTF8`.
- **Long host runs** go detached through `scripts/windows/run-interactive.ps1` (Task 3), then are polled. One sshgate call is capped at 600 s.
- **Gates are no-ops off Windows.** Every gate checks `os.name == "nt"` before doing anything. CI's `out/Default` (Linux, content_shell has no `chrome://gpu`) must behave byte-identically. `scripts/test_lib_shell_launch.py`'s frozen argv must not change.
- **Load rate.** One load per detector page per cell. No retry loops. A re-run is a manual decision recorded in the doc.
- **No product code changes.** Nothing in `client/` changes.
- **Mac git and commits.** Plain git commands only: no `cd X && git`, no heredocs, no `$(...)` in Bash. Commit messages go through `git commit -F <file>` and end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **PR.** The PR body carries evidence and ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. No session URLs anywhere. Not merged without the owner's approval.
- Times to the owner are in ICT (UTC+7).

## Rulings made at planning time (from the 2026-10-13 stock capture)

On 2026-10-13, one headless stock load per page ran in session 1 through a temporary interactive task. All 24 launches read `GPU process crash count :0`. One session-0 launch read `:1`. The rulings below follow from that capture.

1. **Four spec pages are dropped. 20 remain.**
   - `brotector` and `botd`: the title was `Site not found · GitHub Pages`.
   - `areyouheadless`: `502 Bad Gateway`. Task 10 rechecks it once. If it is still not 200 with content, it stays dropped.
   - `turnstile` (`https://demo.turnstile.workers.dev/`): the `cf-turnstile-response` token was 21 characters from 3 s to 30 s, and the challenge frame's text was empty. A length of 21 is consistent with Cloudflare's documented dummy token for test sitekeys. Task 10 reads the value once to confirm. Either way it measures nothing.
   - The measurement doc lists all four with this evidence.
2. **browserleaks rows use `_`, not `.`** (`browserleaks_webgl`). `step2_rows.label_rows` finds a row's site with `".".join(name.split(".")[:2])`, so a dotted site name would hide its UNMEASURED state.
3. **No `action` field.** No surviving page needs a click or a wait condition. `DETECTORS` stays a `{name: url}` dict.
4. **Session check where there is no context or port.**
   - `verify_host_oracle`'s `camoucrome.probe` subprocess launches (O1/O2) and `winhost.dump_dom` give the harness no browser context or DevTools port to read `chrome://gpu` from.
   - A session-id precondition stands in for the per-launch crash count there: session 0 means `UNMEASURED session=0`.
   - Grounds (S4): crash count 1 in every one of about 465 session-0 launches, and 0 in 40 of 40 session-1 launches. Changing `client/` to expose a port is out of scope.
   - This deviates from the spec's "readers, one per launch path" text, and the PR says so.
5. **A generic `blocked` row for every site.** `whoer.net` served Cloudflare's "Performing security verification" interstitial to headless stock, and that is a verdict.
6. **Per-load ids are volatile, not scrubbed.** Fingerprint Pro's visitor id and event ids go into `VOLATILE_LINES` during null-run calibration. `scrub()` handles only addresses, coordinates and the host's geo strings.
7. **Run time.** About 15–24 s per page, so 20 sites × 4 cells ≈ 30 min, plus about 20 min for the other probes. One full run ≈ 50 min. The spec's 2–3 h estimate was for 24 sites with no data.
8. **CI copy line.** `build-verify.yml` copies named scripts into `$VERIFY`. `gpu_gate.py` is added to that `cp` line, and every import of it in a copied script is lazy, inside an `os.name == "nt"` branch.

## Review Focus

1. **A version or clock string mistaken for an IP.** `scrub()` must leave `HeadlessChrome/154.0.8037.93`, `10:00:00` and `2026-10-13T17:15:42` untouched, and still mask `1.2.3.4:443` and `[2001:db8::1]`. Tested in Task 6.
2. **A rejected launch's raw text reaching the tables.** When the gate rejects a detector launch, its `.txt`/`.png` must be removed. Otherwise `write_tables` diffs a crashed launch's text. Tested in Task 7.
3. **A `chrome://gpu` page without the count line.** The reader returns `None`, and `None` must be UNMEASURED, never read as 0. Tested in Task 3.
4. **The set judging an UNMEASURED entry.** An entry whose stdout has an `UNMEASURED` line is neither OK nor BAD-as-FAIL, in both `red` and `green` modes, and the set's rc is non-zero. Tested in Task 4.
5. **A parser matching prose.** dbi_bot's explanation section repeats every key with a colon (`hasWebdriverTrue: True if …`). Only the quoted-JSON lines may count, and the first occurrence wins in incolumitas. Tested in Task 6.

---

## Order

- Task 1 and Task 2 are builds that hold the lock for hours. Start them first.
- Tasks 3–8 are Mac-side code with offline tests. They proceed while the builds run.
- Task 9 (host REDs and GREENs) needs the builds done and the lock free.
- **After Task 9 the session-0 fix is complete and shippable on its own** (gates plus set GREEN). Tasks 10–11 are the measurement and the docs.

---

### Task 1: Re-point the Windows tree to main and rebuild `out\Release`

**Files:** none in the repo. Host: `D:\camou-win\tree`, `D:\camou-win\tree.commit`, `D:\camou-win\chromium\src`, `D:\camou-win\cn\step2b\build-release.ps1`, `D:\camou-win\cn\step2b\build-release.log`.

**Interfaces:**
- Produces: `D:\camou-win\chromium\src\out\Release\chrome.exe` built from main's change set. `D:\camou-win\tree` holds main's files. `tree.commit` names main's SHA.

- [ ] **Step 1: Message canvas, then take the lock.**

SendMessage to `chrome-build-observe-recon`: "Taking build_lock `step2b-release`: tree reset to main + out\Release build (then out\Observe). Leaving D:\camou-win\camoucrome and observe-backup untouched."

Run (sshgate, `buildpc`):
```
wsl -d Ubuntu-24.04 -u lang -- bash /home/lang/actions-runner/_work/camoucrome/camoucrome/scripts/build_lock.sh acquire step2b-release
```
Expected: `acquired by step2b-release`. Anything else: stop, do not break the lock.

- [ ] **Step 2: Archive main in the runner clone. Fetch only; never check out there.**

Run:
```
wsl -d Ubuntu-24.04 -u lang -- bash -c "cd /home/lang/actions-runner/_work/camoucrome/camoucrome && git fetch -q origin main && git rev-parse FETCH_HEAD && git archive --format=tar -o /tmp/step2b-tree.tar FETCH_HEAD && ls -l /tmp/step2b-tree.tar"
```
Expected: one 40-hex SHA (call it `MAIN`), and a tar of a few MB.

- [ ] **Step 3: Refresh `D:\camou-win\tree` and stamp it.**

Run:
```
Copy-Item \\wsl.localhost\Ubuntu-24.04\tmp\step2b-tree.tar D:\camou-win\step2b-tree.tar; tar -xf D:\camou-win\step2b-tree.tar -C D:\camou-win\tree; Set-Content -NoNewline D:\camou-win\tree.commit '<MAIN>'; Get-Content D:\camou-win\tree.commit; Test-Path D:\camou-win\tree\patches\observe.patch
```
Expected: `<MAIN>`, `True`.

- [ ] **Step 4: Record the source tree's state and check that every dirty path is in main's change set.**

Write `D:\camou-win\cn\step2b\dirty-check.sh` (base64 transfer):
```bash
#!/bin/bash
# Every path the bare working tree changes must come from main's change set, or the reset loses it.
cd /d/camou-win/chromium/src || exit 2
[ "$(git rev-parse --show-toplevel)" = "D:/camou-win/chromium/src" ] || { echo "WRONG TREE"; exit 2; }
echo "dirty=$(git status --porcelain -uall | wc -l) head=$(git rev-parse --short=10 HEAD)"
miss=0
for f in $( (git diff --cached --name-only; git diff --name-only) | sort -u); do
  grep -qF "+++ b/$f" /d/camou-win/tree/patches/*.patch || { echo "NOT IN MAIN: $f"; miss=1; }
done
for f in $(git ls-files --others --exclude-standard); do
  case "$f" in
    components/camoucfg/*) [ -e "/d/camou-win/tree/additions/camoucfg/${f#components/camoucfg/}" ] || [ "$f" = components/camoucfg/invariants.json ] || { echo "UNTRACKED NOT IN MAIN: $f"; miss=1; } ;;
    *) echo "UNTRACKED OUTSIDE camoucfg: $f"; miss=1 ;;
  esac
done
echo "miss=$miss"
```
Run: `& 'C:\Program Files\Git\bin\bash.exe' /d/camou-win/cn/step2b/dirty-check.sh`

Expected: `head=f89f3a4363` and `miss=0`.
- `miss=1` means some path would be lost. Stop and report the listed paths to the owner.
- The `dirty=` count goes in the doc.

- [ ] **Step 5: Write the build script and start it detached.**

Write `D:\camou-win\cn\step2b\build-release.ps1`:
```powershell
$ErrorActionPreference = 'Continue'
$env:DEPOT_TOOLS_WIN_TOOLCHAIN = '0'
$env:DEPOT_TOOLS_UPDATE = '0'
$env:vs2022_install = 'C:\Program Files\Microsoft Visual Studio\2022\Community'
$env:PATH = 'D:\camou-win\depot_tools;' + $env:PATH
Set-Location D:\camou-win\chromium\src
if ((git rev-parse --show-toplevel) -ne 'D:/camou-win/chromium/src') { 'WRONG TREE'; exit 2 }
"reset $(Get-Date -Format o)"
git reset --hard -q
git clean -fdq components/camoucfg
"apply $(Get-Date -Format o)"
& 'C:\Program Files\Git\bin\bash.exe' /d/camou-win/tree/scripts/apply.sh D:/camou-win/chromium/src
"apply rc=$LASTEXITCODE"
"dirty after apply=$((git status --porcelain -uall | Measure-Object).Count)"
gn gen out\Release
"gn rc=$LASTEXITCODE"
$t0 = Get-Date
cmd /c "autoninja -C out\Release chrome 2>&1"
"build rc=$LASTEXITCODE wall=$([int]((Get-Date) - $t0).TotalSeconds)s"
"DONE $(Get-Date -Format o)"
```
Start it:
```
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = 'powershell -NoProfile -ExecutionPolicy Bypass -Command "& D:\camou-win\cn\step2b\build-release.ps1 *> D:\camou-win\cn\step2b\build-release.log"' } | Select-Object ProcessId,ReturnValue
```
Expected: `ReturnValue 0`.

- [ ] **Step 6: Poll until `DONE`.** Every 10 min, run:
```
Get-Content D:\camou-win\cn\step2b\build-release.log -Tail 5; (Get-ChildItem D:\camou-win\chromium\src\out\Release\obj -Recurse -Filter *.obj | Measure-Object).Count
```
siso writes its log only at the end, so the `.obj` count is the progress signal.

Expected at the end:
- `apply rc=0`;
- `dirty after apply=` close to step 4's count (record both);
- `gn rc=0`;
- a `Build Succeeded: <N> steps` line with N > 0;
- `build rc=0`.

N = 0 means a stale no-op: stop and investigate.

- [ ] **Step 7: Check the binary.**

Run: `(Get-Item D:\camou-win\chromium\src\out\Release\chrome.exe).VersionInfo.ProductVersion; (Get-Item D:\camou-win\chromium\src\out\Release\chrome.exe).LastWriteTime`

Expected: `154.0.8037.93`, with a timestamp from this build.

- [ ] **Step 8: Release the lock.**

Run: `wsl -d Ubuntu-24.04 -u lang -- bash /home/lang/actions-runner/_work/camoucrome/camoucrome/scripts/build_lock.sh release step2b-release`

Expected: `released by step2b-release`. Record steps, wall time, `MAIN` and the dirty counts for Task 10.

### Task 2: Rebuild `out\Observe` with runtime call stats

**Files:** none in the repo. Host: `D:\camou-win\chromium\src\out\Observe\args.gn`, `D:\camou-win\cn\step2b\build-observe.ps1`, `.log`.

**Interfaces:**
- Consumes: Task 1's tree at main.
- Produces: `out\Observe\chrome.exe` at main with `camou_observe = true` and `v8_enable_runtime_call_stats = true`. E's arm 1 re-runs on it later; that run belongs to E, not to this plan.

- [ ] **Step 1: Take the lock** as `step2b-observe` (same command as Task 1 step 1). Expected: `acquired by step2b-observe`.

- [ ] **Step 2: Diff the args before the edit.**

Run:
```
Copy-Item D:\camou-win\chromium\src\out\Observe\args.gn D:\camou-win\cn\step2b\observe-args.before; Get-Content D:\camou-win\chromium\src\out\Observe\args.gn
```
Expected: the file contains `camou_observe = true` and does not contain `v8_enable_runtime_call_stats`. If it already does, skip step 3 and record that.

- [ ] **Step 3: Append the arg and diff.**

Run:
```
Add-Content D:\camou-win\chromium\src\out\Observe\args.gn 'v8_enable_runtime_call_stats = true'; Compare-Object (Get-Content D:\camou-win\cn\step2b\observe-args.before) (Get-Content D:\camou-win\chromium\src\out\Observe\args.gn)
```
Expected: exactly one `=>` line, `v8_enable_runtime_call_stats = true`.

- [ ] **Step 4: Build detached.** Write `D:\camou-win\cn\step2b\build-observe.ps1`. It is the same as Task 1's script without the reset and apply lines:
```powershell
$ErrorActionPreference = 'Continue'
$env:DEPOT_TOOLS_WIN_TOOLCHAIN = '0'
$env:DEPOT_TOOLS_UPDATE = '0'
$env:vs2022_install = 'C:\Program Files\Microsoft Visual Studio\2022\Community'
$env:PATH = 'D:\camou-win\depot_tools;' + $env:PATH
Set-Location D:\camou-win\chromium\src
gn gen out\Observe
"gn rc=$LASTEXITCODE"
$t0 = Get-Date
cmd /c "autoninja -C out\Observe chrome 2>&1"
"build rc=$LASTEXITCODE wall=$([int]((Get-Date) - $t0).TotalSeconds)s"
"DONE $(Get-Date -Format o)"
```
Start it with `Invoke-CimMethod Win32_Process Create`, as in Task 1 step 5, logging to `build-observe.log`.

- [ ] **Step 5: Poll until `DONE`.** Expected: `gn rc=0`, `Build Succeeded: <N> steps` with N > 0, `build rc=0`, and a version check of `out\Observe\chrome.exe` that reads `154.0.8037.93`.

- [ ] **Step 6: Release, then message canvas.**

Release the lock as `step2b-observe`. Then SendMessage: "Released build_lock. out\Release and out\Observe rebuilt at main `<MAIN>` (steps/wall: …). out\Observe now has v8_enable_runtime_call_stats = true, so E arm 1 can re-run on it."

### Task 3: `gpu_gate.py` and the interactive launcher

**Files:**
- Create: `scripts/gpu_gate.py`
- Create: `scripts/windows/run-interactive.ps1`
- Create: `scripts/test_gpu_gate.py`
- Modify: `.github/workflows/build-verify.yml:62` (the `cp` line)

**Interfaces:**
- Produces, in `gpu_gate`:
  - `GPU_JS: str`;
  - `crash_count(text: str | None) -> int | None`;
  - `class Unmeasured(Exception)` and `class GpuCrashed(Unmeasured)` with `.n: int | None`; `str(e)` is `UNMEASURED gpu-crash=<n|unknown>`;
  - `check(n) -> None`, which raises `GpuCrashed` unless `n == 0`;
  - `read_page(page) -> int | None`;
  - `read_ctx(ctx) -> int | None`;
  - `read_port(port: int) -> int | None`;
  - `session_id() -> int | None`;
  - `session_problem(sid: int | None) -> str | None`;
  - `require_interactive() -> None`, which exits 3 on session 0 unless `CAMOU_ALLOW_SESSION0=1`.
- Produces `run-interactive.ps1 -Name <n> -Command <ps> -Log <path>` and `-Name <n> -Remove`.

- [ ] **Step 1: Write the failing tests** in `scripts/test_gpu_gate.py`:
```python
"""gpu_gate's pure parts (S4: a GPU process that crashed at launch latches empty GPU answers)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gpu_gate as g  # noqa: E402

# The line's shape as chrome://gpu printed it on the host, 2026-10-13 (space before the colon).
S0 = "Video Decode: Hardware accelerated\nGPU process crash count :1\nWebGPU: Hardware accelerated but at reduced performance"
S1 = "Video Decode: Hardware accelerated\nGPU process crash count :0"


def test_crash_count_reads_the_host_shape():
    assert g.crash_count(S0) == 1
    assert g.crash_count(S1) == 0
    assert g.crash_count("GPU process crash count: 12") == 12


@pytest.mark.parametrize("text", [None, "", "Video Decode: Hardware accelerated", "GPU process crash count :"])
def test_no_count_line_is_none_not_zero(text):
    assert g.crash_count(text) is None


def test_check_passes_only_zero():
    g.check(0)
    for n in (1, None):
        with pytest.raises(g.GpuCrashed) as e:
            g.check(n)
        assert e.value.n == n
    assert str(g.GpuCrashed(1)) == "UNMEASURED gpu-crash=1"
    assert str(g.GpuCrashed(None)) == "UNMEASURED gpu-crash=unknown"
    assert isinstance(g.GpuCrashed(1), g.Unmeasured)


def test_session_problem_names_session_zero_only():
    assert g.session_problem(0).startswith("UNMEASURED session=0")
    assert g.session_problem(1) is None
    assert g.session_problem(None) is None  # off Windows


def test_require_interactive_exits_3_in_session_zero(monkeypatch, capsys):
    monkeypatch.setattr(g, "session_id", lambda: 0)
    monkeypatch.delenv("CAMOU_ALLOW_SESSION0", raising=False)
    with pytest.raises(SystemExit) as e:
        g.require_interactive()
    assert e.value.code == 3
    assert capsys.readouterr().out.startswith("UNMEASURED session=0")


def test_require_interactive_allows_a_red_run(monkeypatch, capsys):
    monkeypatch.setattr(g, "session_id", lambda: 0)
    monkeypatch.setenv("CAMOU_ALLOW_SESSION0", "1")
    g.require_interactive()
    assert "CAMOU_ALLOW_SESSION0=1" in capsys.readouterr().out


def test_session_id_is_none_off_windows():
    if os.name != "nt":
        assert g.session_id() is None
```

- [ ] **Step 2: Run them.**

Run: `python3 -m pytest -q scripts/test_gpu_gate.py`

Expected: errors with `ModuleNotFoundError: No module named 'gpu_gate'`.

- [ ] **Step 3: Write `scripts/gpu_gate.py`.**
```python
"""The GPU-process crash gate for browser runs on the Windows host.

S4 (docs/superpowers/measurements/2026-10-12-s4-gpu-session0.md): in Windows
session 0, where anything started through sshd, sshgate or Win32_Process runs,
the GPU process crashes once per launch, stock included. A renderer that
queried it in that window latches empty answers for its life: HEVC
["", false], sometimes a null WebGPU adapter and WebGL. A launch whose
chrome://gpu reports a crash measured nothing GPU-backed, so its rows are
UNMEASURED, never PASS or FAIL. Off Windows every entry point is a no-op.

  python gpu_gate.py PORT   prints the crash count of the browser on that DevTools port
"""
import os
import re
import subprocess
import sys
import time

# chrome://gpu nests shadow roots; every li/tr's text, one per line (S4's s4probe.gpu_page).
GPU_JS = ("(()=>{const o=[];const w=r=>{for(const e of r.querySelectorAll('*')){if(e.tagName==='LI'||e.tagName==='TR')"
          "o.push(e.textContent.replace(/\\s+/g,' ').trim());if(e.shadowRoot)w(e.shadowRoot)}};w(document);return o.join('\\n')})()")
# 2026-10-13 on the host: "GPU process crash count :1" in session 0, ":0" in session 1.
CRASH = re.compile(r"^GPU process crash count\s*:\s*(\d+)\s*$", re.M)


class Unmeasured(Exception):
    """A run that measured nothing; its rows are neither PASS nor FAIL."""


class GpuCrashed(Unmeasured):
    def __init__(self, n):
        self.n = n
        super().__init__(f"UNMEASURED gpu-crash={'unknown' if n is None else n}")


def crash_count(text):
    """The count from a chrome://gpu text, or None when the line is missing (never 0)."""
    m = CRASH.search(text or "")
    return int(m.group(1)) if m else None


def check(n):
    """None (the page had no count) is as unmeasured as a crash."""
    if n != 0:
        raise GpuCrashed(n)


def read_page(page, tries=20):
    page.goto("chrome://gpu", wait_until="load", timeout=15000)
    text = ""
    for _ in range(tries):
        text = page.evaluate(GPU_JS)
        if CRASH.search(text):
            break
        time.sleep(0.25)
    return crash_count(text)


def read_ctx(ctx):
    """The crash count of the browser behind a Playwright/patchright context, from a page of its own."""
    page = ctx.new_page()
    try:
        return read_page(page)
    finally:
        page.close()


def read_port(port, timeout=60):
    """The crash count of the browser on a DevTools port. The read runs in a child
    process, because the caller may be inside a sync Playwright block already."""
    try:
        p = subprocess.run([sys.executable, os.path.abspath(__file__), str(port)],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
    tail = (p.stdout.strip().splitlines() or ["None"])[-1]
    return int(tail) if tail.isdigit() else None


def session_id():
    """This process's Windows session id (0 = services), or None off Windows."""
    if os.name != "nt":
        return None
    import ctypes
    sid = ctypes.c_ulong()
    ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(sid))
    return sid.value


def session_problem(sid):
    if sid == 0:
        return ("UNMEASURED session=0: start this through scripts/windows/run-interactive.ps1 "
                "(in session 0 the GPU process crashes once per launch)")
    return None


def require_interactive():
    """Exit 3 in session 0. CAMOU_ALLOW_SESSION0=1 lets a RED run through, so the
    per-launch crash gates behind this can be seen to trip."""
    why = session_problem(session_id())
    if not why:
        return
    if os.environ.get("CAMOU_ALLOW_SESSION0") == "1":
        print("NOTE: CAMOU_ALLOW_SESSION0=1: session 0 allowed (a RED run)", flush=True)
        return
    print(why, flush=True)
    sys.exit(3)


if __name__ == "__main__":
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{sys.argv[1]}")
        print(read_ctx(browser.contexts[0]))
```

- [ ] **Step 4: Write `scripts/windows/run-interactive.ps1`.**
```powershell
<# Runs a command in the owner's interactive session through a temporary
scheduled task (S4, 2026-10-12: in session 0, where sshd/sshgate put a
shell, the GPU process crashes once per launch). The owner must be logged
on (RDP connected or disconnected); headed windows show on that desktop.

  powershell -NoProfile -ExecutionPolicy Bypass -File run-interactive.ps1 -Name step2b -Log D:\x.log -Command '<PowerShell>'
  powershell -NoProfile -ExecutionPolicy Bypass -File run-interactive.ps1 -Name step2b -Remove

The command runs after set-env.ps1; the log gets SESSION=<id> first and
EXIT=<rc> last. Poll the log, then -Remove. #>
param(
  [Parameter(Mandatory = $true)][string]$Name,
  [string]$Command,
  [string]$Log,
  [string]$EnvScript = 'D:\camou-win\set-env.ps1',
  [switch]$Remove
)
$task = "camou-$Name"
if ($Remove) {
  Unregister-ScheduledTask -TaskName $task -Confirm:$false
  "removed $task"
  return
}
if (-not $Command -or -not $Log) { throw '-Command and -Log are required' }
$dir = Join-Path $env:TEMP $task
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$body = Join-Path $dir 'run.ps1'
$text = @(
  '& {',
  "Invoke-Expression (Get-Content -Raw '$EnvScript')",
  '"SESSION=" + (Get-Process -Id $PID).SessionId',
  $Command,
  '"EXIT=" + $LASTEXITCODE',
  "} *> '$Log'"
) -join "`n"
[IO.File]::WriteAllText($body, $text, (New-Object Text.UTF8Encoding $true))
$a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File $body"
$p = New-ScheduledTaskPrincipal -UserId (whoami) -LogonType Interactive
$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 6)
Register-ScheduledTask -TaskName $task -Action $a -Principal $p -Settings $s -Force | Out-Null
Start-ScheduledTask -TaskName $task
"started $task log=$Log"
```

- [ ] **Step 5: Add `gpu_gate.py` to CI's copy line.** In `.github/workflows/build-verify.yml`, change the `cp scripts/verify_*.py scripts/lib_shell.py …` line to:
```yaml
          cp scripts/verify_*.py scripts/lib_shell.py scripts/gpu_gate.py scripts/capture_host_oracle.py scripts/echo_server.py scripts/observe_report.py "$VERIFY/"
```
Also add `scripts/test_gpu_gate.py` to that workflow's pytest list on line 86, after `scripts/test_windows_verify_set.py`.

- [ ] **Step 6: Run the tests.**

Run: `python3 -m pytest -q scripts/test_gpu_gate.py`

Expected: `7 passed` (on the Mac, `test_session_id_is_none_off_windows` passes trivially).

- [ ] **Step 7: Commit.**
```
git add scripts/gpu_gate.py scripts/test_gpu_gate.py scripts/windows/run-interactive.ps1 .github/workflows/build-verify.yml
git commit -F <msg>
```
Message: `feat(host): GPU-crash gate and interactive-session launcher (S4)`, with a body naming S4's rates, ending with the Co-Authored-By line.

### Task 4: Gate `lib_shell` launches and judge UNMEASURED in the Windows set

**Files:**
- Modify: `scripts/lib_shell.py` (`launch()` after Popen; `shutdown()`)
- Modify: `scripts/windows_verify_set.py` (`judge`, `main`)
- Test: `scripts/test_gpu_gate.py`, `scripts/test_windows_verify_set.py`

**Interfaces:**
- Consumes: `gpu_gate.read_port`, `gpu_gate.require_interactive`.
- Produces:
  - `lib_shell.gpu_gate_line(proc, osname=None, reader=None) -> str | None`;
  - `proc.binary_name` (lower-case basename) on every launched proc;
  - `windows_verify_set.unmeasured(stdout) -> list[str]`.

- [ ] **Step 1: Write the failing tests.** Append to `scripts/test_gpu_gate.py`:
```python
import types

import lib_shell  # noqa: E402


def proc(name="chrome.exe", port=9222):
    return types.SimpleNamespace(binary_name=name, cdp_port=port)


def test_lib_shell_gate_is_off_outside_windows_and_chrome():
    called = []
    reader = lambda port: called.append(port) or 1  # noqa: E731
    assert lib_shell.gpu_gate_line(proc(), osname="posix", reader=reader) is None
    assert lib_shell.gpu_gate_line(proc("content_shell.exe"), osname="nt", reader=reader) is None
    assert lib_shell.gpu_gate_line(proc(port=None), osname="nt", reader=reader) is None
    assert called == []


def test_lib_shell_gate_lines():
    assert lib_shell.gpu_gate_line(proc(), osname="nt", reader=lambda p: 0) is None
    assert lib_shell.gpu_gate_line(proc(), osname="nt", reader=lambda p: 1) == "UNMEASURED gpu-crash=1"
    assert lib_shell.gpu_gate_line(proc(), osname="nt", reader=lambda p: None) == "UNMEASURED gpu-crash=unknown"


def test_lib_shell_gate_fails_closed_when_the_read_raises():
    def boom(port):
        raise OSError("gone")
    assert lib_shell.gpu_gate_line(proc(), osname="nt", reader=boom) == "UNMEASURED gpu-crash=unknown"
```
Append to `scripts/test_windows_verify_set.py`:
```python
@pytest.mark.parametrize("mode", ["green", "red"])
def test_an_unmeasured_line_is_never_ok(mode):
    e = w.Entry("verify_x.py", 1, "stock")
    out = "PASS  a\nUNMEASURED gpu-crash=1\n" if mode == "green" else "FAIL  a\nUNMEASURED gpu-crash=1\n"
    ok, why = w.judge(mode, e, 0 if mode == "green" else 1, out)
    assert ok is False and why.startswith("UNMEASURED")


def test_unmeasured_lists_the_lines():
    assert w.unmeasured("PASS  a\nUNMEASURED session=0: x\nnote\n") == ["UNMEASURED session=0: x"]
    assert w.unmeasured("PASS  a\n") == []
```

- [ ] **Step 2: Run them.**

Run: `python3 -m pytest -q scripts/test_gpu_gate.py scripts/test_windows_verify_set.py`

Expected: FAIL with `AttributeError: module 'lib_shell' has no attribute 'gpu_gate_line'` and `... 'windows_verify_set' has no attribute 'unmeasured'`.

- [ ] **Step 3: Implement in `scripts/lib_shell.py`.**

In `launch()`, directly after `proc.profile_dir = profile if user_data_dir is None else ""`, add:
```python
    proc.binary_name = name.lower()
```

Add above `def shutdown(proc):`:
```python
def gpu_gate_line(proc, osname=None, reader=None):
    """On the Windows host, the UNMEASURED line for a chrome.exe launch whose GPU
    process crashed (gpu_gate.py, S4), else None. Off Windows, and for
    content_shell, this reads nothing: the Linux CI path stays as it was."""
    osname = os.name if osname is None else osname
    if osname != "nt" or getattr(proc, "binary_name", "") != "chrome.exe" or not getattr(proc, "cdp_port", None):
        return None
    if reader is None:
        import gpu_gate  # lazy: CI copies lib_shell without needing this on Linux
        reader = gpu_gate.read_port
    try:
        n = reader(proc.cdp_port)
    except Exception:  # noqa: BLE001 - an unreadable count is unmeasured, never 0
        n = None
    return None if n == 0 else f"UNMEASURED gpu-crash={'unknown' if n is None else n}"
```

In `shutdown(proc)`, insert as its first lines, before `proc.terminate()`:
```python
    line = gpu_gate_line(proc)
    if line:
        print(line, flush=True)
```

- [ ] **Step 4: Implement in `scripts/windows_verify_set.py`.**

Add below `count_rows`:
```python
def unmeasured(stdout):
    """UNMEASURED lines (gpu_gate.py): a launch that measured nothing GPU-backed, or a run in session 0."""
    return [line for line in stdout.splitlines() if line.startswith("UNMEASURED")]
```
In `judge`, insert as its first statement:
```python
    um = unmeasured(stdout)
    if um:
        return False, f"UNMEASURED ({len(um)}): {um[0]}"
```
In `main`, insert directly after the `mode = argv[1]` line:
```python
    import gpu_gate
    gpu_gate.require_interactive()
```
Change the final summary print to:
```python
    um = sum(1 for e in entries if (logs / f"{e.script}.log").exists()
             and unmeasured((logs / f"{e.script}.log").read_text(encoding="utf-8")))
    print(f"{good}/{len(entries)} entries OK ({mode}); {um} UNMEASURED")
```

- [ ] **Step 5: Run the tests, plus the frozen-argv check.**

Run: `python3 -m pytest -q scripts/test_gpu_gate.py scripts/test_windows_verify_set.py && python3 scripts/test_lib_shell_launch.py`

Expected: all pass. `test_lib_shell_launch.py` prints its usual OK.

- [ ] **Step 6: Commit** `scripts/lib_shell.py scripts/windows_verify_set.py scripts/test_gpu_gate.py scripts/test_windows_verify_set.py` with message `feat(host): lib_shell gates each Windows chrome launch on its GPU crash count; the set judges UNMEASURED` (Co-Authored-By line).

### Task 5: Gate `verify_host_oracle` and `verify_s3_host`

**Files:**
- Modify: `scripts/verify_host_oracle.py` (`main`, `font_access_rows`, `brand_header_rows`)
- Modify: `scripts/verify_s3_host.py` (`main`)

**Interfaces:**
- Consumes: `gpu_gate.require_interactive`, `gpu_gate.read_ctx`, `gpu_gate.GpuCrashed`, and Task 7's gated `measure_step2.opened` (used by `verify_s3_host.one`/`session`).

These scripts are host-run integration code, so their proof is Task 9's host RED/GREEN, not a unit test.

- [ ] **Step 1: `verify_host_oracle.main()`.** Insert as the first lines of `main()`:
```python
    if os.name == "nt":
        import gpu_gate  # lazy: CI runs this file on Linux from $VERIFY
        # O1/O2 launch through camoucrome.probe, which gives no context to read chrome://gpu from:
        # the session check stands in for the crash count there (S4: session 0 crashed every launch).
        gpu_gate.require_interactive()
```

- [ ] **Step 2: O3 and O4 read the count.** In the `script` string of `font_access_rows`, replace the line `    ctx.close()` with:
```python
    if os.name == "nt":
        sys.path.insert(0, {json.dumps(str(CLIENT / "scripts"))})
        import gpu_gate
        out["gpu"] = gpu_gate.read_ctx(ctx)
    ctx.close()
```
Also add `import os` to that script's first line, so it reads `import json, os, sys`.

In `brand_header_rows`'s `script` string, replace `    ctx.close()` with:
```python
    if os.name == "nt":
        import gpu_gate
        out["gpu"] = gpu_gate.read_ctx(ctx)
    ctx.close()
```
Add `import os` there too, so it reads `import json, os, sys`. Its path already includes `CLIENT / "scripts"`.

In both functions, directly after `r = json.loads(p.stdout.strip().splitlines()[-1])`, add:
```python
    if os.name == "nt" and r.get("gpu") != 0:
        print(f"UNMEASURED gpu-crash={'unknown' if r.get('gpu') is None else r['gpu']} (O3)")
```
In `brand_header_rows`, use `(O4)` instead.

- [ ] **Step 3: `verify_s3_host.main()`.** Wrap the body so a gate trip ends the run as UNMEASURED. At the top of `main()`:
```python
    import gpu_gate
    gpu_gate.require_interactive()
```
Change `with sync_playwright() as pw:` and its block so they sit inside:
```python
    try:
        with sync_playwright() as pw:
            ...  # the existing block, unchanged
    except gpu_gate.GpuCrashed as exc:
        print(exc)
        sys.exit(3)
```

- [ ] **Step 4: Check the Linux path is unchanged.**

Run: `python3 -m pytest -q scripts/ && python3 -c "import ast,sys; [ast.parse(open(f).read()) for f in ('scripts/verify_host_oracle.py','scripts/verify_s3_host.py')]; print('parse ok')"`

Expected: the whole suite passes, then `parse ok`.

- [ ] **Step 5: Commit** both files with message `feat(host): host oracle and S3 host verifies refuse session 0 and gated launches` (Co-Authored-By line).

### Task 6: Verdict parsers, the verdict table and `scrub()` in `step2_rows`

**Files:**
- Modify: `scripts/step2_rows.py`
- Test: `scripts/test_step2_rows.py`

**Interfaces:**
- Produces:
  - `parse_rebrowser(text) -> dict[str, str]` with values `pass|fail|not triggered`;
  - `parse_dbi(text) -> dict[str, bool]`;
  - `parse_incolumitas(text) -> dict[str, str]` with values `OK|FAIL`;
  - `parse_fingerprint_pro(text) -> dict[str, str]`;
  - `blocked(text) -> str` with values `cloudflare challenge|no`;
  - `VERDICT_SITES: tuple[str, ...]`;
  - `verdict_table(doc) -> list[str]`;
  - `scrub(value, geo: dict[str, list[str]])`.
- `PARSERS` gains `detect_headless` (`parse_tabbed`), `rebrowser`, `dbi_bot`, `incolumitas` and `fingerprint_pro`.

- [ ] **Step 1: Write the failing tests.** Append to `scripts/test_step2_rows.py`. Every fixture is synthetic: it keeps the format seen on 2026-10-13 and holds no host value.
```python
REBROWSER = (
    "Test name\tTime since load\tNotes\n"
    "\u26aa\ufe0f dummyFn\t0.2 ms\tCall window.dummyFn() to test if you can access main world objects.\n"
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
    ("HeadlessChrome/154.0.8037.93 Safari/537.36", "HeadlessChrome/154.0.8037.93 Safari/537.36"),
    ("at 10:00:00 on 2026-10-13T17:15:42.195Z", "at 10:00:00 on 2026-10-13T17:15:42.195Z"),
    ("mac aa:bb:cc:dd:ee:ff", "mac aa:bb:cc:dd:ee:ff"),
    ("Somewhere City, Region (SC), Land", "<city>, <region> (SC), <country>"),
])
def test_scrub(raw, want):
    geo = {"<city>": ["Somewhere City"], "<region>": ["Region"], "<country>": ["Land"]}
    assert r.scrub(raw, geo) == want


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
```
The columns are ordered by mode, then arm: `control headed | fork headed | control headless | fork headless`.

- [ ] **Step 2: Run them.**

Run: `python3 -m pytest -q scripts/test_step2_rows.py`

Expected: FAIL with `AttributeError: module 'step2_rows' has no attribute 'parse_rebrowser'` and the like.

- [ ] **Step 3: Implement.** In `scripts/step2_rows.py`, add `import ipaddress` to the imports. Replace the line `PARSERS = {"sannysoft": parse_tabbed, "creepjs": parse_colon}` with:
```python
# step2b verdict parsers: each shape fixed from its first stock capture (2026-10-13), each
# fixture in test_step2_rows.py synthetic in that shape.
REBROWSER_STATUS = {"\U0001f7e2": "pass", "\U0001f534": "fail", "\u26aa": "not triggered"}
REBROWSER_ROW = re.compile("^(\U0001f7e2|\U0001f534|\u26aa)\ufe0f?\\s*(\\w+)\\t")
JSON_BOOL = re.compile(r'^\s*"(\w+)": (true|false),?$')
JSON_OKFAIL = re.compile(r'^\s*"(\w+)": "(OK|FAIL)",?$')
# Fingerprint Pro's smart signals; Geolocation, IP Address, Visitor ID and Velocity carry the host.
FP_PRO_SIGNALS = ("Incognito Mode", "Bot", "VPN", "Browser Tampering", "Developer Tools", "Virtual Machine",
                  "Privacy Settings", "IP Blocklist", "Proxy Detection", "High-Activity Device", "Rare Device",
                  "Suspect Score")


def parse_rebrowser(text):
    """rebrowser-bot-detector: "<status emoji> <test>\\t<ms>\\t<notes>" per test."""
    out = {}
    for line in text.splitlines():
        m = REBROWSER_ROW.match(line)
        if m:
            out.setdefault(m.group(2), REBROWSER_STATUS[m.group(1)])
    return out


def parse_dbi(text):
    """deviceandbrowserinfo are_you_a_bot: the raw-detection JSON's booleans. The prose
    below it repeats every key with a colon, so only the quoted JSON form counts."""
    out = {}
    for line in text.splitlines():
        m = JSON_BOOL.match(line)
        if m:
            out.setdefault(m.group(1), m.group(2) == "true")
    return out


def parse_incolumitas(text):
    """bot.incolumitas.com: "name": "OK"|"FAIL" lines; the first occurrence of a name wins."""
    out = {}
    for line in text.splitlines():
        m = JSON_OKFAIL.match(line)
        if m:
            out.setdefault(m.group(1), m.group(2))
    return out


def parse_fingerprint_pro(text):
    """Fingerprint Pro playground: a signal's label line ends in a tab, its value is the next non-empty line."""
    raw, out = text.splitlines(), {}
    for i, line in enumerate(raw):
        k = line.strip()
        if k in FP_PRO_SIGNALS and line.endswith("\t") and k not in out:
            out[k] = next((x.strip() for x in raw[i + 1:i + 4] if x.strip()), ABSENT)
    return out


def blocked(text):
    """A Cloudflare interstitial in place of the page (whoer.net to headless stock, 2026-10-13)."""
    return "cloudflare challenge" if "Performing security verification" in text else "no"


PARSERS = {"sannysoft": parse_tabbed, "creepjs": parse_colon, "detect_headless": parse_tabbed,
           "rebrowser": parse_rebrowser, "dbi_bot": parse_dbi, "incolumitas": parse_incolumitas,
           "fingerprint_pro": parse_fingerprint_pro}
VERDICT_SITES = ("rebrowser", "dbi_bot", "incolumitas", "fingerprint_pro")


def _verdict_row(name):
    parts = name.split(".")
    return len(parts) >= 3 and parts[0] == "det" and (parts[1] in VERDICT_SITES or parts[2] == "blocked")


def verdict_table(doc):
    """Every verdict row in all four cells, equal or not: both arms flagged is a finding too."""
    cells = doc["rows"].get("detectors") or {}
    cols = [(arm, mode) for mode in MODES for arm in ARMS]
    got = {c: (cells.get(c[0]) or {}).get(c[1]) for c in cols}
    names = sorted({k for v in got.values() if v for k in v if _verdict_row(k)})

    def val(cell, name):
        if cell is None or cell.get(".".join(name.split(".")[:2])) == UNMEASURED:
            return UNMEASURED
        return _cell(cell.get(name, ABSENT))
    out = ["## verdicts", "", "| row | " + " | ".join(f"{a} {m}" for a, m in cols) + " |", "|---" * (len(cols) + 1) + "|"]
    out += [f"| {n} | " + " | ".join(val(got[c], n) for c in cols) + " |" for n in names]
    return out + [""]


_IP_TOKEN = re.compile(r"(?<![\w:.])[0-9A-Fa-f:.]*[.:][0-9A-Fa-f:.]*(?![\w:.])")
_COORD = re.compile(r"-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}")


def _ip(tok):
    head, _, port = tok.rpartition(":")
    for cand, tail in ((tok, ""), (head, ":" + port)):
        try:
            a = ipaddress.ip_address(cand)
        except ValueError:
            continue
        return ("<ip>" if a.version == 4 else "<ip6>") + tail
    return tok


def scrub(value, geo):
    """`value` (str, or list/dict walked recursively) with IP addresses, coordinate pairs and the
    host's geo strings replaced. A candidate counts as an address only if ipaddress parses it, so
    a version (154.0.8037.93) or a clock (10:00:00) stays. `geo` maps a placeholder to the strings
    it replaces; it comes from CAMOU_SCRUB on the host and is never committed."""
    if isinstance(value, dict):
        return {scrub(k, geo): scrub(v, geo) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v, geo) for v in value]
    if not isinstance(value, str):
        return value
    s = _COORD.sub("<coord>", _IP_TOKEN.sub(lambda m: _ip(m.group(0)), value))
    for label, needles in geo.items():
        for n in sorted(needles, key=len, reverse=True):
            s = s.replace(n, label)
    return s
```
At the end of `render_tables`, change `return "\n".join(out) + "\n"` to:
```python
    if "detectors" in doc["rows"]:
        out += verdict_table(doc)
    return "\n".join(out) + "\n"
```

- [ ] **Step 4: Run the tests.**

Run: `python3 -m pytest -q scripts/test_step2_rows.py`

Expected: all pass. If the coordinate row fails because `_IP_TOKEN` took `10.7623`, the `_COORD` substitution must run first. Swap the order to `_IP_TOKEN.sub(..., _COORD.sub("<coord>", value))` and re-run.

- [ ] **Step 5: Run the whole suite.**

Run: `python3 -m pytest -q scripts/ client/python/tests`

Expected: all pass.

- [ ] **Step 6: Commit** `scripts/step2_rows.py scripts/test_step2_rows.py` with message `feat(step2b): verdict parsers, verdict table and scrub()` (Co-Authored-By line).

### Task 7: Gate `measure_step2` launches, and the 20-site table

**Files:**
- Modify: `scripts/measure_step2.py` (`opened`, `DETECTORS`, `probe_detectors`, `write_tables`, `run_cmd`, `main`; new `scrub_cmd`, `desktop_size`)
- Test: `scripts/test_step2_rows.py`

**Interfaces:**
- Consumes: `gpu_gate.read_ctx`, `gpu_gate.check`, `gpu_gate.GpuCrashed`, `gpu_gate.require_interactive`, `gpu_gate.session_id`.
- Consumes from Task 6: `rows.blocked(text) -> str`, `rows.PARSERS`, `rows.scrub(value, geo)`.
- Produces:
  - `DETECTORS: dict[str, str]` with 20 entries and no dot in any name;
  - `measure_step2.py scrub RUN OUT`;
  - each detectors cell writes `det.<site>`, `det.<site>.blocked`, `det.<site>.gpu_crash` (only on a gate trip) and the parser rows.

- [ ] **Step 1: Write the failing tests.** Append to `scripts/test_step2_rows.py`:
```python
def test_detectors_are_the_twenty_live_sites():
    import measure_step2 as m
    assert len(m.DETECTORS) == 20
    assert all("." not in name for name in m.DETECTORS)  # label_rows finds a site from the first two dotted parts
    assert all(url.startswith("https://") for url in m.DETECTORS.values())
    for dropped in ("brotector", "botd", "areyouheadless", "turnstile"):
        assert dropped not in m.DETECTORS


def test_a_gated_detector_launch_leaves_no_text(tmp_path, monkeypatch):
    import contextlib
    import argparse
    import gpu_gate
    import measure_step2 as m

    class Page:
        def goto(self, *a, **k): pass
        def screenshot(self, path, **k): open(path, "wb").write(b"png")

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
```

- [ ] **Step 2: Run them.**

Run: `python3 -m pytest -q scripts/test_step2_rows.py -k "detectors or gated"`

Expected: FAIL. `len(m.DETECTORS) == 4`, and the gated test either finds raw files left behind or `GpuCrashed` propagates.

- [ ] **Step 3: Gate `opened()`.** Add `import gpu_gate  # noqa: E402` after `import step2_rows as rows`. Replace the body of `opened`'s `try/finally` with:
```python
    try:
        yield ctx
        # S4: a launch whose GPU process crashed measured nothing GPU-backed.
        gpu_gate.check(gpu_gate.read_ctx(ctx))
    finally:
        ctx.close()
```

- [ ] **Step 4: Replace `DETECTORS`** (keep the pixelscan comment below it):
```python
# The 2026-10-13 stock capture (step2b) dropped brotector and botd (GitHub Pages 404),
# arh.antoinevastel.com (502) and demo.turnstile.workers.dev (a dummy-sitekey token from
# 3 s on: it measures nothing). Names carry no dot: label_rows reads a site from two dotted parts.
DETECTORS = {
    "sannysoft": "https://bot.sannysoft.com/",
    "creepjs": "https://abrahamjuliot.github.io/creepjs/",
    "browserscan": "https://www.browserscan.net/",
    "pixelscan": "https://pixelscan.net/fingerprint-check",
    "rebrowser": "https://bot-detector.rebrowser.net/",
    "dbi_bot": "https://deviceandbrowserinfo.com/are_you_a_bot",
    "incolumitas": "https://bot.incolumitas.com/",
    "detect_headless": "https://infosimples.github.io/detect-headless/",
    "browserleaks_javascript": "https://browserleaks.com/javascript",
    "browserleaks_canvas": "https://browserleaks.com/canvas",
    "browserleaks_webgl": "https://browserleaks.com/webgl",
    "browserleaks_webrtc": "https://browserleaks.com/webrtc",
    "browserleaks_fonts": "https://browserleaks.com/fonts",
    "browserleaks_client_hints": "https://browserleaks.com/client-hints",
    "browserleaks_tls": "https://browserleaks.com/tls",
    "iphey": "https://iphey.com/",
    "whoer": "https://whoer.net/",
    "amiunique": "https://amiunique.org/fingerprint",
    "fingerprint_scan": "https://fingerprint-scan.com/",
    "fingerprint_pro": "https://demo.fingerprint.com/playground",
}
```

- [ ] **Step 5: Replace `probe_detectors`.**
```python
def probe_detectors(pw, arm, mode, run):
    out = {}
    for site, url in DETECTORS.items():
        stem = run.dir / "raw" / f"{site}-{arm.name}-{mode}"
        text = None
        try:
            with opened(pw, arm, mode) as ctx:
                page = first_page(ctx)
                try:
                    page.goto(url, wait_until="load", timeout=60000)
                    text = settle(page)
                except Exception:  # noqa: BLE001 - a page that does not load is not measured
                    text = None
                if text is not None:
                    stem.with_suffix(".txt").write_text(text, encoding="utf-8")
                    page.screenshot(path=str(stem.with_suffix(".png")), full_page=True)
        except gpu_gate.GpuCrashed as exc:
            # Nothing this launch read counts, and its text must not reach the line diff.
            for p in (stem.with_suffix(".txt"), stem.with_suffix(".png")):
                p.unlink(missing_ok=True)
            out[f"det.{site}"], out[f"det.{site}.gpu_crash"] = rows.UNMEASURED, exc.n
            continue
        if text is None:
            out[f"det.{site}"] = rows.UNMEASURED
            continue
        out[f"det.{site}"] = "ok"
        out[f"det.{site}.blocked"] = rows.blocked(text)
        out.update({f"det.{site}.{k}": v for k, v in rows.PARSERS.get(site, lambda t: {})(text).items()})
    return out
```

- [ ] **Step 6: `write_tables` reads every detector's text.** Replace its loop header `for site in rows.PARSERS.keys() | {"browserscan", "pixelscan"}:` with `for site in DETECTORS:`.

- [ ] **Step 7: Session precondition, desktop size, scrub subcommand.**

Add above `run_cmd`:
```python
def desktop_size():
    """The interactive desktop's size: a headed window cannot exceed it (step 2's outerMinusInner artefact)."""
    if os.name != "nt":
        return None
    import ctypes
    return [ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)]
```
In `run_cmd`, as the first statement:
```python
    gpu_gate.require_interactive()
```
In `run_cmd`'s `doc = {...}`, add the keys `"session": gpu_gate.session_id(), "desktop": desktop_size(),`.

Add below `compare_cmd`:
```python
def scrub_cmd(a):
    """The committable copy of a run: rows.json and tables.md through rows.scrub()."""
    geo = json.loads(os.environ.get("CAMOU_SCRUB") or "null")
    if not isinstance(geo, dict) or not geo:
        sys.exit("scrub: set CAMOU_SCRUB to a JSON object {placeholder: [host geo strings]}; it is never committed")
    src, dst = pathlib.Path(a.run_dir), pathlib.Path(a.out_dir)
    dst.mkdir(parents=True, exist_ok=True)
    doc = rows.scrub(json.loads((src / "rows.json").read_text(encoding="utf-8")), geo)
    (dst / "rows.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    (dst / "tables.md").write_text(rows.scrub((src / "tables.md").read_text(encoding="utf-8"), geo), encoding="utf-8")
    print(f"scrubbed {src} -> {dst}")
    return 0
```
In `main`, add the subparser after `t.add_argument("run_dir")`:
```python
    s = sub.add_parser("scrub")
    s.add_argument("run_dir")
    s.add_argument("out_dir")
```
Change the dispatch so `scrub` is handled before `write_tables`:
```python
    if a.cmd == "scrub":
        return scrub_cmd(a)
```
Update the module docstring's usage block with `python measure_step2.py scrub RUN OUT   (needs CAMOU_SCRUB)`.

- [ ] **Step 8: Run the tests.**

Run: `python3 -m pytest -q scripts/test_step2_rows.py`

Expected: all pass. That includes the two new tests, with Task 6's `rows.blocked` in place.

- [ ] **Step 9: Commit** `scripts/measure_step2.py scripts/test_step2_rows.py` with message `feat(step2b): 20 detector sites, GPU-gated launches, scrub subcommand` (Co-Authored-By line).

### Task 8: `winhost.py` in the interactive session, with its gates

**Files:**
- Modify: `scripts/winhost.py` (`powershell`, `cdp_eval`, `cdp_headers`, `CdpChrome.__exit__`; new `PS_IN_SESSION`, `in_session`, `session_gate`, `PS_GPU`, `crash_gate`)
- Test: `scripts/test_winhost.py`

**Interfaces:**
- Consumes: `gpu_gate.GPU_JS`, `gpu_gate.crash_count`, `gpu_gate.GpuCrashed`, `gpu_gate.Unmeasured`, `gpu_gate.session_problem`, `gpu_gate.read_port`.
- Produces:
  - `winhost.in_session(script: str, timeout_s: int) -> str`;
  - `winhost.session_gate(out: str) -> None`;
  - `winhost.crash_gate(out: str) -> None`.
- Env: `CAMOU_WINHOST_NO_TASK=1` (no task wrapper; for the session RED); `CAMOU_ALLOW_SESSION0=1` (no session gate; for the crash RED).

- [ ] **Step 1: Write the failing tests.** Append to `scripts/test_winhost.py`:
```python
import base64

import gpu_gate  # noqa: E402


def test_in_session_registers_an_interactive_task_and_cleans_up():
    ps = winhost.in_session('"hello"', 90)
    for needle in ("New-ScheduledTaskPrincipal -UserId (whoami) -LogonType Interactive", "Register-ScheduledTask",
                   "Start-ScheduledTask", "Unregister-ScheduledTask", "AddSeconds(90)"):
        assert needle in ps
    b64 = ps.split('FromBase64String("')[1].split('"')[0]
    assert base64.b64decode(b64).decode() == '"hello"'


@pytest.mark.parametrize("out,raises", [
    ("SESSION=1\nx", None),
    ("SESSION=0\nx", "UNMEASURED session=0"),
    ("x", "UNMEASURED session=unknown"),
])
def test_session_gate(out, raises, monkeypatch):
    monkeypatch.delenv("CAMOU_ALLOW_SESSION0", raising=False)
    if raises is None:
        winhost.session_gate(out)
    else:
        with pytest.raises(gpu_gate.Unmeasured) as e:
            winhost.session_gate(out)
        assert str(e.value).startswith(raises)


def test_session_gate_off_for_a_red(monkeypatch):
    monkeypatch.setenv("CAMOU_ALLOW_SESSION0", "1")
    winhost.session_gate("SESSION=0\n")


def gpu_out(text):
    return 'GPU_BEGIN\n{"id":9,"result":{"result":{"type":"string","value":' + json.dumps(text) + "}}}\nGPU_END\n"


def test_crash_gate():
    winhost.crash_gate(gpu_out("GPU process crash count :0"))
    with pytest.raises(gpu_gate.GpuCrashed) as e:
        winhost.crash_gate(gpu_out("GPU process crash count :1"))
    assert e.value.n == 1
    with pytest.raises(gpu_gate.GpuCrashed):
        winhost.crash_gate("GPU_BEGIN\nGPU_END\n")  # no reading is not a pass


def test_cdp_paths_read_chrome_gpu(captured):
    winhost.cdp_eval("<p>")
    winhost.cdp_headers("https://a/", seconds=0)
    assert all("json/new?chrome://gpu" in s and "GPU_BEGIN" in s for s in captured)
```
Check that the existing `captured` fixture's fake output passes the new gates. It must include `SESSION=1` and a GPU block with count 0. Change the fake's return value in that fixture to:
```python
        return ('SESSION=1\n<pre id="o">{}</pre>\nCDP_RESULT_BEGIN\n{"result":{"result":{"value":1}}}\nCDP_RESULT_END\n'
                'CDP_EVENTS_BEGIN\n\nCDP_EVENTS_END\n'
                'GPU_BEGIN\n{"id":9,"result":{"result":{"type":"string","value":"GPU process crash count :0"}}}\nGPU_END\n')
```
Add `import json` at the top of the test file if it is missing.

- [ ] **Step 2: Run them.**

Run: `python3 -m pytest -q scripts/test_winhost.py`

Expected: FAIL with `AttributeError: module 'winhost' has no attribute 'in_session'`.

- [ ] **Step 3: Implement.** In `scripts/winhost.py`, add `import gpu_gate` after `import subprocess`. Replace `powershell`:
```python
PS_IN_SESSION = r"""
$t = "camou-winhost-" + $PID
$d = Join-Path $env:TEMP $t
New-Item -ItemType Directory -Force -Path $d | Out-Null
$body = Join-Path $d "body.ps1"
$out = Join-Path $d "out.txt"
$inner = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("__B64__"))
[IO.File]::WriteAllText($body, "& {`n" + $inner + "`n} *> '" + $out + "'", (New-Object Text.UTF8Encoding $true))
$a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ("-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File " + $body)
$p = New-ScheduledTaskPrincipal -UserId (whoami) -LogonType Interactive
Register-ScheduledTask -TaskName $t -Action $a -Principal $p -Force | Out-Null
Start-ScheduledTask -TaskName $t
Start-Sleep -Seconds 1
$deadline = (Get-Date).AddSeconds(__TIMEOUT__)
while ((Get-ScheduledTask -TaskName $t).State -eq "Running" -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
if ((Get-ScheduledTask -TaskName $t).State -eq "Running") { Stop-ScheduledTask -TaskName $t; "IN_SESSION_TIMEOUT" }
Unregister-ScheduledTask -TaskName $t -Confirm:$false
if (Test-Path $out) { Get-Content -Raw $out }
Remove-Item -Recurse -Force $d -ErrorAction SilentlyContinue
"""
SESSION_LINE = '"SESSION=" + (Get-Process -Id $PID).SessionId\n'


def in_session(script, timeout_s):
    """`script` run by a temporary scheduled task in the owner's interactive session
    (S4: in session 0, where sshd puts this shell, the GPU process crashes once per
    launch). The output comes back through a file; the task is removed afterwards."""
    b64 = base64.b64encode(script.encode()).decode()
    return PS_IN_SESSION.replace("__B64__", b64).replace("__TIMEOUT__", str(int(timeout_s)))


def session_gate(out):
    """Refuse output from session 0, or with no SESSION line, unless CAMOU_ALLOW_SESSION0=1 (a RED)."""
    if os.environ.get("CAMOU_ALLOW_SESSION0") == "1":
        return
    m = re.search(r"^SESSION=(\d+)$", out, re.M)
    why = (gpu_gate.session_problem(int(m.group(1))) if m
           else "UNMEASURED session=unknown: the host printed no SESSION line")
    if why:
        print(why, flush=True)
        raise gpu_gate.Unmeasured(why)


def powershell(script, timeout=300):
    script = SESSION_LINE + script
    if os.environ.get("CAMOU_WINHOST_NO_TASK") != "1":
        script = in_session(script, timeout)
    p = subprocess.run(SSH + [script], capture_output=True, text=True, timeout=timeout + 60)
    if p.returncode != 0:
        raise RuntimeError(f"powershell rc={p.returncode}: {p.stderr[-800:]}")
    out = p.stdout.replace("\r", "")
    session_gate(out)
    return out
```
Add below `PS_CDP`:
```python
# Opens chrome://gpu as a new target of the browser on `port` and prints Runtime.evaluate's answer.
PS_GPU = r"""
try { $gt = (Invoke-WebRequest -UseBasicParsing -Method Put "http://127.0.0.1:__PORT__/json/new?chrome://gpu").Content | ConvertFrom-Json } catch { $gt = $null }
"GPU_BEGIN"
if ($gt) {
  Start-Sleep -Seconds 3
  $gw = Cdp-Connect $gt.webSocketDebuggerUrl
  Cdp-Send $gw @{ id = 9; method = "Runtime.evaluate"; params = @{ expression = __JS__; returnByValue = $true } }
  for ($i = 0; $i -lt 10; $i++) { $m = Cdp-Recv $gw 5000; if ($m -and $m.StartsWith('{"id":9,')) { $m; break } }
  $gw.Dispose()
}
"GPU_END"
"""


def ps_gpu(port=9333):
    return PS_GPU.replace("__PORT__", str(port)).replace("__JS__", ps_quote(gpu_gate.GPU_JS))


def crash_gate(out):
    """GpuCrashed unless the GPU block reads a crash count of 0 (a missing reading is not a pass)."""
    m = re.search(r"GPU_BEGIN\n(.*?)GPU_END", out, re.S)
    text = None
    if m and m.group(1).strip():
        try:
            text = json.loads(m.group(1).strip().splitlines()[0])["result"]["result"]["value"]
        except (ValueError, KeyError, IndexError, TypeError):
            text = None
    n = gpu_gate.crash_count(text)
    if n != 0:
        e = gpu_gate.GpuCrashed(n)
        print(e, flush=True)
        raise e
```
In `cdp_eval`'s PS f-string, insert `{ps_gpu()}` on its own line directly before the line `$ws.Dispose()`. In Python, directly after `out = powershell(ps, timeout=180)`, add `crash_gate(out)`.

In `cdp_headers`'s PS f-string, insert `{ps_gpu()}` directly before `$ws.Dispose()`. After `out = powershell(ps, timeout=seconds + 120)`, add `crash_gate(out)`.

Replace `CdpChrome.__exit__`:
```python
    def __exit__(self, *a):
        # The count is read over the forward before it closes; a run already failing keeps its own exception.
        n = gpu_gate.read_port(self.port) if self.forward and a[0] is None else 0
        if self.forward:
            self.forward.kill()
        powershell(f"Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object {{ $_.CommandLine -like '*remote-debugging-port={self.port}*' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}; 'STOPPED'")
        if n != 0:
            e = gpu_gate.GpuCrashed(n)
            print(e, flush=True)
            raise e
```
Update the module docstring: every launch runs in the owner's interactive session through a temporary task, and output from session 0 is refused.

- [ ] **Step 4: Run the tests.**

Run: `python3 -m pytest -q scripts/test_winhost.py && python3 -m pytest -q scripts/`

Expected: all pass.

- [ ] **Step 5: Commit** `scripts/winhost.py scripts/test_winhost.py` with message `feat(host): winhost launches in the interactive session; CDP paths gate on chrome://gpu` (Co-Authored-By line).

### Task 9: Host REDs and GREENs for every gate

**Files:** none in the repo. Host: `D:\camou-win\cn\step2b\gate-*.log`. Mac: the evidence goes into Task 11's doc.

**Interfaces:**
- Consumes: Tasks 1, 3–8 committed, and the branch on the host.

- [ ] **Step 1: Ship the branch to the host tree.**
  - Push the branch: `git push -u origin step2b-detectors`.
  - Archive it in the runner clone (Task 1 step 2's command with `git fetch -q origin step2b-detectors` and `FETCH_HEAD`).
  - Untar it into `D:\camou-win\tree` (Task 1 step 3), and write `tree.commit`.
  - On the WSL box, copy `scripts/winhost.py scripts/gpu_gate.py` from that archive into `~/camoucrome-verify/` only for the winhost rows, and restore the originals after step 5.
  - Expected: `D:\camou-win\tree\scripts\gpu_gate.py` exists.

- [ ] **Step 2: Lock and message.** Message canvas, then acquire as `step2b-gates`. Expected: `acquired by step2b-gates`.

- [ ] **Step 3: Session gate REDs (session 0, run directly over sshgate).**

Run each with `Invoke-Expression (Get-Content -Raw D:\camou-win\set-env.ps1); cmd /c "<python> <script> 2>&1"`, where `<python>` is `D:\camou-win\client-venv\Scripts\python.exe` and the scripts are under `D:\camou-win\tree\scripts`. In the `CAMOU_FORK_EXE` lines, `<fork>` is `D:\camou-win\chromium\src\out\Release\chrome.exe`.

| command | expected stdout | rc |
|---|---|---|
| `windows_verify_set.py green --only verify_sp1b.py` | `UNMEASURED session=0: …` | 3 |
| `verify_host_oracle.py` | `UNMEASURED session=0: …` | 3 |
| `$env:CAMOU_FORK_EXE='<fork>'; verify_s3_host.py` | `UNMEASURED session=0: …` | 3 |
| `$env:CAMOU_FORK_EXE='<fork>'; measure_step2.py run --only noise --modes headless` | `UNMEASURED session=0: …` | 3 |

- [ ] **Step 4: Crash gate REDs (session 0, `$env:CAMOU_ALLOW_SESSION0='1'`).**

| command | expected |
|---|---|
| `verify_sp1b.py` (through lib_shell, with the set's env: `$env:CAMOU_SHELL='chrome'`) | at least one `UNMEASURED gpu-crash=1` line |
| `windows_verify_set.py green --only verify_sp1b.py` | `BAD  verify_sp1b.py: UNMEASURED (…): UNMEASURED gpu-crash=1`, summary `0/1 entries OK (green); 1 UNMEASURED`, rc 1 |
| `verify_host_oracle.py` | `UNMEASURED gpu-crash=1 (O3)` and `UNMEASURED gpu-crash=1 (O4)` |
| `verify_s3_host.py` (with `CAMOU_FORK_EXE`) | `UNMEASURED gpu-crash=1`, rc 3 |
| `measure_step2.py run --only noise --modes headless` (with `CAMOU_FORK_EXE`) | `noise/control/headless: ERROR`; the run's `rows.json` `errors` names `GpuCrashed: UNMEASURED gpu-crash=1`; `tables.md` shows `UNMEASURED: GpuCrashed: …` |
| `measure_step2.py run --only detectors --modes headless` with `DETECTORS` cut to `sannysoft` by a one-off `-c` wrapper: `import measure_step2 as m; m.DETECTORS={'sannysoft': m.DETECTORS['sannysoft']}; m.main(['run','--only','detectors','--modes','headless'])` | `rows.json`: `det.sannysoft` = `UNMEASURED` and `det.sannysoft.gpu_crash` = 1 on both arms; `raw/` has no `sannysoft-*.txt` |

- [ ] **Step 5: winhost REDs and GREENs, from the WSL box** (`~/camoucrome-verify/venv/bin/python3`, in `~/camoucrome-verify`).

| env | call | expected |
|---|---|---|
| `CAMOU_WINHOST_NO_TASK=1` | `python3 -c "import winhost; print(winhost.dump_dom('<pre id=o>{\"a\":1}</pre>'))"` | `UNMEASURED session=0: …` and `Unmeasured` raised |
| `CAMOU_WINHOST_NO_TASK=1 CAMOU_ALLOW_SESSION0=1` | `python3 -c "import winhost; print(winhost.cdp_eval('<pre id=o>1</pre>'))"` | `UNMEASURED gpu-crash=1` and `GpuCrashed` raised |
| (none) | the same `dump_dom` call | `{'a': 1}`; the host has no leftover `camou-winhost-*` task (`Get-ScheduledTask camou-*` empty) |
| (none) | the same `cdp_eval` call | `1` |
| (none) | `python3 -c "import winhost, urllib.request; c = winhost.CdpChrome(); c.__enter__(); print(urllib.request.urlopen(c.url + '/json/version').read()[:40]); c.__exit__(None, None, None)"` | a JSON prefix. **If `__enter__` raises "no CDP endpoint"** (Chrome did not outlive its task), CdpChrome has no callers in the repo, so give it a clear refusal: `__enter__` raises `RuntimeError("CdpChrome: Chrome does not outlive an interactive task; no caller needs this today")`. Add a test for that, and record the ruling. |

Restore `~/camoucrome-verify/winhost.py` and `gpu_gate.py` afterwards. Remove `gpu_gate.py` if it was not there before.

- [ ] **Step 6: GREENs in session 1 through `run-interactive.ps1`.**

For each command, run:
```
powershell -NoProfile -ExecutionPolicy Bypass -File D:\camou-win\tree\scripts\windows\run-interactive.ps1 -Name step2b-gate -Log D:\camou-win\cn\step2b\gate-<n>.log -Command '<command>'
```
Poll the log until `EXIT=`, then `-Remove`. Each `<command>` is `& D:\camou-win\client-venv\Scripts\python.exe D:\camou-win\tree\scripts\<script> <args>`, prefixed with `$env:CAMOU_FORK_EXE='<fork>'; ` where needed.

| command | expected |
|---|---|
| `windows_verify_set.py green` | `SESSION=1`; every entry `OK` except as below; `21/21 entries OK (green); 0 UNMEASURED`; `verify_host_oracle.py` OK with exactly O2 failing (known); `EXIT=0` |
| `verify_s3_host.py` | `7/7 ALL_PASS`, no UNMEASURED |
| `measure_step2.py run --only noise --modes headless,headed` | `SESSION=1`; `rows.json` `session` = 1, `desktop` recorded; no errors |

O2 must fail with the same message as on 2026-10-04 (`host-only=['bluetooth', 'canShare', 'share']` absent). That confirms O2 is not the GPU artefact. If any other entry is BAD, stop and investigate before Task 10. A set entry that flips because the session-0 artefact is gone (for example HEVC now `probably`) is a finding: record it.

- [ ] **Step 7: Release the lock and message canvas.** Expected: `released by step2b-gates`.

### Task 10: The measurement runs

**Files:**
- Modify: `scripts/step2_rows.py` (`VOLATILE`, `VOLATILE_LINES`, `EXPECTED` from calibration)
- Test: `scripts/test_step2_rows.py`
- Host: run dirs under `D:\camou-win\cn\step2b\step2\`

**Interfaces:**
- Consumes: Tasks 1–9.

**GREEN criterion for a run:** `rows.json` has empty `errors`, no detector cell is `UNMEASURED` except a page recorded as down, and `session` = 1.

- [ ] **Step 1: Prechecks.**
  - Recheck the two pending liveness items once, through a one-off session-1 run of `cap.py` (the planning-time research script in `D:\camou-win\cn\step2b`), as `areyouheadless` with its real URL.
  - Read the Turnstile token value once with `cap2.py`, changed to print the value: `XXXX.DUMMY.TOKEN.XXXX` is expected.
  - If `areyouheadless` now serves its page, add it back to `DETECTORS` (and the test's count) as a ruling. Otherwise it stays dropped.

- [ ] **Step 2: Tell the owner** in chat, before any headed run: headed windows will open on the RDP desktop for about 50 minutes per run, about 6 runs; please leave the desktop alone. Wait for the owner's go.

- [ ] **Step 3: Lock** as `step2b-measure`, and message canvas. PR #36 sequencing: if the owner merged #36 and its CI has not finished, wait for it first.

- [ ] **Step 4: Two null runs.** Through `run-interactive.ps1`, run `measure_step2.py run --null --out D:\camou-win\cn\step2b` twice, then `measure_step2.py compare <run1> <run2>`.
  - Expected: `0 rows disagree outside VOLATILE`.
  - Otherwise, for each disagreeing row or line, add an entry to `VOLATILE` or `VOLATILE_LINES` with its reason (for example Fingerprint Pro's `Your Visitor ID`, `event_id`, `linked_id`, `first_seen_at`, timestamps). For each entry, add a test to `scripts/test_step2_rows.py` in the existing style:
    ```python
    def test_<site>_volatile_<thing>():
        assert r.line_diff("<line as control>", "<line as fork>") == ([], [])
    ```
  - Re-run `measure_step2.py tables` on both runs, then `compare`, until 0.
  - No new null run is needed for a VOLATILE change: `compare` re-reads `rows.json`, and `tables` re-renders.

- [ ] **Step 5: Plant 1** (`--null --plant --disable-blink-features=WebShare --only detectors`). For every site, record whether it shows a fork-only line or row.

- [ ] **Step 6: Plant 2** (`--null --plant --disable-blink-features=AutomationControlled --only detectors`). Record, per site, whether its verdict or a line changes. A site that sees neither plant is `blind to plant`.

- [ ] **Step 7: Two fork runs** (`run`, all probes), then `compare` them.
  - Disagreements outside VOLATILE are findings. Record them; do not suppress them.
  - Label the fork-vs-control rows. An `unexpected` row becomes `EXPECTED` only when it traces to an identity key or to SP2, with the reason. Otherwise it stays a finding. Every new `EXPECTED` entry gets a test like the existing ones.

- [ ] **Step 8: Release the lock** and message canvas. Commit the calibration: `scripts/step2_rows.py scripts/test_step2_rows.py`, message `feat(step2b): VOLATILE and EXPECTED from the null and fork runs` (Co-Authored-By line).

- [ ] **Step 9: Scrub the baseline run.**

On the host, set `$env:CAMOU_SCRUB` to the host's city, region, country, ISP and ASN strings. Read them from the captures, never write them into a file. Then run:
```
measure_step2.py scrub <fork run 2> D:\camou-win\cn\step2b\step2b-main
```
Copy `rows.json` and `tables.md` to the Mac as base64 through sshgate output, into `docs/superpowers/measurements/step2b-main/`.

Then `grep -nE "([0-9]{1,3}\.){3}[0-9]{1,3}" docs/superpowers/measurements/step2b-main/*`, and read every hit. Only versions may remain. Also grep for the city name: expect no hits.

### Task 11: Docs, and the PR

**Files:**
- Create: `docs/superpowers/measurements/2026-10-12-s4-gpu-session0.md`
- Create: `docs/superpowers/measurements/2026-10-step2b-detectors.md`
- Create: `docs/superpowers/measurements/step2b-main/rows.json`, `tables.md` (from Task 10)
- Modify: `docs/superpowers/measurements/2026-10-step2-baseline.md` (§5, §6.5 note)
- Modify: `docs/superpowers/measurements/2026-10-04-windows-verify-set.md` (O2 note: confirmed not the GPU artefact)
- Modify: `docs/superpowers/plans/2026-10-02-long-term-roadmap.md` (step 2b line)
- Modify: `CLAUDE.md` (one bullet under "Build & verify": host runs go through `scripts/windows/run-interactive.ps1`, and the gate)

- [ ] **Step 1: S4 evidence doc.**
  - Copy the spike write-up: verdict, probe, rate tables, diagnosis with code citations, gaps.
  - Rename "Recommended fix" to "Fix (step2b)" and point it at `gpu_gate.py` and `run-interactive.ps1`.
  - No detector text, no IPs, no device labels.
  - Check: `grep -nE "([0-9]{1,3}\.){3}[0-9]{1,3}" docs/superpowers/measurements/2026-10-12-s4-gpu-session0.md` returns only version strings.

- [ ] **Step 2: Step 2 reclassification note.** At the top of §5 and of §6.5 of `2026-10-step2-baseline.md`, add a blockquote:
  > Session-0 artefact (S4, `2026-10-12-s4-gpu-session0.md`): this run launched in Windows session 0, where the GPU process crashes once per launch. The step2b recapture in session 1 (`2026-10-step2b-detectors.md`) confirms: <rows>; overturns: <rows>.

  Fill in the rows from Task 10's tables.

- [ ] **Step 3: Step 2b measurement doc**, in step 2's section order:
  1. what was compared: `MAIN`, the build steps and wall time, session 1, desktop size;
  2. the preconditions and gates, with Task 9's RED/GREEN tables;
  3. liveness: 20 sites, the four drops with evidence and Task 10 step 1's rechecks;
  4. each probe seen RED first, with the plants per site (sees it / blind to plant);
  5. volatile;
  6. two fork runs, `compare`;
  7. findings: verdict table highlights, unexpected rows;
  8. what step 2's §5/§6.5 rows became.

  Then list the planning rulings 1–8 and every later ruling.

- [ ] **Step 4: Roadmap and `CLAUDE.md`.**
  - Roadmap: "Step 2b (2026-10-13): 20 detectors, session-1 recapture → `2026-10-step2b-detectors.md`".
  - `CLAUDE.md` bullet: "Windows host runs launch through `scripts/windows/run-interactive.ps1` (session 1). In session 0 the GPU process crashes once per launch (S4). Every host launch path gates on `chrome://gpu`'s crash count (`scripts/gpu_gate.py`); non-zero is `UNMEASURED`."

- [ ] **Step 5: Final suite.**

Run: `python3 -m pytest -q client/python/tests scripts/ && python3 scripts/test_lib_shell_launch.py`

Expected: all pass. Record the counts.

- [ ] **Step 6: Commit** the docs (one commit), push, and open the PR against `main`.
  - **Body:** evidence (build steps, Task 9's RED/GREEN outputs, the null `compare` = 0, plant results, the set's `21/21 … 0 UNMEASURED`, suite counts); the planning rulings, including the session-check deviation from the spec text; and what is deferred.
  - The body ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
  - Do not merge.

- [ ] **Step 7: Memory.** Write `step2b-2026-10-13.md` in the memory dir: PR number, `MAIN`, host state, the lessons. Add one line to `MEMORY.md`.
