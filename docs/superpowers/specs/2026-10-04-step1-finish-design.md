# Step 1 finish: the named Windows verify set, the host oracle, process coverage and fonts

Design for closing step 1 of `plans/2026-10-02-long-term-roadmap.md`. Approved
with the owner on 2026-10-04. This step adds no Chromium build: everything here
runs against the `chrome.exe` 154.0.8037.93 already built in `D:\camou-win`
(`measurements/2026-10-03-windows-substrate.md`, "The crashpad lever"). A
defect that needs C++ goes to the next approved build, which is the Safe
Browsing work (backlog item 4).

## Preconditions (done 2026-10-04, re-asserted by every run)

- **The control stays on 154.** Stock Chrome on the Windows host is
  154.0.8037.93, which is the pin. Google Update would have moved it to 155
  on 2026-10-06, so it is held:
  - the scheduled task `GoogleUpdaterTaskSystem156.0.8067.0{…}` is Disabled;
  - the services `GoogleUpdaterService156.0.8067.0` and
    `GoogleUpdaterInternalService156.0.8067.0` are StartupType Disabled.

  The 156 re-pin re-enables all three (runbook §7). Every run of the set
  asserts the stock version before it measures anything.
- **The verify tree is current.** `D:\camou-win\tree` holds main `babbd2f`:
  - it was made with `git archive` of the runner clone and untarred in place;
  - the tar's sha256 was equal on both sides;
  - `git diff --diff-filter=DR 9125be6 babbd2f` is empty, so untarring in place
    leaves no stale file;
  - the stamp is `D:\camou-win\tree.commit`.

## 1. One switch: verifies drive `chrome` instead of `content_shell`

Most verifies call `lib_shell.session()` or `launch()` without `shell=`, so they
start `content_shell` with `--ozone-platform=headless`. A Windows release out
dir has no `content_shell.exe`.

Setting `CAMOU_SHELL=chrome` in the environment changes three things in
`lib_shell`:
- `SHELL` becomes `CHROME`;
- `SHELL_FLAGS` becomes `CHROME_FLAGS`;
- `--enable-logging=stderr` is added. The `camoucfg:` startup lines that
  `STDERR_LOG` readers assert on reach stderr only with that switch on
  `chrome`.

With the variable unset, nothing changes: Linux CI keeps `content_shell` byte
for byte. Scripts that pass a literal `--ozone-platform` are not in the set.

## 2. The named Windows verify set

The set is `scripts/windows_verify_set.py`: a list of entries, each
`(script, success-line regex, RED kind)`, and a runner.

| Mode | Environment | Requirement |
|---|---|---|
| `green` | the fork | every script exits 0 and prints its success line with the asserted count |
| `red` | `CAMOU_EXE` = the host's stock `chrome.exe`, the same version and the same machine | stock ignores `CAMOU_CONFIG`, so every entry whose RED kind is `stock` must exit non-zero |

- **Order.** An entry's GREEN counts only after its RED has been seen.
- **RED kind `own`.** These are entries whose rows stock also passes: worker
  parity, and fallback on bad config. They rely on the script's built-in
  control rows instead, and the runner records that this is the kind of RED
  they have.
