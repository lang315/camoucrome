# Camoucrome long-term roadmap (from 2026-10)

Written 2026-10-02, revised the same day after a four-way review (feasibility,
anti-detection, product, strategy). It succeeds the two earlier roadmaps as
the place where ordering is decided:

- `2026-09-02-followon-roadmap.md` stays the per-slice status ledger for the
  SP4 follow-on arc.
- `2026-09-09-completion-roadmap.md` stays the gap analysis against the SP map
  and Camoufox. Its rejections ("do not re-propose") and harness gates still
  hold; nothing here reopens them.

This document does not restate either. It says what comes next and in what
order.

## Shape of this roadmap

One person and one build machine cannot honestly plan twelve months in
phases. So this roadmap has two parts:

- **Steps 0 to 3 are concrete**, with work lists and done-criteria. They end
  at the first release.
- **Everything after is a ranked backlog**, re-ranked at every release and at
  every Chrome milestone.

## Decisions this roadmap rests on

Taken with the project owner on 2026-10-02:

1. **Two goals, in this order of tie-break: a product people can use, then
   deeper anti-detection.** Community and contributor work is not a goal.
2. **The user is an automation developer who runs many identities on one
   machine.** The product is a browser archive plus launcher libraries
   (Python, Go, Node), not a desktop app. Installer, sync, sign-in and crash
   reporting stay out.
3. **Windows is the flagship platform; Linux ships at once as a labelled
   beta.** macOS is out of scope (it needs its own build machine).
4. **Measurement comes before new spoofing work**, in three layers: the host
   oracle, the public detectors, and commercial anti-bot systems. The first
   two gate the first release. The third starts after it.

The non-negotiable rules in `specs/00-conventions.md` bind every step: no
JavaScript injection, native accessors, worker parity, coherence over
coverage, fall back to the real value, bad config never crashes.

### What "many identities on one machine" implies

A Windows build that reports the real GPU, fonts, voices and screen gives
every profile the same device. Different noise seeds on top of one device
read as one machine with noised canvas, which links the profiles.

So the product's identity on Windows is **a different Windows device per
profile**, not the host's real one:

- Each profile carries a device preset (GPU profile, screen, cores, memory,
  fonts list, voices) that differs from the host and from other profiles.
- Each profile's noise seeds are stable for the life of that profile.
- **Cross-profile linkability is a first-class measurement**: two profiles on
  one host must not share a fingerprint component that identifies the host.
- Windows as host still matters. A Windows host claiming another Windows
  device keeps the OS-level surfaces real (font rendering, DirectX backend,
  system voices), which a Linux host cannot.

## Where the project stands

As of 2026-10-02. Later changes are recorded under the step that made them.

- SP0 to SP7 and the follow-on arc are shipped or partial, with residuals
  recorded per slice.
- The change set is 32 patches on pin `f89f3a4363` (Chrome 154.0.8037.93),
  re-pinned on 2026-10-02 (`measurements/2026-10-repin.md`): 37/37 commits
  rebased, 2 trivial conflicts, zero semantic conflicts, 6 h 10 m of build.
- **The pin is current but ages fast.** 155 goes fully stable 2026-10-06, 156
  on 2026-10-20, 157 on 2026-11-03 (chromiumdash, read 2026-10-02). The stable
  milestone moves every two weeks, so **the next re-pin is due by 2026-10-20**.
  154 was chosen over 155 early-stable because the Windows host that captures
  every stock baseline runs 154.
