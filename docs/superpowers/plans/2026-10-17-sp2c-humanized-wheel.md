# SP2c — Humanized wheel (notches) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** With `humanize:enabled` and an effective OS of Windows, a CDP `mouseWheel` reaches the page the way stock Chrome 154 on Windows delivers the same number of physical wheel notches; everything else stays byte-identical to stock.

**Architecture:** Measure first: a host oracle records what stock Chrome 154 shows a page for real `SendInput` notches and for CDP wheels (Task 1). A pure quantizer in `components/camoucfg` turns a delta into signed notch counts (Task 2). The CDP wheel path in `input_handler.cc` splits a gated wheel into one event per notch. Notches are posted 18–60 ms apart, intermediate ones without `kFromDebugger`, and the last one goes through the stock delivery path, which owns the CDP callback (Task 3). A browser verify with RED rows (Task 4) and the ledger close it out (Task 5).

**Tech Stack:** C++20 (Chromium style), GN/Siso on the WSL box, Python 3 + Playwright over CDP, PowerShell on the Windows host through `scripts/winhost.py`, `components_unittests`.

**Spec:** `docs/superpowers/specs/2026-10-17-sp2c-humanized-wheel-design.md`

## Global Constraints

- Pin: Chrome `154.0.8037.93` (`f89f3a4363`). `scripts/apply.sh` refuses any other HEAD.
- No JavaScript injection into page-visible scopes; `Object.keys(window)` unchanged; accessors stay `[native code]`.
- No config key → today's path, byte-identical (rule 5). Gate = `humanize:enabled` true **and** effective OS Windows (`camoucfg::ClaimedOs(GlobalScope())`; `kUnknown` → `BUILDFLAG(IS_WIN)`).
- A claimed macOS/Linux keeps the CDP shape (owner scope 2026-10-17: Windows only).
- `<random>` is banned; use `base/rand_util.h`. At this pin the function is `base::RandIntInclusive(min, max)`; `base::RandInt` does not exist (memory `buildpc-client-layout`, 2026-09-12).
- Every `camoucfg::Get*` takes a scope first; key names come from `keys.h` constants, never string literals (`gen_keys.py --check` enforces it).
- No new config key. `invariants.json` unchanged unless Task 1 finds the per-notch values track DPR (then STOP, see Task 1 Step 6).
- Patches are exported, not hand-written: commit on `camoucrome/main` in `~/chromium/src` with subject `sp2c-humanized-wheel`, run `scripts/export.sh`, gate `git status --porcelain additions patches settings`.
- Every Chromium build takes `scripts/build_lock.sh acquire sp2c` and releases after. Build in the foreground.
- Host Chrome runs in session 1 (`winhost.powershell` wraps every script in a scheduled task) and pass the GPU crash gate. A nonzero count is `UNMEASURED`, never PASS or FAIL.
- Assert expected counts; RED-first: every verification is seen failing before it is trusted.
- Bad config never crashes a renderer or the browser; a widget gone mid-sequence fails the CDP callback, never dereferences.

## Review Focus

1. **Huge or non-finite delta** (`wheel(0, 1e9)`, `NaN`, `Infinity` from a buggy caller): a reasonable person expects no hang and no flood of tasks. The plan clamps each axis to `kMaxWheelNotches` = 60, and sends non-finite input down the stock path. Tests: Task 2 `QuantizeWheelClampsAndRejectsNonFinite`.
2. **Back-to-back wheels** (`wheel(0,300)` twice with no wait): the second must not interleave with the first's notches. The deferred callback serializes them, since Playwright awaits each command. Test: Task 4 row 7 (6 events, `timeStamp` monotonic).
3. **Page closed or navigated mid-sequence**: the browser must not crash, and the pending CDP command must resolve, not hang. Test: Task 4 row 8 (navigate away 10 ms after a 5-notch wheel; the command returns or errors within 10 s, and the browser still answers).
4. **Renderer coalescing**: if a notch is still unacked when the next arrives, Chromium's wheel queue merges them, and the page sees fewer, larger events. A real wheel coalesces the same way, so this is authentic. But it would make row 2's exact count flaky. Test: Task 4 row 2 runs on a page with only passive listeners and asserts the exact count. A failure there is reported, never loosened.
5. **Horizontal and diagonal wheels** (`wheel(-250, 0)`, `wheel(-300, 100)`): each axis quantizes on its own, and the longer axis sets the event count. Tests: Task 2 cases `{-300, 100}`, plus Task 4 row 3's `wheel(-250, 0)`.

## Box conventions (used by Tasks 2–5)

Every box command runs through `mcp__sshgate__exec` (`server: "buildpc"`). The shell there is Windows PowerShell 5, so:
- wrap a bash script as `wsl -d Ubuntu-24.04 -u <user> -- bash -c "echo <base64> | base64 -d | bash"`;
- a newline anywhere in `command` is refused;
- one call is capped at 600 s.

Names used below:
- `R=~/actions-runner/_work/camoucrome/camoucrome` is the runner's full clone. To get a repo file onto the box, push this branch, then `git -C $R fetch -q origin worktree-sp2c-humanized-wheel` and `git -C $R show origin/worktree-sp2c-humanized-wheel:<path> > <dest>` (memory `box-evidence-for-a-branch`). Do not run anything that writes into `$R`'s working tree.
- `LOCK="bash $R/scripts/build_lock.sh"` and `SYNC="bash $R/scripts/check_checkout_sync.sh"`. `$R`'s working tree is `main` as of the last CI run, which is right for the lock and for the pre-SP2c sync check.
- `V=~/camoucrome-verify`: verifies run from here with `$V/venv/bin/python3`. Copy `verify_sp2c.py` (and `lib_shell.py`, if it changed) in with `git show`. Back up any file you overwrite (`cp -n f ~/f.orig`), restore it at the end, and print its sha256.
- `X=~/sp2c-export`: `git -C $R archive origin/worktree-sp2c-humanized-wheel | tar -x -C $X` gives a scratch tree that `export.sh` may write into.

**Diffs into `~/chromium/src`** (Task 3) go as `stdin` to `wsl ... bash -c "cd ~/chromium/src && git apply"`. Probe this once before relying on it: command `wsl -d Ubuntu-24.04 -u <user> -- bash -c "cat > ~/sp2c-stdin-probe; sha256sum ~/sp2c-stdin-probe"` with stdin `probe` plus a newline. Compare with `printf 'probe\n' | shasum -a 256` on the Mac. If they differ, stdin does not reach WSL: use the 500-byte chunk method (memory `buildpc-sshgate-and-hardening`).

## Order and preconditions

Task 1 runs on the Windows host only and needs no build. Run it first: its output fixes constants that Tasks 2–3 use. Tasks 2–4 need the WSL box with `~/chromium/src` on `camoucrome/main` at the 154 pin, and the build lock free. On 2026-10-17 the lock was held by `repin-156-prep`. Task 3 Step 1 checks this; if it fails, stop and ask the owner. Do not build into a tree that a re-pin is moving.

---

### Task 1: Host oracle — how stock Chrome 154 delivers wheel notches

**Files:**
- Modify: `scripts/winhost.py` (`cdp_eval`, add `act_ps` and `window_style`)
- Modify: `scripts/test_winhost.py`
- Create: `scripts/capture_wheel_oracle.py`
- Create: `scripts/test_capture_wheel_oracle.py`
- Modify: `.github/workflows/build-verify.yml:86` (pytest list)
- Create (run output): `baselines/chrome-8037-wheel.json`
- Create: `docs/superpowers/measurements/2026-10-sp2c-wheel.md`