- **Pre-checks.** The runner refuses to start if the host's stock Chrome
  version (the version directory under `Application\`) is not `upstream.env`'s
  tag. It sets `CAMOU_SHELL=chrome` for its children itself rather than
  refusing to start without it.

Membership, by the roadmap's five criteria:

| Criterion | Scripts |
|---|---|
| (a) a spoofed value takes effect | `verify_windows_sandbox_env`, `verify_windows_client`, `verify_sp2b`, `verify_sp6b_generator`, `verify_sp1b`, `verify_sp3b`, `verify_sp4a`, `verify_d_pointer_touch` |
| (b) noise behaviour | `verify_metric_jitter`, `verify_audio_ii` |
| (c) worker parity | rows inside `verify_windows_sandbox_env`, `verify_sp1b` (N6, N8), `verify_sp3b` (V9), `verify_fonts_ii` (F-WORKER) |
| (d) fallback on bad config, no crash | `verify_ua_halfconfig_reject`, `verify_sp5b_domain`, `verify_webgl_pairing`, `verify_webgl_capability_identity`, `verify_navplatform_bucket` |
| (e) rule 2 window keys against stock `chrome` | `verify_host_oracle` (O1 compares `windowKeys`, `navProto`, `windowNames` to the host's stock capture; its O2 Linux-claim sub-run is the RED) |
| launcher and driver contract | `verify_sp6b_launcher`, `verify_sp6b_driver`, `verify_crash_dumps` |
| fonts | `verify_fonts_ii` (Windows family names), `verify_windows_fonts` (new, §5) |

**Counts.** A count is the script's own asserted row count. Where a script
asserts none, the count is fixed in the set from its first GREEN run, after a
reading of the rows.

**Left out, each for a stated reason:**
- `verify_fonts_bundle` and `verify_font_metrics`: they test the Linux bundle
  and fontconfig.
- `verify_windows_behaviour`: its share fake is `#if BUILDFLAG(IS_LINUX)`.
- `verify_sp0`, `verify_sp3a`, `verify_sp4_audio`, `verify_sp4_fonts`,
  `verify_sp1a_chrome`: they compare against `content_shell` or Linux
  baselines that would need recapturing from stock `chrome.exe` first. That is
  step 2's recapture work, not this step's.
- `verify_chrome_object`: its only RED (O4) is `content_shell`, which a
  Windows release out dir lacks, and its O1–O3 pass on stock, so on Windows it
  would have no RED at all. `verify_host_oracle` O1 covers the window keys with
  a RED.
- `verify_sp7_fieldtrial`: F1–F4 need `content_shell`, and C2 is backlog
  item 6.
- `verify_sp7_phonehome`: backlog item 4 owns it.

**Adaptations, each the smallest that works:**
- `verify_fonts_ii`: its three host family names get Windows values when
  `os.name == "nt"`: `Verdana`, `Verdana` (its PostScript name) and `Georgia`.
  Neither is a generic default on Windows, which keeps F-DIRECT unconfounded.

## 3. The host oracle on Windows

`verify_host_oracle.py` runs on the host as written: the fork under a generated
Windows identity against the committed `chrome-8037-stock-oracle-windows.json`.

The host has a real GPU, so two exclusions may lift on their own, and each is
designed to:
- `gpu`: when a WebGPU adapter appears, the subtree is compared.
- HEVC: when the fork answers `"probably"`, the row is compared.

Every DIFF it prints is recorded as found. A difference that is the host's real
GPU under a spoofed identity is evidence for backlog item 2, not a defect to fix
in this step. The result is the four rows O1–O4 with their counts, and the DIFF
list.

## 4. Other process types

- **GPU process: no consumer.** No file in `patches/` touches `gpu/`, `ui/gl`,
  `components/viz` or `content/gpu`. `additions/` holds only `camoucfg`. The
  three `media/base` files belong to `windows-behaviour-ii` (`audio_parameters`),
  which runs in the audio service. So nothing in the GPU process reads the
  config, and there is nothing to measure there. The measurement doc records
  this closure with the path list, and a later patch that reaches the GPU
  process reopens it.
- **Audio service: one sandboxed measurement.** `media/audio/audio_manager_base.cc`
  reads `audio:sampleRate` and `audio:bufferFrames`, and on Windows it runs in
  a sandboxed utility process. `verify_windows_sandbox_env` gains two rows:
  - A1: under `{"audio:sampleRate": <a rate the device does not report>}`,
    `new AudioContext().sampleRate` equals the configured rate.
  - A2: with no config it equals the device's real rate.

  It is RED first against stock, where A1 fails. The script's asserted count
  moves from 5 to 7.

## 5. Fonts on Windows: `verify_windows_fonts.py`

`fonts:list`, `fonts:alias`, `fonts:aliasLocal` and `fonts:local` are enforced
in Blink with no OS gate. On a Windows host the claimed Windows families are
mostly real host fonts. Read against `settings/fonts.json`:
- the host has 118 families;
- the claimed `families.Windows.list` has 116, every one of them on the host;
- the host holds two that are not claimed: `ROG Fonts` and
  `AniMe Matrix - MB_EN`, both ASUS fonts that identify this machine.

| Row | Measures | RED |
|---|---|---|
| F1 | a host-only family (`ROG Fonts`) is invisible to `measureText` under a generated Windows identity, in a window and a worker. `document.fonts.check()` is not used: it returns true for any family no `@font-face` names, so it says nothing about a system font | stock sees it |
| F2 | a claimed family the host has (`Arial`, `Segoe UI`, `Times New Roman`, `Verdana`) renders as the host's real face: widths equal stock's at 100 px, through the Python, Go and Node clients (rows F2-py, F2-go, F2-node) | see below |
| F3 | a note, not a row: claimed families the host lacks, counted (0 on this host today); each one is a tell to record, since a real device would have it | — |
| F4 | per-character system fallback (CJK, emoji) through DirectWrite: whether a family outside the list becomes observable through fallback, which `fonts:list` does not filter (no patch touches `PlatformFallbackFontForCharacter`) | stock |
| F5 | a note, not a row: whether two generated identities claim different font lists. The same list on every profile is a cross-profile finding for backlog item 2, not a failure of this step | — |

**F2's expected RED is the fork itself.**
- *What the code does.* `gen --os windows` emits `fonts:alias` mapping, for
  example, `Arial` to `Liberation Sans` and `Segoe UI` to `Selawik`.
  `FontCache::GetFontPlatformData` (`fonts-iii-alias.patch`) looks up the alias
  target and returns that result, with no fallback to the real family. The
  bundle fonts are not installed on Windows, so on a Windows host a generated
  Windows identity would lose its real `Arial`. This was read from the code and
  is not yet measured.
- *What to do.* Measure it first. If F2 is RED, the fix is client-side and
  needs no build. When the host OS equals the claimed OS, the launcher drops
  `fonts:alias` and `fonts:aliasLocal`, because the claimed families are the
  host's real ones. This becomes a rule in `settings/launcher.json`,
  implemented in the Python, Go and Node clients with tests, and F2 must then
  go GREEN through each client.
- *Out of scope.* A claimed family the host lacks then shows as missing (F3),
  which is the cost to record. A per-family rule ("alias only when the host
  lacks the family") would need host font enumeration in three clients. It
  waits for F3 to show a non-zero count.

If F1, F4 or F5 shows a leak that needs C++, the finding goes to the next build
with its RED attached. It is not fixed in this step.

## 6. The change loop criterion

Step 1's done-criterion asks for a one-file change to go from edit to verified
to exported on Windows by a written procedure. The crashpad lever did this on
2026-10-03, following runbook §7 "The change loop":
- edit and export on the WSL branch;
- `git apply --3way` of the one patch in the Windows tree;
- an 8-step build;
- RED then GREEN, twice.

This design records that criterion as met. The edit happens on WSL by design:
the box branch lives there and the Windows tree is an apply target.

The component build (`out\Default` on Windows) is deferred. The next approved
change (Safe Browsing) times one Blink `.cc` relink on `out\Release`, and that
number decides whether a component build is worth its hours.

## Done when

- [ ] `windows_verify_set.py red` ran on the host: every `stock` entry exits
  non-zero. The output is in the measurement doc.
- [ ] `windows_verify_set.py green` ran on the host: every entry printed its
  success line at its asserted count, run twice. `verify_sp6b_driver` was run
  on an idle host (its C5 is load-sensitive).
- [ ] The host oracle's O1–O4 and its DIFF list are recorded. Each DIFF is
  either fixed in this step or entered in the backlog with its evidence.
- [ ] Audio service rows A1 and A2 are GREEN after a RED. The GPU process
  closure is recorded with its path list.
- [ ] F1–F5 are measured. F2's alias finding is confirmed or refuted, and if
  confirmed, fixed in the three clients and GREEN through each.
- [ ] Linux CI is unchanged: `build-verify` is green with `CAMOU_SHELL` unset.
- [ ] Documentation:
  - the measurement doc `measurements/2026-10-04-windows-verify-set.md`;
  - roadmap step 1 marked done, or with exactly what remains named;
  - runbook §7 gains "re-enable Google Update at the 156 re-pin".

## Out of scope

- Recapturing `content_shell` and Linux baselines from stock `chrome.exe`
  (step 2).
- Any C++ change, and the component build.
- Backlog items 2 (WebGPU and the device per profile), 4 (Safe Browsing) and
  6 (the field-trial access violation). This step may add evidence to them.
