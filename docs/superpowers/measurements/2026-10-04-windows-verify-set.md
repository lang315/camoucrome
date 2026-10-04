# Step 1 finish: the named Windows verify set (2026-10-04)

The spec is `docs/superpowers/specs/2026-10-04-step1-finish-design.md` and the
plan is `docs/superpowers/plans/2026-10-04-step1-finish.md`. Every number
below is quoted from a host log or a command output of this session. Nothing
was retyped from memory.

The binary under test is the fork's
`D:\camou-win\chromium\src\out\Release\chrome.exe` 154.0.8037.93 (built
2026-10-03, `2026-10-03-windows-substrate.md`, "The crashpad lever"). No
Chromium build was started for this step. Every host command went through the
sshgate MCP server; the long runs were detached through `Win32_Process Create`
and polled.

## Preconditions

- **Stock control.** The host's Google Chrome is
  `C:\Program Files\Google\Chrome\Application\chrome.exe` 154.0.8037.93,
  the pin's tag. Google Update was about to move it to 155 (stable on
  2026-10-06), so it was held: the task
  `GoogleUpdaterTaskSystem156.0.8067.0{5C360162-E68E-44C8-A4A8-8CA40CAF4F3A}`
  reads `Disabled`, the services `GoogleUpdaterService156.0.8067.0` and
  `GoogleUpdaterInternalService156.0.8067.0` read `Stopped Disabled`, and the
  version read afterwards was `host-chrome=154.0.8037.93`. The runbook's §7
  ("The stock control on the host") says how to release it at the re-pin.
  Every run of the set re-reads it: the first line of each log is
  `mode=… stock=154.0.8037.93 pin=154.0.8037.93`.
- **Verify tree.** `D:\camou-win\tree` was refreshed from the runner clone by
  `git archive` and untarred in place, first to main `babbd2f` (tar sha256
  `8cb734c9…` on both sides; `git diff --diff-filter=DR 9125be6 babbd2f`
  empty, so no stale file), then to each branch head the same way. The
  final runs ran on `da4a151`, stamped in `D:\camou-win\tree.commit`, tar
  sha256 `de35fda4…` on both sides.
- **Go probe.** Rebuilt from the tree's `client/go` at every client change
  (`go test ./...` ok, `go-build=0`), because the probe at
  `D:\camou-win\probes\green` predated PR #17.
- **Host font inventory.** 118 families
  (`System.Drawing.Text.InstalledFontCollection`, Windows 10 22H2). Against
  `settings/fonts.json` `families.Windows.list` (116): every listed family is
  on the host, and the host adds two, `ROG Fonts` and
  `AniMe Matrix - MB_EN`, ASUS fonts that identify this machine.

## The set

`scripts/windows_verify_set.py` holds 21 entries. `red` runs each against the
stock `chrome.exe` (`CAMOU_EXE`) and requires a non-zero exit with at least one
FAIL row; `green` runs the fork and requires the asserted row count (or the
`ALL_PASS` line, or, for the host oracle, exactly its known-failing row). The
runner sets `CAMOU_SHELL=chrome` for every child, which makes `lib_shell`'s
default binary `chrome` with `--enable-logging=stderr`.

Final runs on `da4a151`, 11:48–12:00: `v2-red.log` `21/21 entries OK (red)`,
`v2-green1.log` and `v2-green2.log` each `21/21 entries OK (green)`.

