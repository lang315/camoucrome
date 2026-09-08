# A concurrent process splits a LOG line in the shared stderr capture (verify-harness flake)

**Date:** 2026-09-08
**Component:** `scripts/lib_shell.py` — `launch()`'s stderr capture, shared by
every verify script that asserts on a `LOG(ERROR)` substring (sp5a, pairing,
navplatform-bucket, ua-halfconfig, webgl-capability-identity).
**Symptom:** an intermittent (~1 launch in 100) miss where an expected
`ValidateAtStartup` diagnostic line is absent from the captured stderr even
though the browser emitted it. First disclosed as "undiagnosed" in
`2026-09-08-webgl-capability-identity-presence.md`; diagnosed and fixed here.

## Reproduction

The flake needs the multi-launch *sequence*, not a single config: 50 sequential
launches of one config were clean, but the faithful 16-row sequence caught it in
128 launches (`WEBGL2-SHADERPREC`, `LINE-ABSENT`, stderr len 668 vs median 1707).
Earlier belief that it was pinned to `shaderPrecisionFormats` was observation
bias — the committed `CP-WEBGL2` (parameters) row also missed historically.

## Root cause (read from the captured bytes, not inferred)

The missed launch's stderr showed the diagnostic line **split mid-string**:

```
[...:ERROR:coherence_validator.cc:359] camoucfg: libEGL warning: failed to get driver name for fd -1
libEGL warning: MESA-LOADER: failed to retrieve device information
...
y -- an incoherent profile. Set the identity strings ...
```

`camoucfg: ` then interleaved `libEGL warning:` lines then the tail
`y -- an incoherent profile` — the middle of the line (the exact substring the
assertion matches) was **overwritten**. Passing captures (479–491 bytes) carry
no libEGL noise; the failing one does.

`launch()` opened the per-PID stderr file `open(STDERR_LOG, "wb")` — `O_TRUNC`,
no `O_APPEND`. content_shell is multi-process, and in WSL its GPU process spams
libEGL warnings as EGL init fails (no real GPU). A libEGL write landing *inside*
the browser's coherence line means the two writers held offsets that were not
serialized against each other — a shared open-file description would serialize
on Linux (`f_pos_lock`), so at least one writer reached this file through a
separate description. Which process held it and how it got a separate offset was
**not resolved**, and `O_APPEND` does not need that answer: it makes every
write() seek to EOF atomically regardless of offset, so no write can land inside
another. It is a timing race, hence intermittent, and it belongs to the
*capture*, not the check (the check path — config → `FindDict` → violation →
`LOG` — is deterministic; `ValidateAtStartup` runs in `BrowserMainLoop::Init()`
before the DevTools port opens, so the line is always emitted before `launch()`
returns).

## Fix

`O_APPEND`: truncate first (`"wb"` then close, for the per-run-fresh property),
then reopen `"ab"`. Every write() then seeks to EOF atomically, so each whole
log line stays contiguous no matter which process is also writing. Argv-neutral
— `Popen`'s command line is untouched, so `test_lib_shell_launch.py` stays 7/7.
The change is in the shared harness, so it hardens every verify script at once,
not just the one where it surfaced.

## Verification (box, 2026-09-08)

- **Pre-fix rate:** 1 `LINE-ABSENT` in 128 sequenced launches.
- **Post-fix:** 0 misses in 420 sequenced launches (two 210-launch chunks).
  These excluded the GL `MOTIVATION` row, which exhausts the WSLg display under
  rapid repeat (see below), so the stress was headless-only — while every
  pre-fix observation had the GL row present. GL-inclusive post-fix exposure is
  therefore the real-script reruns below: ~92 launches (5×13 + 3×9) with 0
  `LINE-ABSENT`, the only failures being the unrelated X11 abort. The libEGL
  writer that did the splitting is present in every headless launch too (the GPU
  process fails EGL regardless of the GL flags), so the headless stress does
  exercise the race.
- **Corroboration:** the minimum captured stderr length rose 479 → 754 → 1593
  across post-fix runs — with no write landing inside another, the interleaved
  content is preserved rather than clobbered, exactly as `O_APPEND` predicts; the
  diagnostic line was present in every capture.
- **Argv-freeze:** `python3 scripts/test_lib_shell_launch.py` 7/7 (command line
  unchanged).
- **Real scripts on the fixed harness:** `verify_webgl_capability_identity.py`
  13/13, `verify_webgl_pairing.py` 9/9, `verify_sp5a.py` 6/6.

## Not this bug (recorded so it is not re-chased)

- **`CP-MOTIVATION` / `WP-MOTIVATION` SIGABRT (code -6):** a separate,
  X11/Ozone `DeviceDataManagerX11` abort (the stack is pure X11 init), appearing
  after *rapid repeated* GL launches (the stress loop) — those rows drop
  `--ozone-platform=headless` because GL flags replace `SHELL_FLAGS`, so they
  need the real WSLg display. The recovery was NOT from reaping: with the
  process table fully reaped (0 content_shell) the rows still failed 12/13, 8/9;
  they cleared on their own a few minutes later, trigger unresolved, and the
  abort's `CHECK`/`FATAL` message was never captured (the crash dump was gone and
  the later probe succeeded). Unrelated to the stderr change — MOTIVATION
  succeeded with the `O_APPEND` harness in place once the display recovered. A
  normal verify run does one spaced MOTIVATION launch and passes; the prior for
  a future recurrence is "WSLg display state — wait it out or restart WSLg," not
  "reap processes."
- The three per-field webGl2 rows stay dropped: their reason to exist was
  structural redundancy insurance (the `Cap[]` loop keys all four fields off one
  `is_webgl2`, and `CP-WEBGL2` covers the `is_webgl2=true` wiring), which stands
  on its own now that the flake that first justified dropping them is fixed.