**Interfaces:**
- Produces: `winhost.cdp_eval(page_html, expression=..., args=(), headed=True, profile=None, wait_ms=1500, act_ps="", window_style="Hidden")`. `act_ps` is PowerShell run after the page websocket `$ws` connects and before the evaluate. The defaults keep every existing caller unchanged.
- Produces: `capture_wheel_oracle.summarize(log: dict) -> dict` with keys `n_wheel, dy, wdy, modes, trusted, n_scroll, scroll_ms, final_y, dpr`; `capture_wheel_oracle.red_gate(arms: dict[str, dict]) -> list[str]` (empty = measured something).
- Produces for Tasks 2–3 (written into the measurement doc's "Constants" table): `notch_css_px` (expected 100), `tracks_dpr` (expected `false`), `modes` (expected `[0]`).

- [ ] **Step 1: Write the failing winhost test.** Append to `scripts/test_winhost.py`:

```python
def test_cdp_eval_runs_act_after_connect_and_honours_window_style(monkeypatch):
    seen = {}

    class Stop(Exception):
        pass

    def fake(script, timeout=300):
        seen["ps"] = script
        raise Stop()

    monkeypatch.setattr(winhost, "powershell", fake)
    with pytest.raises(Stop):
        winhost.cdp_eval("<p>", act_ps="ACT_MARKER", window_style="Normal")
    ps = seen["ps"]
    assert ps.index("$ws = Cdp-Connect") < ps.index("ACT_MARKER") < ps.index("id = 1; method = \"Runtime.evaluate\"")
    assert "-WindowStyle Normal" in ps
    with pytest.raises(Stop):
        winhost.cdp_eval("<p>")
    assert "-WindowStyle Hidden" in seen["ps"] and "ACT_MARKER" not in seen["ps"]
```

- [ ] **Step 2: Run it, expect FAIL**

Run: `python3 -m pytest -q scripts/test_winhost.py -k act_after_connect`
Expected: FAIL, `TypeError: cdp_eval() got an unexpected keyword argument 'act_ps'`.

- [ ] **Step 3: Implement.** In `scripts/winhost.py`, change the `cdp_eval` signature and the docstring's last sentence, and make two edits in its PowerShell body.

```python
def cdp_eval(page_html, expression="document.getElementById('o').textContent", args=(), headed=True, profile=None, wait_ms=1500, act_ps="", window_style="Hidden"):
    """Runs stock Chrome on the host with --remote-debugging-port (headed by
    default: --dump-dom does not work headed), loads `page_html` from a temp
    file, evaluates `expression` through a .NET ClientWebSocket on the host
    itself (no port forward: the ssh mux master refuses forwards), returns
    the JSON-parsed value. `profile` keeps a profile dir across calls.
    `act_ps` runs after the page socket `$ws` connects and before the
    evaluate (input to measure); `window_style` "Normal" for real OS input."""
```

In the body, replace `-WindowStyle Hidden -PassThru` in the `Start-Process` line with `-WindowStyle {window_style} -PassThru`. Replace

```
$ws = Cdp-Connect $pg.webSocketDebuggerUrl
```

with

```
$ws = Cdp-Connect $pg.webSocketDebuggerUrl
{act_ps}
```

- [ ] **Step 4: Run the winhost tests, expect PASS**

Run: `python3 -m pytest -q scripts/test_winhost.py`
Expected: all pass, including the new test.

- [ ] **Step 5: Write the oracle's pure parts, test first.** Create `scripts/test_capture_wheel_oracle.py`:

```python
"""capture_wheel_oracle's pure parts: summary of a page log, and the RED gate."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import capture_wheel_oracle as c  # noqa: E402


def ev(dy, wdy, mode=0, t=0.0):
    return {"dx": 0, "dy": dy, "dz": 0, "mode": mode, "wdx": 0, "wdy": wdy, "trusted": True, "t": t}


def log(wheel, scroll, dpr=1):
    return {"wheel": wheel, "scroll": scroll, "dpr": dpr, "ua": "x"}


REAL = log([ev(100, -120, t=0), ev(100, -120, t=40), ev(100, -120, t=80)],
           [{"y": y, "t": t} for y, t in [(20, 10), (90, 60), (170, 110), (260, 160), (300, 210)]])
CDP = log([ev(300, -120)], [{"y": 300, "t": 5}])


def test_summarize():
    s = c.summarize(REAL)
    assert (s["n_wheel"], s["dy"], s["wdy"], s["modes"], s["trusted"]) == (3, [100, 100, 100], [-120, -120, -120], [0], True)
    assert (s["n_scroll"], s["scroll_ms"], s["final_y"], s["dpr"]) == (5, 200, 300, 1)
    e = c.summarize(log([], []))
    assert (e["n_wheel"], e["n_scroll"], e["scroll_ms"], e["final_y"]) == (0, 0, 0, 0)


def test_red_gate_passes_when_arms_differ():
    assert c.red_gate({"real3": c.summarize(REAL), "cdp300": c.summarize(CDP)}) == []


def test_red_gate_flags_identical_arms():
    s = c.summarize(CDP)
    problems = c.red_gate({"real3": s, "cdp300": s})
    assert len(problems) == 3


def test_red_gate_flags_a_real_arm_that_saw_nothing():
    problems = c.red_gate({"real3": c.summarize(log([], [])), "cdp300": c.summarize(CDP)})
    assert any("no wheel event" in p for p in problems)
```

Run: `python3 -m pytest -q scripts/test_capture_wheel_oracle.py`
Expected: errors with `ModuleNotFoundError: No module named 'capture_wheel_oracle'`.

- [ ] **Step 6: Write `scripts/capture_wheel_oracle.py`.**

```python
"""SP2c oracle: how stock Chrome 154 on the Windows host shows a page real
mouse-wheel notches (SendInput, the Win32 path a physical wheel takes),
against the same binary scrolled over CDP. Writes
baselines/chrome-8037-wheel.json; exits 1 if the RED gate says the arms do
not differ (the probe measured nothing). Runs where winhost.py runs (the
Mac, with the buildpc ssh master up)."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import winhost  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent.parent / "baselines" / "chrome-8037-wheel.json"

PAGE = """<!doctype html><meta charset=utf-8>
<body style="margin:0;height:20000px"><script>
window.log = {wheel: [], scroll: [], dpr: devicePixelRatio, ua: navigator.userAgent};
addEventListener('wheel', e => log.wheel.push({dx: e.deltaX, dy: e.deltaY, dz: e.deltaZ, mode: e.deltaMode,
  wdx: e.wheelDeltaX, wdy: e.wheelDeltaY, trusted: e.isTrusted, t: e.timeStamp}), {passive: true});
addEventListener('scroll', () => log.scroll.push({y: scrollY, t: performance.now()}), {passive: true});
</script>"""
EXPR = "JSON.stringify(window.log)"

# Window at a known place so a screen point is inside the page; scroll
# animation needs ~1 s to settle before the log is read.
WINDOW = ["--window-position=0,0", "--window-size=1000,800"]
SENDINPUT = r"""
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class CamouWheel {
  [StructLayout(LayoutKind.Sequential)] public struct MOUSEINPUT { public int dx, dy, mouseData; public uint dwFlags, time; public IntPtr dwExtraInfo; }
  [StructLayout(LayoutKind.Sequential)] public struct INPUT { public uint type; public MOUSEINPUT mi; }
  [DllImport("user32.dll")] public static extern uint SendInput(uint n, INPUT[] i, int size);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  public static uint Notch(int data) { var i = new INPUT[1]; i[0].mi.mouseData = data; i[0].mi.dwFlags = 0x0800; return SendInput(1, i, Marshal.SizeOf(typeof(INPUT))); }
}
"@
[CamouWheel]::SetCursorPos(500, 500) | Out-Null
Start-Sleep -Milliseconds 300
"""


def real_act(notches):
    # mouseData -120 = one notch towards the user = page scrolls down (deltaY > 0).
    sends = "\nStart-Sleep -Milliseconds 40\n".join("[CamouWheel]::Notch(-120) | Out-Null" for _ in range(notches))
    return SENDINPUT + sends + "\nStart-Sleep -Milliseconds 1500\n"


def cdp_act(delta_y):
    return ("Cdp-Send $ws @{ id = 7; method = \"Input.dispatchMouseEvent\"; params = @{ type = \"mouseWheel\"; "
            f"x = 300; y = 300; deltaX = 0; deltaY = {delta_y} }} }}\n"
            "for ($i = 0; $i -lt 10; $i++) { $m = Cdp-Recv $ws 5000; if ($m -and $m.StartsWith('{\"id\":7,')) { break } }\n"
            "Start-Sleep -Milliseconds 1500\n")


ARMS = {
    "real1": dict(act_ps=real_act(1), window_style="Normal", args=WINDOW),
    "real3": dict(act_ps=real_act(3), window_style="Normal", args=WINDOW),
    "real3_dsf1": dict(act_ps=real_act(3), window_style="Normal", args=WINDOW + ["--force-device-scale-factor=1"]),
    "cdp100": dict(act_ps=cdp_act(100), args=WINDOW),
    "cdp300": dict(act_ps=cdp_act(300), args=WINDOW),
}

HOST_FACTS = r"""
"WHEELLINES=" + (Get-ItemProperty 'HKCU:\Control Panel\Desktop').WheelScrollLines
"APPLIEDDPI=" + (Get-ItemProperty 'HKCU:\Control Panel\Desktop\WindowMetrics' -ErrorAction SilentlyContinue).AppliedDPI
"CHROMEVER=" + (Get-Item 'C:\Program Files\Google\Chrome\Application\chrome.exe').VersionInfo.ProductVersion
"""


def summarize(log):
    w, s = log["wheel"], log["scroll"]
    return {
        "n_wheel": len(w),
        "dy": [e["dy"] for e in w],
        "wdy": [e["wdy"] for e in w],
        "modes": sorted({e["mode"] for e in w}),
        "trusted": all(e["trusted"] for e in w),
        "n_scroll": len(s),
        "scroll_ms": round(s[-1]["t"] - s[0]["t"]) if len(s) > 1 else 0,
        "final_y": s[-1]["y"] if s else 0,
        "dpr": log["dpr"],
    }


def _ratios(s):
    return [round(w / d, 3) for w, d in zip(s["wdy"], s["dy"]) if d]


def red_gate(arms):
    real, cdp = arms["real3"], arms["cdp300"]
    if real["n_wheel"] == 0:
        return ["real3: no wheel event reached the page (window not under the cursor, or SendInput failed)"]
    problems = []
    if real["n_wheel"] == cdp["n_wheel"]:
        problems.append(f"event count equal ({real['n_wheel']}): count does not separate the arms")
    if _ratios(real) == _ratios(cdp):
        problems.append(f"wheelDeltaY/deltaY ratios equal ({_ratios(real)})")
    if real["n_scroll"] == cdp["n_scroll"]:
        problems.append(f"scroll event counts equal ({real['n_scroll']}): no animation difference seen")
    return problems


def main():
    facts = dict(line.split("=", 1) for line in winhost.powershell(HOST_FACTS).splitlines() if "=" in line)
    arms = {}
    for name, kw in ARMS.items():
        raw = winhost.cdp_eval(PAGE, expression=EXPR, wait_ms=2500, **kw)
        arms[name] = {"log": raw, "summary": summarize(raw)}
        print(name, json.dumps(arms[name]["summary"]), flush=True)
    problems = red_gate({k: v["summary"] for k, v in arms.items()})
    for p in problems:
        print("RED-GATE", p)
    if problems:
        return 1
    OUT.write_text(json.dumps({"host": facts, "arms": arms}, indent=1, sort_keys=True) + "\n")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Run: `python3 -m pytest -q scripts/test_capture_wheel_oracle.py`
Expected: 4 passed.

Add `scripts/test_capture_wheel_oracle.py` to the pytest list at `.github/workflows/build-verify.yml:86`, right after `scripts/test_winhost.py`.

- [ ] **Step 7: Commit the harness**

```bash
git add scripts/winhost.py scripts/test_winhost.py scripts/capture_wheel_oracle.py scripts/test_capture_wheel_oracle.py .github/workflows/build-verify.yml
git commit -m "feat(sp2c): host wheel oracle (SendInput vs CDP) with RED gate"
```

- [ ] **Step 8: Run the oracle on the host.** Preconditions:
- the owner's RDP session is connected and Active (a disconnected session stalls input);
- the buildpc ssh master is up on the Mac (`ssh -O check buildpc`). If it is not, ask the owner to open it with `! ssh -fNM -o ServerAliveInterval=30 buildpc`. Never retry a password yourself: three failures trigger a fail2ban lockout. Fallback, as step2b (PR #38) did: replace `winhost.powershell` with a stub that records each script. Send each recorded script through `mcp__sshgate__exec` (gzip+base64, one line), then feed the output back to the stub.

Run: `python3 scripts/capture_wheel_oracle.py`

Expected:
- 5 summary lines;
- no `RED-GATE` line, and `wrote …/baselines/chrome-8037-wheel.json`;
- `real3` with `n_wheel` 3, all `trusted`;
- `cdp300` with `n_wheel` 1.

Branches:
- `UNMEASURED` (session or GPU gate): report it, fix the session, rerun.
- `RED-GATE real3: no wheel event…`: first rule out SendInput itself. Run `winhost.powershell(capture_wheel_oracle.SENDINPUT + '"SENT=" + [CamouWheel]::Notch(-120)')`; `SENT=0` means a struct-size mismatch in the `INPUT` declaration, and that is what to fix. If it prints `SENT=1`, the Chrome window was not under (500,500): have the owner check that nothing covers the top-left of the screen, then rerun.
- Any other `RED-GATE`: STOP and report the five summaries to the owner. The spec's premise is then wrong, and SP2c needs re-design.

- [ ] **Step 9: Read the constants and decide DPR.** From `baselines/chrome-8037-wheel.json`:
- `notch_css_px` = `real1.summary.dy[0]`;
- `modes` = `real3.summary.modes`;
- `tracks_dpr` = `false` if `real3.dy[0] == real3_dsf1.dy[0]`, else `true`.

Also note `host.APPLIEDDPI` (96 = 100 %). Then decide:
- **DPR = 100 % and `tracks_dpr` cannot be told apart** (both arms run at DPR 1): record `tracks_dpr: unmeasured at 100 %` and proceed with the `false` formula. Add the limit to the doc's "Open" list.
- **`tracks_dpr == true`**: STOP. Notch values then depend on DPR, which is the cross-surface tie the spec says adds an invariant. Report to the owner and amend this plan before Task 3.
- **`modes != [0]`, or `notch_css_px` is not a positive number**: STOP and report, because Task 3's event shape assumes pixel mode.

- [ ] **Step 10: Write the measurement doc** `docs/superpowers/measurements/2026-10-sp2c-wheel.md`. It records:
- date and time in UTC, and the Chrome version (`host.CHROMEVER`);
- `WHEELLINES` and `APPLIEDDPI`;
- the five summaries as a table (columns: arm, n_wheel, dy, wdy, modes, n_scroll, scroll_ms, final_y, dpr);
- the RED-gate verdict;
- a **Constants** table: `notch_css_px`, `tracks_dpr`, `modes`, each with the arm it came from;
- an **Open** list: cadence 18–60 ms is Camoufox's, not measured, because SendInput sets the cadence; DPR at other scales, if unmeasured.

- [ ] **Step 11: Commit**

```bash
git add baselines/chrome-8037-wheel.json docs/superpowers/measurements/2026-10-sp2c-wheel.md
git commit -m "measure(sp2c): stock Chrome 154 wheel notches on the Windows host"
```

---

### Task 2: `QuantizeWheel` in `components/camoucfg`

Edit the files in this worktree's `additions/camoucfg/`, commit, and push. On the box, copy each one into `~/chromium/src/components/camoucfg/` with `git -C $R show origin/worktree-sp2c-humanized-wheel:additions/camoucfg/<file> > ~/chromium/src/components/camoucfg/<file>` (see Box conventions). Then compare `sha256sum` on the box with `shasum -a 256` on the Mac. Task 3's `export.sh` must reproduce these files byte for byte.

**Files:**
- Modify: `additions/camoucfg/mouse_trajectories.h`
- Modify: `additions/camoucfg/mouse_trajectories.cc`
- Test: `additions/camoucfg/mouse_trajectories_unittest.cc`

**Interfaces:**
- Consumes: Task 1's `notch_css_px` (expected 100).
- Produces:
  - `struct camoucfg::WheelNotches { int x; int y; };`
  - `camoucfg::WheelNotches camoucfg::QuantizeWheel(double delta_x, double delta_y);`
  - `inline constexpr int camoucfg::kMaxWheelNotches = 60;`
  - `inline constexpr float camoucfg::kWindowsNotchCssPx = <notch_css_px>;`

- [ ] **Step 1: Write the failing tests.** Append to `mouse_trajectories_unittest.cc`, inside the existing anonymous namespace, after the last `TEST`:

```cpp
TEST(MouseTrajectoriesTest, QuantizeWheelRoundsToWholeNotches) {
  struct Case {
    double dx, dy;
    int x, y;
  } cases[] = {
      {0, 0, 0, 0},       {0, 40, 0, 1},      {0, 50, 0, 1},
      {0, 100, 0, 1},     {0, 149, 0, 1},     {0, 150, 0, 2},
      {0, 250, 0, 3},     {0, -250, 0, -3},   {-300, 100, -3, 1},
      {-250, 0, -3, 0},
  };
  for (const Case& c : cases) {
    WheelNotches n = QuantizeWheel(c.dx, c.dy);
    EXPECT_EQ(n.x, c.x) << c.dx << "," << c.dy;
    EXPECT_EQ(n.y, c.y) << c.dx << "," << c.dy;
  }
}

TEST(MouseTrajectoriesTest, QuantizeWheelClampsAndRejectsNonFinite) {
  EXPECT_EQ(QuantizeWheel(0, 1e9).y, kMaxWheelNotches);
  EXPECT_EQ(QuantizeWheel(-1e9, 0).x, -kMaxWheelNotches);
  for (double bad : {std::nan(""), INFINITY, -INFINITY}) {
    WheelNotches n = QuantizeWheel(bad, 100);
    EXPECT_EQ(n.x, 0);
    EXPECT_EQ(n.y, 0) << "non-finite input must take the stock path";
  }
}
```

If the file's existing tests are not in `namespace camoucfg`, prefix the names with `camoucfg::`. Check its first 20 lines.

- [ ] **Step 2: Build and run, expect a compile FAIL**

Commit the test (`git commit -m "test(sp2c): QuantizeWheel cases (red)"`) and push. Copy `mouse_trajectories_unittest.cc` to the box tree as described above. Then, on the box:

```bash
cd ~/chromium/src && $LOCK acquire sp2c && autoninja -C out/Default components_unittests
```

Expected: FAIL, `use of undeclared identifier 'QuantizeWheel'`. Keep the lock held.

- [ ] **Step 3: Implement.** In `mouse_trajectories.h`, before `}  // namespace camoucfg`:

```cpp
// A wheel turns in whole notches. Signed notch counts per axis for a CDP
// wheel delta: |d| / 100 rounded half away from zero, at least 1 for a
// non-zero delta (Camoufox's rule), clamped to kMaxWheelNotches. A zero or
// non-finite delta on both axes gives {0, 0}: the caller then takes stock's
// path. The event count a caller sends is max(|x|, |y|).
struct WheelNotches {
  int x;
  int y;
};
inline constexpr int kMaxWheelNotches = 60;
WheelNotches QuantizeWheel(double delta_x, double delta_y);

// The page-visible deltaY of one notch on Windows at DPR 1, measured on stock
// Chrome 154 (docs/superpowers/measurements/2026-10-sp2c-wheel.md).
inline constexpr float kWindowsNotchCssPx = 100.0f;
```

Use Task 1's measured `notch_css_px` in place of `100.0f` if it differs.

In `mouse_trajectories.cc`, before `}  // namespace camoucfg`:

```cpp
WheelNotches QuantizeWheel(double delta_x, double delta_y) {
  if (!std::isfinite(delta_x) || !std::isfinite(delta_y)) {
    return {0, 0};
  }
  auto axis = [](double d) {
    if (d == 0) {
      return 0;
    }
    long n = std::max(1L, std::lround(std::min(std::abs(d) / 100.0,
                                               double{kMaxWheelNotches})));
    return static_cast<int>(d > 0 ? n : -n);
  };
  return {axis(delta_x), axis(delta_y)};
}
```