| Entry | Criterion | RED (stock) | GREEN ×2 |
|---|---|---|---|
| `verify_windows_sandbox_env.py` | value takes effect, worker parity, audio service | rc=1 3 PASS 4 FAIL | 7 PASS 0 FAIL |
| `verify_windows_client.py` | value takes effect (three clients) | rc=1 5 PASS 6 FAIL | 11 PASS 0 FAIL |
| `verify_sp2b.py` | value takes effect | rc=1 1 PASS 2 FAIL | 3 PASS 0 FAIL |
| `verify_sp6b_launcher.py` | launcher contract | rc=1 3 PASS 2 FAIL | 5 PASS 0 FAIL |
| `verify_sp6b_driver.py` | driver contract | rc=1 3 PASS 3 FAIL | ALL_PASS |
| `verify_crash_dumps.py` | crash leaves no dump | rc=1 0 PASS 2 FAIL | 2 PASS 0 FAIL |
| `verify_sp6b_generator.py` | generated configs accepted | rc=1 0 PASS 36 FAIL | ALL_PASS |
| `verify_d_pointer_touch.py` | derived values take effect | rc=1 1 PASS 4 FAIL | 5 PASS 0 FAIL |
| `verify_sp1b.py` | values take effect, worker parity | rc=1 2 PASS 6 FAIL | 8 PASS 0 FAIL |
| `verify_sp3b.py` | WebGL values, worker parity | rc=1 1 PASS 8 FAIL | 9 PASS 0 FAIL |
| `verify_sp4a.py` | screen values | rc=1 3 PASS 3 FAIL | 6 PASS 0 FAIL |
| `verify_metric_jitter.py` | noise | rc=1 9 PASS 2 FAIL | 11 PASS 0 FAIL |
| `verify_audio_ii.py` | noise | rc=1 2 PASS 2 FAIL | 4 PASS 0 FAIL |
| `verify_ua_halfconfig_reject.py` | bad config refused | rc=1 2 PASS 4 FAIL | 6 PASS 0 FAIL |
| `verify_sp5b_domain.py` | bad config refused | rc=1 1 PASS 3 FAIL | 4 PASS 0 FAIL |
| `verify_webgl_pairing.py` | bad config refused | rc=1 4 PASS 5 FAIL | 9 PASS 0 FAIL |
| `verify_webgl_capability_identity.py` | bad config refused | rc=1 5 PASS 8 FAIL | 13 PASS 0 FAIL |
| `verify_navplatform_bucket.py` | bad config refused | rc=1 4 PASS 3 FAIL | 7 PASS 0 FAIL |
| `verify_fonts_ii.py` | font allowlist, worker parity | rc=1 3 PASS 3 FAIL | 6 PASS 0 FAIL |
| `verify_windows_fonts.py` | fonts on a Windows host | rc=1 4 PASS 1 FAIL | 5 PASS 0 FAIL |
| `verify_host_oracle.py` | rule 2 window keys, the whole surface vs stock | rc=1 1 PASS 3 FAIL | rc=1 3 PASS 1 FAIL, exactly O2 (known) |

`verify_sp6b_driver.py`'s C5 rows in the second GREEN read
`FAIL … (+26%)`, `ok … (+9%)`, `FAIL … (+27%)`, `ok … (+11%)`,
`FAIL … (+26%)`, `ok … (+9%)` against a 17.3 ms baseline: the FAILs are the
stock-driver rows the script expects to fail, the oks the patched drivers.

### What the runs found on the way

These were seen on the host and fixed before the final runs; each fix is its
own commit.

- **Two scripts could not start** (`a2bebee`). `verify_windows_fonts.py` and
  `verify_host_oracle.py` died before any row with
  `FileNotFoundError: [WinError 206] The filename or extension is too long`:
  a generated Windows identity (~37 KB) was put on a command line, which
  Windows caps at 32767 characters. The identity now travels by temp file.
- **The generator entry could never match a row count** (`cd00463`).
  `verify_sp6b_generator.py` prints a row per config only when it fails; its
  green is one RED row, `36/36 PASS (30 generated configs across 3 OSes)` and
  `ALL_PASS`. It is judged by `ALL_PASS`, which it prints only when all 36
  pass.
- **A false green from the runner** (`ea8e8d6`). `-Only a,b` inside a
  PowerShell `-Command` string became an array joined by a space, the runner
  selected no entry and printed `0/0 entries OK (red)` with exit 0. `--only`
  now refuses a name the set does not hold.

## The font alias finding, and its fix

Read from `fonts-iii-alias.patch` before any run: `gen --os windows` emits
`fonts:alias` (`Arial` → `Liberation Sans`, `Segoe UI` → `Selawik`, …) and
`FontCache::GetFontPlatformData` returns the alias target's lookup with no
fallback to the requested family. The bundle is not installed on Windows.

Measured (`verify_windows_fonts.py`, fork through each client, stock as the
control, 28-character string at 100 px):

```
before (1568bfb not yet applied):
note: F2 widths fork/stock: Arial=1807.99/1794.53; Segoe UI=1807.99/1808.06; Times New Roman=1807.99/1694.34; Verdana=1807.99/2057.67
FAIL  F2-py / F2-go / F2-node
after (da4a151):
note: F2 widths fork mono|serif/stock: Arial=1794.64|1794.64/1794.53; Segoe UI=1807.99|1807.99/1808.06; Times New Roman=1694.46|1694.46/1694.34; Verdana=2057.71|2057.71/2057.67
PASS  F2-py / F2-go / F2-node
```

