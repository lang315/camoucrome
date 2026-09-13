# CI on the build box — `build-verify` on a self-hosted runner

2026-09-13. Decision: GitHub-hosted runners cannot build Chromium (4 vCPU,
16 GB, ~14 GB disk, 6 h cap; a `--no-history` checkout alone is ~40 GB and
a 4-core release build ~20–30 h). Larger hosted runners could, at tens to
hundreds of dollars per clean build. The build already lives on the user's
PC, so the PC becomes the runner: GitHub orchestrates, the box builds.

## 1. The runner

- `~/actions-runner` in WSL2 Ubuntu 24.04 on the build PC: actions/runner
  v2.337.0, registered to `lang315/camoucrome` as **`buildpc-wsl`** (label
  `buildpc-wsl`), installed as a systemd service (`svc.sh install lang`,
  WSL has `systemd=true`), `Active: active (running)`.
- WSL stops its VM when no Windows-side process holds it, and systemd units
  do not count. A Windows scheduled task **`CamouWslKeepAlive`** (trigger:
  at logon, restart on failure, no time limit) runs `wsl.exe -d Ubuntu-24.04
  -u lang -- sleep infinity`, so the distro and the runner service stay up
  while the user is logged on. Registered and `Running`.
- The runner's PATH carries `/home/lang/depot_tools`; the job still exports
  it explicitly.

## 2. The workflow (`.github/workflows/build-verify.yml`)

`runs-on: [self-hosted, buildpc-wsl]`, on push to `main` touching
`patches/`, `additions/`, `settings/`, `scripts/`, `client/`, `upstream.env`
or the workflow, and on `workflow_dispatch`; `concurrency: buildpc`, 180 min
cap. It never edits `~/chromium/src`:

1. **Gate.** The checkout must be on `camoucrome/main`, `git status
   --porcelain` empty (otherwise "checkout dirty: a slice is in progress,
   re-run later" and the job fails fast), and no `ninja -C out/...` may be
   running (a manual build is never raced).
2. `check_checkout_sync.sh`: the pushed change set is byte-identical to the
   built checkout (39 files).
3. Pre-flight: `check_additions_build.py`, `gen_keys.py --check`,
   `gen_fontconfig.py --check`.
4. Sync the client tree the verifies import (`~/camoucrome-client`,
   `~/camoucrome-verify`), `pip install -e` the Python client.
5. `autoninja -C out/Default chrome content_shell components_unittests`;
   the step fails unless ninja prints `Build Succeeded` (step count in the
   log — a 0-step build is visible).
6. Every camoucfg unit suite by name (the per-process coherence suite
   through `run_coherence_tests.sh`).
7. Client tests (pytest, `go test`).
8. Browser verifies against `out/Default/chrome`: sp1a, voices, fonts
   bundle, host oracle (4 rows), windows-behaviour (14 rows), generator
   N=2. Each verify's full log is uploaded as an artifact.

The cheap `checks` workflow stays on `ubuntu-latest`.

## 3. First runs, and what the runner found

- Run 1 (`2420508`): the gate passed, `check_checkout_sync.sh` failed — it
  was written to cross the ssh link from the Mac; it now takes `local` (or
  detects `$SRC/.git` beside it) and hashes in place, with a `sha256sum`
  fallback for `shasum`.
- Run 2 (`2805c44`): gate, sync (39), pre-flight, build (`Build Succeeded:
  1 steps` — the checkout was already built), 21 camoucfg suites SUCCESS,
  coherence 7/7, client tests 40 + `go test` ok, sp1a, voices 5/5, fonts
  17/17 — then **`verify_host_oracle.py` 3/4: `DIFF audio.sampleRate:
  host=48000 fork=44100`** with `audio:sampleRate` set. The runner runs
  under systemd with no PulseAudio session, so the audio manager reports
  *invalid* output parameters, the hook (which only rewrote valid ones) did
  nothing, and Blink fell back to its own 44100 default. That is exactly a
  headless deployment box. Reproduced by hand with `env -u PULSE_SERVER -u
  XDG_RUNTIME_DIR -u DISPLAY -u WAYLAND_DISPLAY`: 44100 / 441 frames even
  with the keys — the audio service's helper returns *no* parameters when
  `HasAudioOutputDevices()` is false (before the manager hook is reached),
  and the renderer falls back to `AudioParameters::UnavailableDeviceParams()`
  (44100, 10 ms). Fix in `windows-behaviour-ii`: that fallback now takes the
  claimed rate and quantum too (`media/base/audio_parameters.cc`, fake sink
  unchanged), so a claimed host reads the same with or without a device.
  A first attempt that synthesized parameters inside the manager hook was
  dead code (never reached) and was removed. Measured by the runner, not by
  hand.
- The verify step now runs every verify and reports all failures, not the
  first.