`<algorithm>` and `<cmath>` are already included there.

- [ ] **Step 4: Build and run, expect PASS**

Commit (`git commit -m "feat(sp2c): QuantizeWheel"`), push, and copy `mouse_trajectories.h` and `.cc` to the box tree. Then:

```bash
cd ~/chromium/src && autoninja -C out/Default components_unittests && out/Default/components_unittests --gtest_filter='MouseTrajectoriesTest.*'
```

Expected:
- the build reports a non-zero step count;
- `[  PASSED  ] 10 tests.` (8 existing + 2 new).

- [ ] **Step 5: RED check of the clamp.** In the box tree only, change the `.cc`'s `double{kMaxWheelNotches}` to `double{kMaxWheelNotches + 1}`, then rebuild and rerun. Expected: `QuantizeWheelClampsAndRejectsNonFinite` FAILS. Restore the file from the branch (`git -C $R show …`), rebuild, and rerun: 10 pass, and the box file's sha256 equals the worktree's. The box tree is committed in Task 3 Step 7.

---

### Task 3: Notch split in the CDP wheel path

**Files (box tree; exported to `patches/sp2c-humanized-wheel.patch`):**
- Modify: `content/browser/devtools/protocol/input_handler.cc` (`InjectWheelEvent`, `:709-740` on the 154 pin; new statics next to SP2b's `ForwardHumanizedMouseEventCompletion`)
- Modify: `content/browser/devtools/protocol/input_handler.h` (two static declarations next to SP2b's)

**Interfaces:**
- Consumes: `camoucfg::QuantizeWheel`, `kWindowsNotchCssPx` (Task 2); `camoucfg::ClaimedOs`, `camoucfg::OsFamily` (`components/camoucfg/derive.h`); `camoucfg::keys::kHumanizeEnabled`.
- Produces:
  - `InputHandler::InputInjector::ForwardWheelEventNow(blink::WebMouseWheelEvent*, std::unique_ptr<DispatchMouseEventCallback>)`, the stock body;
  - static `InputHandler::ForwardSyntheticWheelNotch(base::WeakPtr<InputHandler>, base::WeakPtr<RenderWidgetHostImpl>, blink::WebMouseWheelEvent)`;
  - static `InputHandler::ForwardWheelNotchCompletion(base::WeakPtr<InputHandler>, base::WeakPtr<RenderWidgetHostImpl>, std::unique_ptr<blink::WebMouseWheelEvent>, std::unique_ptr<DispatchMouseEventCallback>)`.

Why the ack path differs from SP2b, read before coding:
- `OnInputEventAck` pops `pending_mouse_callbacks_` for any mouse or wheel event carrying `kFromDebugger`. So intermediate notches must drop that bit, exactly as SP2b's synthetic moves do (`input_handler.cc`, SP2b's `SchedulePath` comment).
- Only the last notch keeps the bit and goes through `ForwardWheelEventNow`. That is the stock body: it queues the callback, forwards, and on `input_queued_` sends stock's zero-delta `kPhaseEnded` follow-up, which ends the latched sequence the notches began.
- Phases follow `MouseWheelPhaseHandler` for a real wheel: the first notch is `kPhaseBegan`, later ones `kPhaseChanged`, and the stock follow-up is `kPhaseEnded`.

- [ ] **Step 1: Preconditions on the box** (read-only):

```bash
cd ~/chromium/src && git rev-parse --abbrev-ref HEAD && git merge-base --is-ancestor f89f3a4363 HEAD && echo PIN_OK && git status --porcelain | head -5; $SYNC; echo sync_rc=$?; $LOCK status
```

The porcelain output must show only Task 2's three `components/camoucfg/mouse_trajectories*` files. Task 2 left them uncommitted on purpose, so `$SYNC` reports exactly those three.

Expected:
- `camoucrome/main` and `PIN_OK`;
- the lock held by `sp2c` (from Task 2) or free.

Anything else (a re-pin moving the tree, another owner holding the lock): STOP and ask the owner.

- [ ] **Step 2: Write the RED verify row first.** Task 4 Steps 1–2 create `verify_sp2c.py` and run it against the current build. Do that now: rows 2 and 3's non-zero cases must FAIL before any C++ changes. Record the output.

- [ ] **Step 3: Implement in `input_handler.cc`.** Transport: there is no Chromium source on the Mac, and the file is larger than one sshgate output (64 KiB). So write `sp2c_edit.py` in the session scratchpad. It holds each edit below as an exact `(old, new)` string pair, asserts `text.count(old) == 1` for each before replacing, and writes the files back. Send it as `stdin` to `wsl -d Ubuntu-24.04 -u <user> -- bash -c "cd ~/chromium/src && python3 -"`. Then confirm with `git diff --stat` (two files) and `git diff | head -400`, read back in pieces.

The `old` text of the `InjectWheelEvent` edit is the stock function exactly as on the pin (`input_handler.cc:709-740`). It runs from `  void InjectWheelEvent(blink::WebMouseWheelEvent* wheel_event,` through the second `    widget_host_->ForwardWheelEvent(*wheel_event);` and its closing `  }`. Print it with `sed -n 709,741p` first and copy it from that output, not from memory.

Add includes next to SP2b's camoucfg includes:

```cpp
#include "build/build_config.h"
#include "components/camoucfg/derive.h"
```

(`build/build_config.h` only if it is not already included.)

In the file's top-level anonymous namespace (the one holding `GetEventTimeTicks`, `input_handler.cc:130`), add a free function. It uses no members:

```cpp
// SP2c: the OS whose wheel encoding to reproduce. Nothing claimed means the
// real OS, as ClaimedOs's own comment directs.
bool EffectiveOsIsWindows() {
  camoucfg::OsFamily os = camoucfg::ClaimedOs(camoucfg::GlobalScope());
  if (os == camoucfg::OsFamily::kUnknown) {
    return BUILDFLAG(IS_WIN);
  }
  return os == camoucfg::OsFamily::kWindows;
}
```

Replace the body of `InjectWheelEvent` with the gate plus a call to the factored-out stock body. Add `ForwardWheelEventNow` and `ScheduleNotches` directly after it, in the same access section and with no new `public:`/`private:` labels. This is the layout SP2b used, with `ForwardMouseEventNow` and `SchedulePath` directly after `InjectMouseEvent` (`grep -n "void ForwardMouseEventNow\|void SchedulePath" input_handler.cc`). The stock code from `input_queued_ = false;` through the trailing `ForwardWheelEvent(*wheel_event);` moves unchanged into `ForwardWheelEventNow`.

```cpp
  void InjectWheelEvent(blink::WebMouseWheelEvent* wheel_event,
                        std::unique_ptr<DispatchMouseEventCallback> callback) {
    if (!widget_host_) {
      callback->sendFailure(Response::InternalError());
      return;
    }

    widget_host_->Focus();

    // SP2c: with humanize:enabled and an effective OS of Windows, deliver the
    // wheel as the whole notches a physical wheel turns. Absent either, this
    // is skipped and the stock body below runs exactly as before.
    if (camoucfg::GetBool(camoucfg::GlobalScope(),
                          camoucfg::keys::kHumanizeEnabled)
            .value_or(false) &&
        EffectiveOsIsWindows()) {
      camoucfg::WheelNotches notches =
          camoucfg::QuantizeWheel(wheel_event->delta_x, wheel_event->delta_y);
      if (notches.x != 0 || notches.y != 0) {
        ScheduleNotches(*wheel_event, notches, std::move(callback));
        // No callback queued on this injector; the completion task owns it.
        MaybeSelfDestruct();
        return;
      }
    }
    ForwardWheelEventNow(wheel_event, std::move(callback));
  }

  // InjectWheelEvent's stock body, factored out so the last notch of a
  // humanized wheel (ForwardWheelNotchCompletion) is delivered and acked
  // exactly as an unhumanized wheel is, phaseEnded follow-up included.
  void ForwardWheelEventNow(
      blink::WebMouseWheelEvent* wheel_event,
      std::unique_ptr<DispatchMouseEventCallback> callback) {
    input_queued_ = false;
    pending_mouse_callbacks_.push_back(std::move(callback));
    // This may destroy the injector if the events get discarded.
    base::WeakPtr<InputHandler::InputInjector> weak_this =
        weak_ptr_factory_.GetWeakPtr();
    widget_host_->ForwardWheelEvent(*wheel_event);
    if (!weak_this) {
      return;
    }
    if (!input_queued_) {
      pending_mouse_callbacks_.back()->sendSuccess();
      pending_mouse_callbacks_.pop_back();
      MaybeSelfDestruct();
      return;
    }

    // Send a synthetic wheel event with phaseEnded to finish scrolling.
    wheel_event->delta_x = 0;
    wheel_event->delta_y = 0;
    wheel_event->wheel_ticks_x = 0;
    wheel_event->wheel_ticks_y = 0;
    wheel_event->phase = blink::WebMouseWheelEvent::kPhaseEnded;
    wheel_event->dispatch_type =
        blink::WebInputEvent::DispatchType::kEventNonBlocking;
    widget_host_->ForwardWheelEvent(*wheel_event);
  }

  // One event per notch, 18-60 ms apart, each shaped like a Windows notch
  // through Aura (MakeWebMouseWheelEventFromUiEvent: pixel units, one tick)
  // with MouseWheelPhaseHandler's phases. Posted in real time, like SP2b's
  // path, so the renderer consumes each notch before the next arrives. The
  // last notch carries the CDP callback and goes through ForwardWheelEventNow.
  void ScheduleNotches(const blink::WebMouseWheelEvent& wheel_event,
                       camoucfg::WheelNotches notches,
                       std::unique_ptr<DispatchMouseEventCallback> callback) {
    const int count = std::max(std::abs(notches.x), std::abs(notches.y));
    // Blink divides a wheel's delta by the page's scale (wheel_event.cc), so
    // scale up to keep kWindowsNotchCssPx page-visible at any DPR or zoom.
    const float notch_px =
        camoucfg::kWindowsNotchCssPx * owner_->ScaleFactor();
    base::WeakPtr<InputHandler> handler = owner_->weak_factory_.GetWeakPtr();
    scoped_refptr<base::SingleThreadTaskRunner> task_runner =
        base::SingleThreadTaskRunner::GetCurrentDefault();
    base::TimeDelta at;
    for (int i = 0; i < count; ++i) {
      if (i > 0) {
        at += base::Milliseconds(base::RandIntInclusive(18, 60));
      }
      const float tx = i < std::abs(notches.x) ? (notches.x > 0 ? 1 : -1) : 0;
      const float ty = i < std::abs(notches.y) ? (notches.y > 0 ? 1 : -1) : 0;
      auto notch = std::make_unique<blink::WebMouseWheelEvent>(wheel_event);
      notch->delta_x = tx * notch_px;
      notch->delta_y = ty * notch_px;
      notch->wheel_ticks_x = tx;
      notch->wheel_ticks_y = ty;
      notch->delta_units = ui::ScrollGranularity::kScrollByPixel;
      notch->phase = i == 0 ? blink::WebMouseWheelEvent::kPhaseBegan
                            : blink::WebMouseWheelEvent::kPhaseChanged;
      if (i + 1 < count) {
        // Without kFromDebugger: OnInputEventAck pops the one queued
        // callback for any debugger-marked wheel ack, and that callback
        // belongs to the last notch.
        notch->SetModifiers(notch->GetModifiers() &
                            ~blink::WebInputEvent::kFromDebugger);
        task_runner->PostDelayedTask(
            FROM_HERE,
            base::BindOnce(&InputHandler::ForwardSyntheticWheelNotch, handler,
                           widget_host_, *notch),
            at);
      } else {
        task_runner->PostDelayedTask(
            FROM_HERE,
            base::BindOnce(&InputHandler::ForwardWheelNotchCompletion, handler,
                           widget_host_, std::move(notch),
                           std::move(callback)),
            at);
      }
    }
  }
```

`std::abs` on `int` needs `<cstdlib>`; add it if the file does not include it.

Next to SP2b's static definitions (after `ForwardHumanizedMouseEventCompletion`):

```cpp
// static
void InputHandler::ForwardSyntheticWheelNotch(
    base::WeakPtr<InputHandler> handler,
    base::WeakPtr<RenderWidgetHostImpl> widget,
    blink::WebMouseWheelEvent notch) {
  if (!handler || !widget) {
    return;
  }
  // Stamped when it fires: the real posted delay is the cadence.
  notch.SetTimeStamp(base::TimeTicks::Now());
  widget->ForwardWheelEvent(notch);
}

// static
void InputHandler::ForwardWheelNotchCompletion(
    base::WeakPtr<InputHandler> handler,
    base::WeakPtr<RenderWidgetHostImpl> widget,
    std::unique_ptr<blink::WebMouseWheelEvent> notch,
    std::unique_ptr<DispatchMouseEventCallback> callback) {
  if (!handler || !widget) {
    callback->sendFailure(Response::InternalError());
    return;
  }
  notch->SetTimeStamp(base::TimeTicks::Now());
  handler->EnsureInjector(widget.get())
      ->ForwardWheelEventNow(notch.get(), std::move(callback));
}
```

- [ ] **Step 4: Declare the statics in `input_handler.h`.** Next to SP2b's two declarations, add the following, plus `#include "third_party/blink/public/common/input/web_mouse_wheel_event.h"` beside the existing `web_mouse_event.h` include:

```cpp
  // Delayed-task callbacks for InputInjector::ScheduleNotches (SP2c). Static
  // for the same reason as SP2b's: the scheduling injector self-destructs.
  static void ForwardSyntheticWheelNotch(
      base::WeakPtr<InputHandler> handler,
      base::WeakPtr<RenderWidgetHostImpl> widget,
      blink::WebMouseWheelEvent notch);
  static void ForwardWheelNotchCompletion(
      base::WeakPtr<InputHandler> handler,
      base::WeakPtr<RenderWidgetHostImpl> widget,
      std::unique_ptr<blink::WebMouseWheelEvent> notch,
      std::unique_ptr<DispatchMouseEventCallback> callback);
```

- [ ] **Step 5: Dependency checks and build.** A `.cc`-only build runs neither check:

```bash
cd ~/chromium/src && gn check out/Default //content/browser:browser && python3 buildtools/checkdeps/checkdeps.py content/browser/devtools/protocol && autoninja -C out/Default chrome content_shell components_unittests
```

Expected:
- `Header dependency check OK`;
- checkdeps prints no violation;
- the build reports NON-ZERO steps and ends without error.

- [ ] **Step 6: Run Task 4's verify, expect GREEN, then the mutant RED.** Run `verify_sp2c.py` (Task 4 Step 3): all rows PASS. Then make the mutant: in `EffectiveOsIsWindows` replace the body with `return true;`, rebuild `chrome`, rerun. Expected: rows 4 and 5 FAIL. Revert, rebuild (non-zero steps), rerun: all PASS.

- [ ] **Step 7: Commit on the box and export.**

Run `git commit` in the foreground of the call (memory: a detached ref-moving git op died mid-run):

```bash
cd ~/chromium/src && git add components/camoucfg/mouse_trajectories.h components/camoucfg/mouse_trajectories.cc components/camoucfg/mouse_trajectories_unittest.cc content/browser/devtools/protocol/input_handler.cc content/browser/devtools/protocol/input_handler.h && git commit -q -m sp2c-humanized-wheel && git log --oneline -1
```

Then export into the scratch tree and bring the result back:

```bash
rm -rf $X && mkdir -p $X && git -C $R archive origin/worktree-sp2c-humanized-wheel | tar -x -C $X && bash $X/scripts/export.sh ~/chromium/src && cd $X && tar czf - additions patches settings/invariants.json | base64 -w0
```

On the Mac, in the worktree: `base64 -d > /private/tmp/claude-501/-Users-<user>-GolandProjects-github-com-lang315-camoucrome/f58518de-b499-4f19-8019-5aabd1640ad4/scratchpad/export.tgz` (paste the output), then `tar xzf` it into the worktree root. If the base64 is longer than one call's 64 KiB stdout, split it with `split -b 60000` on the box and print the pieces one call at a time.

Expected in the worktree:
- `git status --porcelain additions patches settings` lists exactly `?? patches/sp2c-humanized-wheel.patch` and ` M patches/series`;
- no `additions/` line, which proves the box tree's camoucfg files equal Task 2's commits byte for byte;
- `patches/series` has `sp2c-humanized-wheel.patch` as the last line.

Also on the box: `bash $X/scripts/check_checkout_sync.sh ~/chromium/src; echo rc=$?` must give rc 0. Use `$X`'s copy, not `$SYNC`: `$R` is at `main` and lacks the sp2c patch. Check that script's usage line for its argument form first. Release the lock: `$LOCK release sp2c`.

- [ ] **Step 8: Round-trip the patch** (CLAUDE.md: a single extraction can drop a cross-file dep). On the box:

```bash
cd ~/chromium/src && git status --porcelain | wc -l && git checkout HEAD~1 -- content/browser/devtools/protocol/ && git apply --3way $X/patches/sp2c-humanized-wheel.patch && echo "vs HEAD~1:" && git diff --cached --stat HEAD~1 -- content/browser/devtools/protocol/ && echo "vs HEAD:" && git diff --cached HEAD -- content/browser/devtools/protocol/ | wc -l && gn check out/Default //content/browser:browser; git checkout HEAD -- content/browser/devtools/protocol/ && git status --porcelain | wc -l
```

Both porcelain counts must be `0`. The tree is clean after Step 7's commit, so no stash is needed. If the first count is not 0, STOP.

Expected:
- `vs HEAD~1` lists exactly `input_handler.cc` and `input_handler.h` (sanity);
- `vs HEAD` prints `0`: the re-applied patch reproduces the commit exactly, which is the actual round-trip test;
- `Header dependency check OK`.

Finish with `check_checkout_sync.sh` rc 0. Drop the guard stash only if one was created: find it by its tag in `git stash list` and drop it by that index.

- [ ] **Step 9: Pre-flight and commit in the worktree**

```bash
python3 scripts/check_additions_build.py && python3 scripts/gen_keys.py --check
git add patches/sp2c-humanized-wheel.patch patches/series
git commit -m "feat(sp2c): humanized wheel notches in the CDP wheel path"
```

Expected: both checks PASS before the commit.

---

### Task 4: `scripts/verify_sp2c.py` and CI

**Files:**
- Create: `scripts/verify_sp2c.py`
- Modify: `.github/workflows/build-verify.yml` (run list, after `run verify_sp1a_chrome.py`)

**Interfaces:**
- Consumes: `lib_shell.launch(config, shell=lib_shell.CHROME, extra_flags=lib_shell.CHROME_FLAGS)`, `lib_shell.shutdown(proc)`, `proc.cdp_port`; Task 1's constants (`notch_css_px`, `modes`).

- [ ] **Step 1: Write `scripts/verify_sp2c.py`.**

```python
"""Verifies SP2c: with humanize:enabled and a claimed Windows, a CDP mouseWheel
reaches the page as whole notches (one event per notch, Task 1's per-notch
shape, 18-60 ms apart); without either it is stock's single event.

Driven with page.mouse.wheel, one Input.dispatchMouseEvent per call, like
verify_sp2b. Every row states its count. Animation is not asserted here:
whether content_shell/chrome on Linux animates pixel-unit wheels says nothing
about Windows (spec section 4); the host-native arm owns that.
"""

import json
import signal
import sys

from playwright.sync_api import sync_playwright

import lib_shell

NOTCH_PX = 100  # baselines/chrome-8037-wheel.json real1 dy[0]; update if Task 1 measured otherwise
WIN = {"ua:osInfo": "Windows NT 10.0; Win64; x64", "ua:platform": "Windows"}
MAC = {"ua:osInfo": "Macintosh; Intel Mac OS X 10_15_7", "ua:platform": "macOS"}
HUMANIZE = {"humanize:enabled": True}

PAGE = """<!doctype html><body style="margin:0;height:40000px;width:40000px"><script>
window.__w = [];
addEventListener('wheel', e => __w.push({dx: e.deltaX, dy: e.deltaY, mode: e.deltaMode,
  wdx: e.wheelDeltaX, wdy: e.wheelDeltaY, t: e.timeStamp}), {passive: true});
</script>"""


def session(config, actions):
    """actions(page) -> value; returns (value, err)."""
    proc = None
    try:
        proc = lib_shell.launch(json.dumps(config) if config else None, shell=lib_shell.CHROME,
                                extra_flags=lib_shell.CHROME_FLAGS)
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{proc.cdp_port}")
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.set_content(PAGE)
            page.mouse.move(300, 300)
            return actions(page), None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)


def wheel_then_read(*deltas):
    def act(page):
        out = []
        for dx, dy in deltas:
            page.evaluate("window.__w = []")
            page.mouse.wheel(dx, dy)
            page.wait_for_timeout(300)
            out.append(page.evaluate("window.__w"))
        return out
    return act


def notch_ok(e, sx, sy):
    return (e["mode"] == 0 and e["dx"] == sx * NOTCH_PX and e["dy"] == sy * NOTCH_PX
            and e["wdx"] == -120 * sx and e["wdy"] == -120 * sy)


def gaps(events):
    return [b["t"] - a["t"] for a, b in zip(events, events[1:])]


results, notes = {}, []


def row(name, ok, note=None):
    results[name] = bool(ok)
    if note and not ok:
        notes.append(f"{name}: {note}")


R1 = "1 no config: wheel(0,300) is one event of deltaY 300"
R2 = "2 humanize+Windows: wheel(0,300) is 3 notch events, 18-60 ms apart"
R3 = "3 humanize+Windows: wheel(0,0)=stock count, (0,40)=1 notch, (-250,0)=3 notches on X"
R4 = "4 humanize+macOS: wheel(0,300) is stock's single event"
R5 = "5 humanize, nothing claimed (Linux build): wheel(0,300) is stock's single event"
R6 = "6 no new window keys and WheelEvent accessors native under humanize+Windows"
R7 = "7 humanize+Windows: two back-to-back wheel(0,300) give 6 events, timeStamps increasing"
R8 = "8 humanize+Windows: navigating away mid-sequence neither hangs nor kills the browser"

stock, err = session(None, wheel_then_read((0, 300), (0, 0)))
if err:
    row(R1, False, repr(err))
    stock_zero = None
else:
    w300, stock_zero = stock
    row(R1, len(w300) == 1 and w300[0]["dy"] == 300, json.dumps(w300))

got, err = session({**HUMANIZE, **WIN}, wheel_then_read((0, 300), (0, 0), (0, 40), (-250, 0)))
if err:
    row(R2, False, repr(err))
    row(R3, False, repr(err))
else:
    w300, w0, w40, wx = got
    g = gaps(w300)
    row(R2, len(w300) == 3 and all(notch_ok(e, 0, 1) for e in w300) and all(15 <= x <= 75 for x in g),
        f"n={len(w300)} gaps={g} ev={json.dumps(w300)}")
    row(R3, stock_zero is not None and len(w0) == len(stock_zero)
        and len(w40) == 1 and notch_ok(w40[0], 0, 1)
        and len(wx) == 3 and all(notch_ok(e, -1, 0) for e in wx),
        f"w0={w0} stock0={stock_zero} w40={w40} wx={wx}")

for name, cfg in ((R4, {**HUMANIZE, **MAC}), (R5, HUMANIZE)):
    got, err = session(cfg, wheel_then_read((0, 300)))
    row(name, not err and len(got[0]) == 1 and got[0][0]["dy"] == 300, repr(err) if err else json.dumps(got))

KEYS = "JSON.stringify([Object.keys(window).length, ['deltaX','deltaY','deltaMode','wheelDeltaY'].map(k => Object.getOwnPropertyDescriptor(WheelEvent.prototype, k) ? Function.prototype.toString.call(Object.getOwnPropertyDescriptor(WheelEvent.prototype, k).get || (() => {})) : 'own:' + k)])"
base, err1 = session(None, lambda page: page.evaluate(KEYS))
hum, err2 = session({**HUMANIZE, **WIN}, lambda page: page.evaluate(KEYS))
row(R6, not err1 and not err2 and base == hum and "[native code]" in hum, f"{base} vs {hum}")


def back_to_back(page):
    page.evaluate("window.__w = []")
    page.mouse.wheel(0, 300)
    page.mouse.wheel(0, 300)
    page.wait_for_timeout(300)
    return page.evaluate("window.__w")


got, err = session({**HUMANIZE, **WIN}, back_to_back)
row(R7, not err and len(got) == 6 and all(x > 0 for x in gaps(got)), repr(err) if err else json.dumps(got))


class Hung(Exception):
    pass


def _alarm(signum, frame):
    raise Hung()


def nav(page):
    """A 5-notch wheel with a navigation 10 ms in: the command may succeed or
    error, but must return within 10 s, and the browser must still answer."""
    page.evaluate("setTimeout(() => location.href = 'about:blank', 10)")
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(10)
    returned = True
    try:
        page.mouse.wheel(0, 500)
    except Hung:
        returned = False
    except Exception:  # noqa: BLE001 - an error is an allowed outcome; a hang is not
        pass
    finally:
        signal.alarm(0)
    page.wait_for_timeout(500)
    return {"returned": returned, "alive": page.evaluate("1 + 1") == 2}


got, err = session({**HUMANIZE, **WIN}, nav)
row(R8, not err and got == {"returned": True, "alive": True}, repr(err) if err else json.dumps(got))

EXPECTED = 8
for name in sorted(results):
    print(f"{'PASS' if results[name] else 'FAIL'}  {name}")
if len(results) != EXPECTED:
    notes.append(f"expected {EXPECTED} rows, found {len(results)}")
for n in notes:
    print(f"      {n}")
sys.exit(0 if len(results) == EXPECTED and all(results.values()) else 1)
```

This passes config the way `verify_sp2b.py` does: a `json.dumps` string, or `None`. Row 8's `signal.alarm` is POSIX-only. The script runs on the WSL box and in CI, both Linux.

RED-check row 8's own guard once by hand. In a scratch copy, replace `page.mouse.wheel(0, 500)` with `page.wait_for_timeout(15000)` and run it. Expected: R8 FAIL with `"returned": false` after about 10 s, which proves a hang is reported rather than waited out. Delete the scratch copy afterwards.

- [ ] **Step 2: Commit, push, copy to the box and run against the pre-SP2c build (RED).** This is Task 3 Step 2.

Run on the box: `git -C $R fetch -q origin worktree-sp2c-humanized-wheel && git -C $R show origin/worktree-sp2c-humanized-wheel:scripts/verify_sp2c.py > $V/verify_sp2c.py && cd $V && ./venv/bin/python3 verify_sp2c.py`.

Expected:
- R2 FAIL;
- R3 FAIL;
- R7 FAIL (stock gives 2 events);
- R1, R4, R5, R6 and R8 PASS;
- exit 1;
- `8` rows printed.

If R2 passes here, the verify measures nothing. STOP and find out why.

- [ ] **Step 3: After Task 3 Step 5's build, run again (GREEN).** Expected: 8 PASS, exit 0. Then Task 3 Step 6's mutant: R4 and R5 FAIL.

- [ ] **Step 4: Wire into CI.** In `.github/workflows/build-verify.yml`, after the line `          run verify_sp1a_chrome.py`, add:

```yaml
          run verify_sp2c.py
```

(`cp scripts/verify_*.py` on line 62 already copies it.)

- [ ] **Step 5: Commit**

```bash
git add scripts/verify_sp2c.py .github/workflows/build-verify.yml
git commit -m "test(sp2c): browser verify for humanized wheel notches, in CI"
```

---

### Task 5: Ledger, docs, PR

**Files:**
- Modify: `docs/superpowers/plans/2026-09-02-followon-roadmap.md` (ledger)
- Modify: `docs/superpowers/measurements/2026-10-sp2c-wheel.md` (verify results)

- [ ] **Step 1: Append the verify evidence to the measurement doc.** Add a section "Verify (WSL `chrome`)" with:
  - the RED run (Task 4 Step 2) verbatim;
  - the GREEN run (Task 4 Step 3);
  - the mutant run;
  - `components_unittests` `MouseTrajectoriesTest.*` (10 passed) and the clamp RED.

Add a "Not done" line: host-native arm (`chrome.exe` with `humanize:enabled` vs `baselines/chrome-8037-wheel.json`, including animation). It needs a Windows rebuild, which is the owner's call.

- [ ] **Step 2: Ledger.** In `2026-09-02-followon-roadmap.md`, add a row in the existing ledger table's format:
  - slice `SP2c humanized wheel`;
  - status `shipped (WSL)`, with `partial: host-native arm open`;
  - pointer to `measurements/2026-10-sp2c-wheel.md`.

  Read the table header first and match its columns.

- [ ] **Step 3: Commit, push the branch, open the PR.** The PR body carries evidence: the oracle summaries, the RED and GREEN verify output, the unit-test output, the `gn check` line, and the export gate output. Name what was not run (host-native arm). No session URLs.

```bash
git add docs/superpowers/plans/2026-09-02-followon-roadmap.md docs/superpowers/measurements/2026-10-sp2c-wheel.md
git commit -m "docs(sp2c): verify evidence and ledger"
git push -u origin worktree-sp2c-humanized-wheel
gh pr create --title "SP2c: humanized wheel notches (Windows)" --body-file /private/tmp/claude-501/-Users-<user>-GolandProjects-github-com-lang315-camoucrome/f58518de-b499-4f19-8019-5aabd1640ad4/scratchpad/sp2c-pr-body.md
```

- [ ] **Step 4: Merge order.** Per CLAUDE.md, a slice that changes the box tree lands on the box first. It is already committed there (Task 3 Step 7) and `check_checkout_sync.sh` is rc 0, so merging does not turn CI's sync gate red. Tell the owner the re-pin (due 2026-10-20) must carry `sp2c-humanized-wheel` in its rebase.