Before the fix every claimed family measured the same 1807.99: the face the
failed alias lookups fell through to, close to Segoe UI's own width. A
generated Windows identity on a Windows host lost its real Arial, Times New
Roman and Verdana.

The fix is in the launcher, not C++ (`1568bfb`, `099cdd5`, `f777f59`):
`settings/launcher.json` `launch.native_fonts` drops `fonts:alias` and
`fonts:aliasLocal` from the config when the claimed OS (derive.cc ClaimedOs
over config and preset) equals the host OS, in the Python, Go and Node
clients. A config with nothing to drop passes through untouched, and an
unmapped host OS never triggers the drop. `fonts.json` has `alias_map`
entries only for Windows and macOS, so a Linux claim on Linux is unaffected,
and a Windows or macOS claim on the Linux build box keeps its aliases. Client
tests: Python 53 passed, Go ok, Node 20 pass.

**How the rows compare.** The fork carries `canvas:seed` under a generated
identity, which jitters `measureText` by design: the fork reads
+0.04..+0.12 px off stock. F2 therefore compares within `JITTER_TOL = 1.0` px
and additionally requires each family to win over both fallbacks (its
`", monospace"` and `", serif"` variants agree). That second rule decides
Segoe UI, whose width sits 0.07 px from the face the failed lookups landed
on. It was seen RED once, in a one-off run that aliased Segoe UI to a missing
font through `lib_shell` (no client drop):

```
aliased Segoe UI mono|serif: [1539.453125, 1694.3359375] control: [1808.056640625, 1808.056640625] fallbacks (1539.453125, 1694.3359375)
resolved(aliased SegoeUI) = False
real_ok(aliased, control) = False (want False)
real_ok(control, control) = True (want True)
```

The bare monospace fallback is 1539.45 and the serif fallback 1694.34; F2
also fails if those two come within the tolerance of each other.

### The other font rows

- **F1 PASS**: `ROG Fonts` is invisible to `measureText` in a window and a
  worker under the identity, and visible to stock in the same row. It counts
  because F2 passes in the same run; before the fix, "hidden" was
  indistinguishable from "every family broken".
- **F4 PASS**: per-character fallback (CJK, Thai, emoji in a family nobody
  has) measures `767.95/767.92` fork/stock. The fallback is the host's real
  one, which is what a Windows host claiming Windows should show. `fonts:list`
  does not filter it (no patch touches `PlatformFallbackFontForCharacter`).
  F4 cannot fail under stock, so its RED is the entry's F1.
- **F3, a note**: `the identity claims 119 families; stock cannot resolve 14:
  Bahnschrift Light Condensed, Bahnschrift Light SemiCondensed, Bahnschrift
  SemiBold Condensed, Bahnschrift SemiBold SemiConden, Bahnschrift SemiLight,
  Bahnschrift SemiLight Condensed, Bahnschrift SemiLight SemiConde, Cascadia
  Code SemiLight, Cascadia Mono SemiLight, Leelawadee UI Semilight` (first 10
  shown). These are GDI family names (the capture used the GDI enumeration),
  which DirectWrite treats as weights of one family, so stock Chrome on this
  host cannot resolve them by name either. The fork without aliases behaves
  the same, so on this host they are not a tell. On a host that lacks a
  claimed family stock would resolve, F3 is where it shows.
- **F5, a note**: `seeds 1 and 2 claim the SAME font lists (119 vs 119)`.
  Every generated Windows profile claims the same font list. That is a
  cross-profile finding for backlog item 2, not a failure here.

## The audio service

`media/audio/audio_manager_base.cc` reads `audio:sampleRate`, and on Windows
it runs in a sandboxed utility process. `verify_windows_sandbox_env.py` gained
A1 and A2:

```
note: A1: sandboxed + audio:sampleRate, AudioContext.sampleRate -> 22050 (expect 22050)
note: A2: sandboxed, no config, AudioContext.sampleRate -> 48000 (expect the device's own rate, not 22050 or the 44100 no-device fallback)
```

The renderer has a second reader of the same key, the no-device fallback in
`media/base/audio_parameters.cc` (44100 by default), so A1 alone could pass
through the renderer. A2's 48000 says the host has an output device and the
rate came from the audio service. Under stock, A1 fails (the RED row
counts above).

## The GPU process