- The 2026-09-24 review is merged (PR #1, merge `2e12467`).
- The first native Windows build exists (`D:\camou-win`, `out\Release`,
  58,285 steps, about 7.5 hours from clean). One Windows-only bug has been
  found and fixed: the sandbox dropped `CAMOU_*` from the renderer
  environment (`windows-sandbox-env`). That tree was on the old pin; it moved
  to 154 on 2026-10-03 (step 1).
- On Windows, exactly one key has been checked in a browser
  (`navigator.hardwareConcurrency`, main thread and worker).
- The Linux build is verified and packaged (`scripts/package.py`), but there
  is no tag and no release.
- CI builds and verifies on Linux only, on one self-hosted runner in WSL on
  the build PC. The repo is public.
- There is no LICENSE file. `client/node/package.json` declares MPL-2.0.
  Settled 2026-10-03: MPL-2.0 (step 3).
- Codec distribution licensing is open (`settings/build-args.gn`, "OPEN,
  deliberately"); the completion roadmap says it must be settled before
  anything ships. Settled 2026-10-03: ship with the codecs (step 3).

## Steps to the first release

| Step | Content | Rough size |
|---|---|---|
| 0. Re-pin and safety | Move to current stable, fix the recovery tool, harden the runner | 1–2 weeks |
| 1. Windows foundation | Edit loop, harness and clients on Windows; a named verify set green | 4–6 weeks |
| 2. Measurement, layers 1 and 2 | Oracle and public detectors, with a like-for-like stock control | 2–3 weeks |
| 3. First release | Windows flagship plus Linux beta, with the release gates closed | 2–3 weeks |

Sizes are estimates for one person. A clean Windows build costs about 7.5
hours of the only build machine, and the WSL and Windows builds must not run
at once.

### Step 0: re-pin and safety

**Goal:** a current pin, and a project that survives losing its machine.

- **Re-pin to the current stable milestone.** Do it as a drill and time each
  part. The one recorded re-pin (`measurements/2026-09-09-sp6a-version-honesty.md`)
  had 26 patches and one conflicting hunk; this one has 32.
- **Fix `rebuild_branch.sh`** (it aborts mid-series, then its own guard
  refuses to run again). It is the only recovery tool.
- **Write the re-pin as a script and a checklist**, including the check that
  `chrome/VERSION` is a shipped stable version.
- **Recovery drill.** Write down, and try once, how to rebuild the box branch
  and both out dirs from the repo alone.
- **Runner hardening.** Settle the open decision (dedicated runner user, no
  sudo, WSL interop off). It was deferred on 2026-09-25 to get the
  Windows build running; the repo is public and the runner sits on the only
  build machine.

Done when: the pin is the current stable milestone, CI is green on it, the
re-pin time is recorded, and `rebuild_branch.sh` recreates the branch from a
clean state.

**Status: done.** (2026-10-02: done except CI on the merged pin; `build-verify`
has since been green on every run that completed on `main` after the re-pin's
merge (one run was cancelled and superseded; merges touching no filtered path
have no run), as of 2026-10-04.)
`plans/2026-10-02-step0-repin-and-safety.md` ran as six tasks; the evidence is
`measurements/2026-10-repin.md` and the procedure is
`specs/repin-runbook.md`.

| | |
|---|---|
| Pin | `154.0.8037.93` (`f89f3a4363`), 37/37 commits rebased, zero semantic conflicts |
| Re-pin cost | about 7 h 40 m of machine time, 6 h 10 m of it one from-scratch build |
| `rebuild_branch.sh` | fixed (atomic, signal-safe, absolute worktree) and drilled on the real tree: `difflines=0` in 100 s; a broken series leaves no branch and no worktree (rc 128) |
| Re-pin as a script | `scripts/repin.py` (`target`, `check`, `retarget`) with tests, plus the runbook checklist |
| Runner hardening | `lang` has no sudo, WSL interop and automount off, runner re-registered; three escape routes verified closed |
| Verify sweep on the new pin | 48/51 green, coherence 7/7, `verify_host_oracle` 0 DIFF with O1–O4 PASS (177 leaves equal by value, 41 by type, 21 not compared and named) |
| CI | green on `main` **before** the re-pin (run 36974876383); the re-pin's own `build-verify` runs when its PR merges |

Three findings the re-pin surfaced are backlog items 2, 3 and 4, not step 0
work: the Safe Browsing request, the HEVC claim and WebGPU adapter identity.

### Step 1: Windows foundation

**Goal:** the Windows build is developed and verified with the same
discipline as the Linux one.

- **Verification target is `chrome.exe`.** The repo already settles this:
  `content_shell` has no `window.chrome` and rebuilds UA metadata
  (`specs/00-conventions.md`), and `package.py` targets `//chrome:chrome`.
- **A Windows component build** (`out\Default`) for iteration, next to the
  release build. Measure the incremental rebuild time first; it sizes
  everything below.
- **The Windows change loop.** Today the Windows tree is an `apply.sh`
  application with no way back. Define edit, export and re-apply for it, and
  a lock so the WSL and Windows builds never overlap.
- **Parametrise `lib_shell.py`** (binary path, flags, temp dir). It hardcodes
  the Linux `content_shell` path, `--ozone-platform=headless` and `/tmp`, and
  41 of the 50 verify scripts go through it. Run it natively on Windows.
- **Clients on Windows** (Python, Go, Node): paths, environment transport
  and its length limits, chunked `CAMOU_CONFIG_1..N`, `CAMOU_PRESET`, temp
  directory cleanup, tests. Step 2 measures through the client, so this
  cannot wait for the release step.
- **A named Windows verify set.** Not all 50 scripts. The oracle (step 2)
  covers "does the fork differ from stock where it should not". The verify
  set covers what the oracle cannot see: spoofed values taking effect, noise
  behaviour, worker parity, fallback on bad config, and the rule 2 window-keys
  diff on `chrome`. List the set by name; each script is seen RED on Windows
  once before its GREEN counts.
- **Other process types.** The sandbox fix covered renderers and utilities.
  Check the GPU process and the audio service read the config too.
- **Fonts on Windows.** Fontconfig does not exist there. Decide and measure
  how a Windows profile presents a font list that differs from the host's.

**Status 2026-10-03.** Shipped: `lib_shell` resolves its binaries and temp dir
from the environment (`CAMOU_OUT`, `CAMOU_EXE`, `tempfile.gettempdir()`, PR #4),
and the layout block eleven scripts repeated is one `lib_shell.layout()` call
(PRs #5, #6). Flags were deliberately not parametrised: `launch()` already takes
`extra_flags` and `CHROME_FLAGS` is platform-neutral.

Then, on the Windows host and with no build: `verify_sp2b.py` is green natively on
`chrome.exe` (3 of 3, with a RED control), and `launch()` gained a `sandbox`
parameter because `--no-sandbox` was unconditional and that is the one argv under
which the project's only Windows-specific bug is invisible. With it,
`verify_windows_sandbox_env.py` measures a renderer-consumed key under the real
sandbox: **the `windows-sandbox-env` fix holds on Windows**, main thread and
dedicated worker alike (5 of 5, seen RED first; the no-config controls read the
machine's real 16 in both). `CAMOU_EXE` is measured there too, in both
directions, so all three things PR #4 shipped have run against a real Windows
browser. The Python client runs on Windows: its tests, the launcher verify (5 of
5) and the driver verify's Python rows pass, and a sandboxed `camoucrome.launch()`
carries a chunked 37 KB identity to the renderer and a worker (5 of 5, seen RED
first). The Go and Node clients run there too: the driver verify's six rows
pass, and the same chunked identity reaches a sandboxed renderer and worker
through each of them (11 of 11, seen RED first). The Windows bugs fixed on the
way include a temp profile left behind on every launch. Still open for this
step: the component build, the change loop end to end, fonts, and the
baseline-comparing verifications, which the 154 Windows binary (below) now
makes possible.
Evidence:
`measurements/2026-10-03-windows-substrate.md`.

**Superseded the same evening:** the owner chose to re-point the Windows tree
to 154 overnight so that backlog item 5's C++ lever could be measured on
Windows. `D:\camou-win\chromium\src` is at `f89f3a4363` with the change set
applied and `chrome.exe` 154.0.8037.93 built (5 h 31 m, 57,101 steps;
`measurements/2026-10-03-windows-substrate.md`, "The crashpad lever"). So the
binary and the host's stock Chrome now share a version. The 156 re-pin will
cost a second Windows build; that was the price, and it was accepted. The
ruling as first written:

Ruling 2026-10-03: the Windows tree stays on the **old** pin (`507c6ee3e2`,
153.0.8010.36) until the re-pin due 2026-10-20. Re-pointing it to 154 would
cost a from-scratch Windows build of about 7.5 hours that Chrome 156 obsoletes
in 17 days, and it would put that build on the same day as the re-pin's own
7 h 40 m of machine time (6 h 10 m of it the WSL build) on one machine, with the
build-overlap lock this step still owes. The plumbing is verified against the
153 build that already exists instead
(`plans/2026-10-03-step1-windows-substrate.md`). Stock baselines come from the
Windows host's Chrome 154.0.8037.93, while the binary being verified runs
153.0.8010.36; only behavior-asserting verifications run there, as baseline
comparisons would differ on the Chrome version rather than the Windows fork.

Done when: the named verify set is green on `chrome.exe` at asserted counts,
each seen RED once, and a one-file change goes from edit to verified to
exported on Windows by a written procedure.

**Status 2026-10-04: done, with one filed exception.** The named set is
`scripts/windows_verify_set.py`: 21 entries covering spoofed values, noise,
worker parity, bad config, the host oracle's window keys, the launcher and
driver contracts, crash dumps and fonts. Against the host's stock Chrome
154.0.8037.93 it read `21/21 entries OK (red)`; against the fork, twice,
`21/21 entries OK (green)`. The exception: the host oracle's O2 (a Linux claim
hides `navigator.share`/`bluetooth`) fails on the Windows build, because the
renderer block in `windows-oracle.patch` only enables them for a Windows or
macOS claim and nothing disables them under a Linux claim (stock Windows Chrome
ships both on). It is marked as the oracle's one known-failing
row and filed below. Along the way:
- **Fonts on Windows were broken under every generated identity.** The
  identity's `fonts:alias` sent the host's real Arial, Times New Roman and
  Verdana to bundle fonts Windows does not have. The launchers now drop the
  aliases when the claimed OS is the host's (`settings/launcher.json`
  `launch.native_fonts`), and the four probed claimed families (Arial, Segoe UI, Times New Roman,
  Verdana) measure as stock through all three clients. A host-only font (ASUS's `ROG Fonts`) stays hidden.
- **Other process types.** The audio service reads its key under the real
  sandbox (22050 configured, 48000 real). Nothing that runs in the GPU
  process reads the config (the only patched code that runs there is crashpad's
  handler-behaviour switch, which reads no config); no patched path is under
  `gpu/`, `ui/gl`, `components/viz` or `content/gpu`.
- **The change loop** criterion was met by the crashpad lever on 2026-10-03
  (runbook §7 "The change loop").

The Windows component build stayed deferred until a Blink relink on
`out\Release` was timed. **Timed on 2026-10-04: 38.38 s, 49 steps.** That was
one Blink `.cc` whose mtime was touched, so a component build is not needed
(`measurements/2026-10-04-safe-browsing.md`). The stock Chrome on the host is held at the pin
(Google Update disabled; runbook §7 says how to release it at the re-pin).
Evidence: `measurements/2026-10-04-windows-verify-set.md`.

### Step 2: measurement, layers 1 and 2

**Goal:** know what detectors see, for the fork and for a stock control,
before choosing any new spoofing work.

Preconditions: the pin milestone equals the control Chrome's milestone (the
host's Chrome auto-updates; assert its version), and both arms run through
the project's client with the same argv. Driving the control over raw CDP
while the fork goes through patchright would confound the result.

- **Layer 1, host oracle.** The fork under a generated Windows identity
  against stock Chrome on that host, every differing leaf as a line.
- **Layer 2, public detectors.** CreepJS, BrowserScan, Pixelscan, sannysoft.
  Store the raw result and **named-row differences against the control**. No
  aggregate score: these tools disagree about what is good (some reward
  commonness, some punish rarity), and stock Chrome does not score perfectly.
- **Headed and headless as separate columns.** The clients default to
  headless, and headless has tells of its own.
- **Stability across relaunch.** The same profile, launched twice, reports
  the same canvas and audio hashes and the same device IDs.
- **Cross-profile linkability.** Two profiles on one host: list every
  fingerprint component they share that a different machine would not.
- **Noise as a tell.** Known-pixel readback: a solid fill must not read back
  non-uniform in a way a detector can flag as farbling.
- **Network fingerprint.** JA4, HTTP/2 SETTINGS and header order against the
  control. The fork should inherit these unchanged; this row proves it.

Done when: one command produces these tables for the fork and the control,
two runs agree row for row apart from a stated list of volatile rows, and the
baseline is committed under `docs/superpowers/measurements/`.

**Status 2026-10-04: done, with the fork's instability recorded.**
`scripts/measure_step2.py` runs both arms through `camoucrome.launch()` on the
Windows host, headed and headless, with six probes:

- the oracle;
- noise readback;
- the network fingerprint through `tls.peet.ws`;
- relaunch stability;
- cross-profile linkability;
- CreepJS, BrowserScan, Pixelscan and sannysoft.

Each probe was seen RED first, and the version and argv preconditions refuse
on purpose. Two null runs agree (`0 rows disagree outside VOLATILE`). Fork
runs agree except on three rows where the fork itself is unstable: the WebGPU
adapter, the HEVC answer and a CreepJS rendering check. The 154 baseline is
committed. The findings are ranked into the backlog below ("Re-rank from the
step 2 tables"). Rule 2's window keys are now measured on `chrome.exe`, and
are equal to stock. Evidence: `measurements/2026-10-step2-baseline.md`, with
the tables in `measurements/step2-154/`. The 156 re-pin recaptures the
baseline.

### Step 3: first release

**Goal:** an automation developer installs it and launches a chosen identity
from the README alone.

Release gates, settled before any archive is published:

- **Codec licensing.** Ship without proprietary codecs and document the tell,
  ship with them and accept the exposure, or publish source only. **Decided
  2026-10-03: ship with them and accept the exposure.** The other two lose: no
  codecs is a tell on every page, and source-only defeats this step's 15-minute
  goal. The exposure is stated in the README ("Licence and codecs") and
  must be in the release notes. `settings/build-args.gn` records the decision.
- **LICENSE** for the repo, consistent with the client packages. **Decided
  2026-10-03: MPL-2.0**, the same as Camoufox and `client/node/package.json`.
  `LICENSE` is the canonical text and `client/python/pyproject.toml` declares
  it. Still owed for a binary release: `package.py` packs no license file, and
  a Chromium binary must carry Chromium's `LICENSE` and its third-party
  notices (`about:credits`).
- **Code signing.** The SP6 spec deferred it "until there are external
  users". Decide: sign, or document the SmartScreen warning. **Decided
  2026-10-03: unsigned for the first release.** The README says SmartScreen
  will warn on first run and how to proceed. Revisit when there are users;
  the paid options are an OV certificate (about USD 200–400 a year, and it
  still warns until it gains reputation) or Azure Trusted Signing (about USD 10
  a month, if an individual in the owner's country can enrol).
- **Acceptable-use statement.** **Decided 2026-10-04: none.** A statement was
  drafted on 2026-10-03 and dropped by the owner. MPL-2.0 binds nothing beyond
  copying and modification anyway, and its warranty disclaimer (sections 6
  and 7) stands on its own. The draft's codec paragraph moved to the README.
  It now names both GN args for the opt-out, not only `proprietary_codecs`,
  and says it is not legal advice.

Work:

- **Persist per-profile seeds.** `settings/launcher.json` has each client
  draw `canvas:seed`, `audio:seed` and `mediaDevices:seed` fresh per launch
  while the profile persists. Store them with the `user_data_dir`. **Done
  2026-10-03:** `profile_seeds(user_data_dir)` (Go `ProfileSeeds`, Node
  `profileSeeds`) draws them once into `<user_data_dir>/camoucrome-seeds.json`
  (`per_instance_seeds.profile_file`) and reads them back on every later
  launch. A damaged file is an error, never a redraw. The three clients read
  each other's file. `launch()` is unchanged, so the caller opts in. Step 2's
  stability row measures this in a browser.
- `package.py` for Windows, with its Linux refusals, and with the open stamp
  finding closed (`branch_tip` and tree cleanliness never validated).
- Clients published or vendorable, including a fix for the
  `CAMOUCROME_ROOT` requirement on a non-editable Python install.
- At least two distinct Windows device presets, generated end to end.
- README: install, quickstart, one persistent profile per identity, what is
  and is not spoofed, known limits (no Widevine, no auto-update, archive
  size).
- **Windows release as flagship; the existing Linux archive as a labelled
  beta.** The Linux notes say plainly that a Linux host claiming Windows is
  the weaker identity (aliased fonts, software GPU).
- GitHub Release with archives, checksums and the layer 1 and 2 tables for
  that exact build.

Done when: on a clean machine with no build tools, an outsider following only
the README launches two distinct identities within 15 minutes, and layers 1
and 2 reproduce within the stated tolerance.

## Standing commitment: re-pin

From step 0 on, this outranks everything in the backlog.

- **Re-pin is the only security-update channel.** The component updater is
  stopped and there is no auto-update, so a stale release is a liability for
  its users as well as a fingerprint signal.
- **Target: never more than one milestone behind stable.** With a milestone
  every two weeks and a 7.5-hour clean build per platform, "within a week of
  each stable" is not a promise one machine can keep. Patch-level re-pins
  within a milestone are for security fixes only.
- Each release states its Chrome version; releases more than one milestone
  behind are marked unsupported.
- If the step 0 drill shows the target cannot be met, that finding re-ranks
  the backlog (second machine, compiler cache) before anything else.

## Backlog after the first release

Ranked as of 2026-10-02. Re-rank at every release and every milestone; the
step 2 tables, not this list, decide.

**Re-rank from the step 2 tables (2026-10-04).** The numbered items below keep
their numbers, because other documents cite them. The step 2 findings slot in
like this:

- After item 4's open Web Store request, which is traffic, come the new surface items S1–S5.
- Then item 2, which S2 and S3 extend.
- Then the rest of the list.

Evidence for all of them: `measurements/2026-10-step2-baseline.md`.

- **S1. DONE 2026-10-05 (target design, density 0.04; `measurements/2026-10-canvas-noise.md`).** Farbling is visible on a solid fill. A one-colour canvas reads back
  3 distinct colours on the fork and a WebGL clear reads 5, where stock reads
  1. Any page can run this test, so it outranks every other surface item.
- **S2. DONE 2026-10-05 (target design, density 0.04; `measurements/2026-10-canvas-noise.md`).** Canvas noise has little entropy. `canvas.text` stays `9c3103de` in 7
  of 8 seeded launches, and `canvas.shape` repeats one hash for three seeds.
  Two identities share `canvas.text`.
- **S3. Device IDs are empty on the fork after the camera/microphone grant**,
  while stock exposes real IDs. This is a tell, and it leaves `mediaDevices:seed`
  unmeasurable.
- **S4. The fork is unstable across launches.** WebGPU's adapter was missing in
  one of two launches (1 of 3 runs). HEVC's answer flipped (2 of 3 runs). One
  CreepJS run reported "rgba noise". The control never did any of this.
- **S5. No remote voices.** Stock lists 19 remote speech voices; the fork lists
  none. BrowserScan also hits a "WebGL exception" on the fork and counts 95
  fonts against stock's 132. Pixelscan flags "Masking detected" and
  "Timezone spoofed", because the claimed zone does not match the IP. That
  belongs to the proxy layer, but it is worth one run behind a proxy in the
  claimed region.

Item 3 (HEVC) is answered on a host with a GPU: the fork says `probably` like
stock there, and what remains is S4's flip.

1. **Layer 3: commercial anti-bot** (Cloudflare, DataDome, Akamai,
   PerimeterX). Decide the proxy budget first. Design: both arms through the
   same client, interleaved, at least 20 runs per site per arm, a fresh
   profile per run plus a warmed-profile variant, one fixed interaction
   script, and the result as a challenge-rate difference with an interval.
   Pass, challenge or block is not enough: a page can load while the session
   is flagged. Published at vendor level only; the site list stays private.
2. **A different Windows device per profile, in depth.** Whatever step 2's
   linkability table shows is shared between profiles. WebGPU belongs here:
   it must agree with the WebGL claim. **WebGPU adapter identity** is now
   measured as absent: on the GPU-less build box `requestAdapter()` resolves
   to `null` where the Windows host returns an Intel adapter, so
   `verify_host_oracle` excludes the whole `gpu` subtree by prefix and cannot
   see a difference there at all. Measuring it needs a machine with a GPU.
   The Windows host is one, but on 2026-10-04 the oracle still ran with
   `--use-angle=swiftshader`, so the fork's adapter was null there too; the
   measurement is that oracle run without the SwiftShader argv. **Measured by
   step 2 (2026-10-04):** without SwiftShader, the fork reports the host's real
   Intel adapter, equal to stock, and two identities share every `gpu.*` leaf. Also
   measured 2026-10-04: every generated Windows identity claims the **same**
   119-family font list (seeds 1 and 2 identical), so fonts do not yet differ
   per profile.
3. **HEVC claim.** Stock Chrome on the Windows host answers `canPlayType`
   `"probably"` for `hev1.1.6.L93.B0` (it decodes through the OS); the Linux
   build answers `""`. A Windows-claiming browser that cannot play HEVC is a
   tell. Excluded in `verify_host_oracle` with that reason until the claim
   lands; delete the exclusion when it does. Measured on the Windows build
   on 2026-10-04 too: with the proprietary-codec pair it still answers
   `["", false]` where the host answers `["probably", true]`.
4. **Safe Browsing phones home on some startups.** Found by the re-pin: on the
   154 base, `verify_sp7_phonehome` P1 saw `safebrowsing.googleapis.com` once
   in six runs (it was always `{}` on 153). Safe Browsing is not a
   component-updater registrant, so none of the sp7 levers touches it and the
   build has `safe_browsing_mode = 1`. Network-visible to Google. Highest
   priority of the three findings here, because it is traffic and not a
   surface. Same script: a truncated netlog scores P1/P2 FAIL instead of
   "could not measure" — fix that too. **Closed 2026-10-04.**
   - **Not intermittent.** The first list fetch fires on every start, at a
     uniform 60–300 s (`kTimerStartIntervalSecMin/Max`). The 75 s window caught
     it about one start in sixteen.
   - **The lever.** `sp7-phone-home.patch` now defaults
     `prefs::kSafeBrowsingEnabled` to false. That is the "No protection" state a
     user can pick; the owner chose it over two alternatives: stopping only the
     fetch, or a config key.
   - **The verify.** `verify_sp7_phonehome` passes
     `--safebrowsing-fast-initial-lists-update`, so the fetch lands in every
     window.
   - **Results.**
     - Linux: RED on all four runs, GREEN on three at 75 s and one at 330 s.
     - Windows: RED twice and GREEN twice for Safe Browsing. The verify still
       fails there, on the Web Store request below.
   - **The netlog.** It is now read line by line, and an unreadable log scores
     `UNMEASURED`.
   - **P4.** The same work found that P4 had measured nothing on Linux, because
     the profile was passed twice. Fixed through `lib_shell.launch(user_data_dir=)`.

   Evidence: `measurements/2026-10-04-safe-browsing.md`.

   **Opened by the same measurement: `chromewebstore.googleapis.com` on
   Windows.** The Windows build's RED runs showed one request to it in 75 s,
   next to the Safe Browsing fetch. It does not appear on Linux, and the
   Safe Browsing lever does not touch it. The caller is not identified yet.
   This is traffic, so it ranks here, above every surface item.
5. **A crash writes the identity's config and the machine's environment into
   the profile.** Measured on Windows 2026-10-03: any crash of a fork process
   makes crashpad write a minidump (about 190 KB) to
   `<profile>\Crashpad\reports\`, and the dump holds the process's whole
   environment block in UTF-16 — `CAMOU_CONFIG={...}` verbatim, beside every
   host variable. A marker value put in the config was found in the dump; the
   same crash with no config had none. Nothing is uploaded: `GetUploadUrl()` is
   empty unless the build is both branded and official
   (`components/crash/core/app/crash_reporter_client.cc:144-147`). So this is
   local, not traffic — but the config *is* the identity, so every crashed
   profile carries a plain-text record of who it pretended to be next to who
   the machine is, which is the cross-profile link "many identities on one
   machine" must not have. Below item 4 because it is not traffic; above the
   crash-exit item because it applies to every crash, not one flag. **Closed
   2026-10-04 by the C++ lever:** `patches/crashpad-no-dumps.patch` tells the
   crashpad handler never to write a report
   (`set_crashpad_handler_behavior(kDisabled)` in `InitializeCrashpadImpl`).
   The handler still terminates the process with the exception's own code.
   Measured by `verify_crash_dumps.py`, a launch that bypasses the clients:
   - Windows 154: RED 2 FAIL, both dumps holding the marker; GREEN 2 of 2,
     twice; exit code `0x80000003` both times.
   - Linux 154: RED 2 FAIL; GREEN 2 of 2, twice; exit code -6 both times.

   The lever the entry first named, `GetCrashDumpLocation` returning empty,
   would not have worked: `crashpad_win.cc` still starts the handler with an
   empty database, which fails, and crashes then go to Windows Error
   Reporting. **The client lever came first (2026-10-03):** every launch through the Python, Go or
   Node client points `BREAKPAD_DUMP_LOCATION` at a temp directory it removes on
   close, so a kept profile no longer accumulates dumps (measured on Windows,
   RED then GREEN; a renderer dump carries the marker too). The client lever
   left a launch that bypasses the clients, and a client killed before its
   close event; the C++ lever above covers both. Scrubbing `CAMOU_*` from the
   environment after parsing is not a lever: child processes need it, which is
   the whole point of the `windows-sandbox-env` patch. Linux: no Linux dump
   measured so far carried the config. The RED dumps landed in
   `~/.config/chromium/Crash Reports`, which every profile on the host shares.
   With the lever there are none to carry anything.
6. **`chrome.exe` crashes on `--enable-field-trial-config` on Windows.** The
   flag is still refused (the exclusion message prints), but the process then
   exits with `0xC0000005`, an access violation, where Linux exits with code 1.
   Reproduced on five runs; root cause unknown. It matters because a crash is
   itself a fingerprint, and since 2026-10-03 for a second reason: every crash
   writes item 5's dump. Its rank rests on the trigger being an
   operator-supplied command-line flag, not anything page-reachable. The
   question this entry used to end on is answered: the access violation
   produces **no crashpad upload** — the upload URL is empty in this build —
   so it is not traffic, and the rank stands.
7. **Host tells from section D of the completion roadmap**:
   `storage.estimate()`, `keyboard.getLayoutMap()`, `navigator.connection`,
   `getScreenDetails()`, `matchMedia('(display-mode)')`.
8. **A Linux claim on the Windows build keeps `navigator.share`,
   `canShare` and `bluetooth`** (a macOS claim should too; only the Linux
   claim was measured). Measured 2026-10-04: `verify_host_oracle`'s
   Linux-claim sub-run on the Windows fork differs from the host only in the
   UA and platform leaves, so its O2 fails. Cause: the renderer block in
   `windows-oracle.patch` only enables the features for a Windows or macOS
   claim and nothing disables them under a Linux claim; stock Windows Chrome
   ships them on, the Linux build has them off by default. The fix is a
   "Linux claim: disable" branch in that block. Low: a Linux claim on a Windows host is off the
   product path (decision 3). `scripts/windows_verify_set.py` marks O2 as the
   oracle's known-failing row; delete `known_fail` when that branch lands.
9. **Windows CI.** A build and verify job, once the runner is hardened.
10. **Build time**, if the re-pin commitment is at risk.
11. **Linux out of beta.**
12. **Lower value, kept for the record:** `readPixels` on a framebuffer
   object (noise parity only), media device ID reverse map, geolocation
   permission order, the Android claim with a coarse pointer and zero touch
   points (a coherence defect, cheap, not on the Windows path).

`screenX` and `measureText` are recorded design trade-offs in the 2026-09-24
triage, not gaps. Slice residuals in the follow-on roadmap keep their
recorded dispositions and harness gates.

Things layer 3 may surface that no browser fork controls (IP reputation,
behavioural scoring) are recorded as out of scope with a reason, not left
unexplained.

## Risks

| Risk | Effect | Response |
|---|---|---|
| Re-pin falls behind | The claimed version becomes rare, and users run unpatched Chromium | Standing commitment; outranks the backlog |
| The build machine is lost | No builds, no CI, no branch | Step 0 recovery drill; `rebuild_branch.sh` fixed |
| Public repo, self-hosted runner on the build machine | A workflow change could run code on it | Step 0 hardening; existing approval policy and action allow-list |
| Profiles on one host are linkable | The product's main use case fails quietly | Step 2 linkability table; backlog item 2 |
| A check measures nothing on Windows | Green results with no information | RED-first for every script in the Windows verify set |
| Publishing against named sites | Terms-of-service and takedown exposure | Layer 3 at vendor level only (no acceptable-use statement, decided 2026-10-04) |
| Shipping proprietary codecs unlicensed | Legal exposure | Release gate in step 3 |
| Detection vendors change | A passing table decays | Tables re-run at every release |

## Out of scope

- A macOS build, an Android build.
- A desktop-app experience: installer, auto-update, sync, sign-in.
- Community infrastructure: contributor guides, hosted CI.
- Proxy, IP rotation or CAPTCHA solving. The fork is the browser only.