Nothing in the GPU process reads the config. The change set's paths, by
directory: `third_party/blink` (61 patched files), `components/embedder_support`
(8), `content/browser` (7), `chrome/browser` (7), `media/audio` (4),
`sandbox/win` (3), `media/base` (3, all `windows-behaviour-ii`'s
`audio_parameters`), `chrome/renderer` (3), `content/renderer` (2),
`components/signin` (2), and one each in `components/omnibox`,
`components/network_time`, `components/gcm_driver`, `components/crash`,
`components/component_updater`, `components/BUILD.gn`; `additions/` holds only
`camoucfg`. No path is under `gpu/`, `ui/gl`, `components/viz` or
`content/gpu`. A patch that reaches the GPU process reopens this.

## The host oracle on Windows

O1 compares the fork under a generated Windows identity with the committed
capture of stock Chrome on this host:

```
0 DIFF; 177 leaves equal by value, 41 compared by type only, 6 named in KNOWN, 11 prefix-excluded (NOT compared); fork done=True pageError=None
PASS  O1 generated Windows identity: no difference from stock Windows Chrome outside the named set
PASS  O3 queryLocalFonts(): …
PASS  O4 brands: …
FAIL  O2 RED Linux claim: navigator.share / bluetooth absent (the gate follows the claim); …
```

Under stock (the RED run) O1 failed with `3 DIFF`, so O1 has a RED on
Windows.

- **O2 is a Windows finding, filed, not fixed.** Run alone under a generated
  Linux identity, the sub-run finished (`fork done=True`) and differed from
  the host only in `nav.appVersion`, `nav.platform`, `ua`, `uad.platform`
  and `uadHigh.platform`: no `navProto`/`windowNames` difference, so under a
  Linux claim the Windows build keeps `navigator.share`, `canShare` and
  `bluetooth`. The gate that removes them lives in `IS_LINUX`-only code. The
  set marks the row `known_fail=("O2",)`; delete that when the gate lands.
  A Linux claim on a Windows host is off the product path (roadmap decision
  3), so it ranks low.
- **HEVC on the flagship build**: `known: codecs.video/mp4; codecs="hev1.1.6.L93.B0":
  host=["probably", true] fork=["", false]`. The Windows build with the
  proprietary-codec pair still answers no, so backlog item 3 holds on
  Windows too.
- **WebGPU was not compared.** The oracle passes `--use-angle=swiftshader`,
  so the fork's `requestAdapter()` resolves to null and the `gpu` exclusion
  stays active (`known: gpu: host="<absent>" fork=null`). A run without that
  argv on this GPU host is backlog item 2's measurement.

## Step 1's change-loop criterion

Step 1 asks for a one-file change to go from edit to verified to exported on
Windows by a written procedure. The crashpad lever did that on 2026-10-03 by
runbook §7 "The change loop": edit and export on the WSL branch, `git apply
--3way` of the one patch in the Windows tree, an 8-step build, RED then GREEN
twice. The edit is on WSL by design (the box branch lives there). This step
records the criterion as met.

The Windows component build stays deferred: the next approved change times
one Blink `.cc` relink on `out\Release`, and that number decides it.

## What this does not establish

- **Baseline-comparing scripts** (`verify_sp0`, `verify_sp3a`,
  `verify_sp4_audio`, `verify_sp4_fonts`, `verify_sp1a_chrome`) are not in
  the set: their baselines are `content_shell` or Linux captures. Recapturing
  them from stock `chrome.exe` is step 2's work.
- **`verify_windows_client.py` passes the generator's wrapper as the
  config.** Line 130 sends `gen.generate()`'s `{config, launch}` object, so
  only the top-level `navigator.hardwareConcurrency` takes effect, and K1's
  "N ≥ 2 chunks" holds because the wrapper is large. With `["config"]` and
  the alias drop, a Windows identity is about 19 KB, under the 30000-char
  chunk, and K1 would fail. This predates the branch; it needs a larger
  identity shape (a macOS one) and is left for a separate change.
- **`verify_sp2.py` aborts under `CAMOU_SHELL=chrome`** (it refuses a
  `--headless` in `SHELL_FLAGS`). It is not in the set; run it on Linux.
- **Fonts on another Windows host.** F3 counts what this host lacks; a host
  without, say, an Office font set would show those as missing under a claim
  that lists them, and the launcher no longer aliases them.
- **Linux CI** was not run on this branch from here; `test_lib_shell_launch.py`
  (24 PASS, the frozen argv with `CAMOU_SHELL` unset) and the client suites
  are the evidence that it does not change. The PR's `checks` and the
  post-merge `build-verify` are the measurement.
