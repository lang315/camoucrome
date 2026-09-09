# SP7 field-trial testing config Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compile `testing/variations/fieldtrial_testing_config.json` out of the fork's binaries so its feature state stops sitting at a third position that matches neither seeded nor default Chrome.

**Architecture:** One GN arg (`disable_fieldtrial_testing_config = true`, `components/variations/service/BUILD.gn`) flips `FIELDTRIAL_TESTING_ENABLED` to 0, which removes `ApplyFieldTrialTestingConfig` from `variations_field_trial_creator.cc` for both `content_shell` and `chrome`. Persist the arg in `settings/build-args.gn` next to the codec pair; verify RED→GREEN on `content_shell` through the stderr `VLOG(1)` line and the `--enable-field-trial-config` hard exit. No patch, no addition, no key.

**Tech Stack:** GN args, `scripts/lib_shell.py` (CDP over Playwright), stderr capture; build on the WSL box (`ssh buildpc` → `runwsl`, siso).

**Measurement basis:** `docs/superpowers/measurements/2026-09-09-sp7-fieldtrial-config.md` — read it first. Its source lines were read from Chromium `main`; Task 0 re-confirms them at the pin.

## Global Constraints

- All spoofing stays C++/build-level; this slice injects nothing and adds no page-visible property.
- SP0 hook pattern is N/A (no config key) — rule 5 fallback untouched.
- RED-first: `verify_sp7_fieldtrial.py` must FAIL on the current `out/Default/content_shell` before the rebuild and PASS after; assert the expected COUNT (F1) and the expected FAILURE (F2), never exit 0.
- Confirm the rebuild reports NON-ZERO steps and that the recompiled objects include `variations_field_trial_creator.o`.
- Every `verify_*.py` runs under `~/camoucrome-verify/venv/bin/python3` on the box; `extra_flags` REPLACES `lib_shell.SHELL_FLAGS`, so `--ozone-platform=headless` must be repeated whenever flags are passed.
- Commits are local; the user drives pushes. Secret-scan the diff (no Tailscale IPs, no passwords) before every commit.
- Box routing: `/usr/bin/ssh buildpc` lands in PowerShell; use the session harness `runwsl '<bash>'` / `pushfile <local> <remote-abs>` from `wsl-build-server.md`. If the SSH master is down, ask the user to re-establish it — never retry password auth yourself.

---

### Task 0: Gate 0 — confirm the source facts at the pin

**Files:**
- Read (on the box, `~/chromium/src` at `a727b57805`): `components/variations/service/BUILD.gn`, `components/variations/service/variations_field_trial_creator.cc`, `content/test/setup_field_trials.cc`, `content/shell/browser/shell_content_browser_client.cc`, `out/Default/args.gn`
- Modify: `docs/superpowers/measurements/2026-09-09-sp7-fieldtrial-config.md` (replace the "read from main" caveat with pin line numbers)

**Interfaces:**
- Produces: confirmed line numbers for §2–§3 of the measurement; the current `args.gn` contents (Task 2 appends to it).

- [x] **Step 1: Confirm the GN arg and the buildflag exist at the pin**

Run (via `runwsl`):
```bash
cd ~/chromium/src && git rev-parse --short HEAD && \
grep -n 'disable_fieldtrial_testing_config\|FIELDTRIAL_TESTING_ENABLED' components/variations/service/BUILD.gn
```
Expected: `a727b57805`, then hits for `disable_fieldtrial_testing_config = false` and `FIELDTRIAL_TESTING_ENABLED=$fieldtrial_testing_enabled`. If the arg is absent at the pin, STOP: the lever does not exist at this revision and the slice needs the switch as fallback (record it in the measurement §2 and re-plan).

- [x] **Step 2: Confirm the three code sites**

Run:
```bash
cd ~/chromium/src && \
grep -n 'Applying FieldTrialTestingConfig\|ShouldUseFieldTrialTestingConfig\|excluded from the build\|BUILDFLAG(FIELDTRIAL_TESTING_ENABLED)' components/variations/service/variations_field_trial_creator.cc && \
grep -n 'fieldtrial_testing_config\|SetUpFieldTrials\|VariationsFieldTrialCreator field_trial_creator' content/test/setup_field_trials.cc && \
grep -n 'SetupFieldTrials\|CreateFeatureListAndFieldTrials' content/shell/browser/shell_content_browser_client.cc content/shell/app/shell_main_delegate.cc
```
Expected: one hit for each string. If `content/test/setup_field_trials.cc` does not exist at the pin, find the caller with `grep -rn 'SetupFieldTrials()' content/shell content/test` — the plan needs the file that calls `SetUpFieldTrials` for `content_shell`, whatever it is named.

- [x] **Step 2b: Confirm the three facts F2 and §4 of the measurement rest on**

Run:
```bash
cd ~/chromium/src && \
grep -n 'ExitWithMessage' content/test/setup_field_trials.cc components/variations/service/variations_service_client.h && \
grep -rn 'VariationsService(' content/shell | grep -v RegisterPrefs ; \
grep -n 'setup_field_trials' content/shell/BUILD.gn content/test/BUILD.gn content/public/test/BUILD.gn
```
Expected, and what each decides:
- `ExitWithMessage`: the content_shell client inherits the base `VariationsServiceClient::ExitWithMessage` (`variations_service_client.cc:97-100`), which is `puts(message); exit(1);` — stdout, which `launch()` discards. F2 therefore asserts `exited during startup, code 1` and never the message text (confirmed at the pin 2026-09-09; the script already encodes this).
- `VariationsService(` in `content/shell`: expected NO constructor call (the measurement §4 claims content_shell never constructs one). A hit means the seed-fetch path IS reachable in content_shell — extend the verify with a fetch-off assertion and correct §4.
- `setup_field_trials` in a target that `content_shell` links: expected a hit in `content/test/BUILD.gn` or `content/public/test/BUILD.gn` reachable from `//content/shell:content_shell_lib`. Confirm with `gn refs out/Default //content/test:<target> | grep content_shell` if the BUILD.gn read is ambiguous. The file lives under a test path; a header include is not proof it is compiled into the shell.

- [x] **Step 3: Record the current `args.gn` and confirm the arg is not already set**

Run:
```bash
cd ~/chromium/src && cat out/Default/args.gn && \
gn args out/Default --list=disable_fieldtrial_testing_config --short
```
Expected: `args.gn` shows the codec pair and dev conveniences; `disable_fieldtrial_testing_config = false`. If it already reads `true`, the RED in Task 1 cannot happen — STOP and investigate who set it.

- [x] **Step 4: Update the measurement doc with pin line numbers**

Edit `docs/superpowers/measurements/2026-09-09-sp7-fieldtrial-config.md`: replace the bold caveat paragraph at the top with `Source lines confirmed at the pin a727b57805 on <date>: ...` and correct any line number that moved. Keep the `main` numbers only if identical.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/measurements/2026-09-09-sp7-fieldtrial-config.md
git commit -m "docs(sp7): confirm field-trial testing-config source sites at the pin"
```

---

### Task 1: `verify_sp7_fieldtrial.py` — RED on the current binary

**Files:**
- Create: `scripts/verify_sp7_fieldtrial.py`
- Read: `scripts/lib_shell.py:47,52,87-236,270-290` (STDERR_LOG, SHELL_FLAGS, launch, session), `scripts/verify_navplatform_bucket.py` (`read_stderr` helper pattern)

**Interfaces:**
- Consumes: `lib_shell.launch(config, extra_flags=..., ...)` → `proc` with `.cdp_port`, raises `RuntimeError("... exited during startup, code N")`; `lib_shell.shutdown(proc)`; `lib_shell.session(config, [js...])` → `(values, error)`; `lib_shell.STDERR_LOG` — per-launch truncated stderr file.
- Produces: a script printing `F1..F4: PASS|FAIL` lines and exiting non-zero on any FAIL. Task 2 reruns it unchanged.

- [x] **Step 1: Write the verify script**

```python
"""SP7 field-trial testing config verify: disable_fieldtrial_testing_config=true.

F1 the testing config is NOT applied at startup (VLOG line count == 0; RED: 1).
F2 --enable-field-trial-config is a hard exit, code 1 (RED: starts). The
   exclusion message itself is not asserted: VariationsServiceClient::
   ExitWithMessage is puts()+exit(1) -- it goes to STDOUT, which launch()
   sends to DEVNULL -- so the exit code is the observable, not the text.
F3 control: the fork's config layer still works (hardwareConcurrency override).
F4 probe capability: the stderr capture of the F1 launch carries a line that
   is present in every build, so F1's absence claim is not an empty file.

Measurement: docs/superpowers/measurements/2026-09-09-sp7-fieldtrial-config.md
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell

APPLY_LINE = "Applying FieldTrialTestingConfig"
PRESENT_LINE = "DevTools listening on"
VLOG_EXTRA = ["--enable-logging=stderr", "--v=0",
              "--vmodule=variations_field_trial_creator=1"]

results = {}
notes = []


def read_stderr():
    """Guarded read of this session's browser stderr (verify_sp5a.py's helper).
    launch() truncates the log per launch, so a read sees only its own run."""
    try:
        with open(lib_shell.STDERR_LOG, "rb") as handle:
            return handle.read().decode("utf-8", "replace"), None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, exc


def run_f1_f4(shell=None, base_flags=None, k1="F1", k4="F4"):
    flags = [*(base_flags or lib_shell.SHELL_FLAGS), *VLOG_EXTRA]
    proc = None
    try:
        proc = lib_shell.launch(None, shell=shell, extra_flags=flags)
    except Exception as exc:  # noqa: BLE001
        results[k1] = results[k4] = False
        notes.append(f"{k1}/{k4} launch: {type(exc).__name__}: {exc}")
        return
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)
    stderr, err = read_stderr()
    if err is not None:
        results[k1] = results[k4] = False
        notes.append(f"{k1}/{k4} stderr: {type(err).__name__}: {err}")
        return
    count = stderr.count(APPLY_LINE)
    results[k4] = PRESENT_LINE in stderr
    if not results[k4]:
        notes.append(f"{k4}: stderr capture lacks the always-present line; "
                     f"{k1}'s count is not evidence")
    results[k1] = results[k4] and count == 0
    notes.append(f"{k1}: '{APPLY_LINE}' count = {count} (expect 0; RED build 1)")


def run_f2(shell=None, base_flags=None, k2="F2"):
    flags = [*(base_flags or lib_shell.SHELL_FLAGS), *VLOG_EXTRA,
             "--enable-field-trial-config"]
    proc = None
    try:
        proc = lib_shell.launch(None, shell=shell, extra_flags=flags)
    except RuntimeError as exc:
        # launch() formats "<name> exited during startup, code N". The
        # exclusion message itself went to stdout (DEVNULL); the exit is the
        # observable, and code 1 is what ExitWithMessage's exit(1) produces --
        # a crash (SIGABRT, -6) or a sandbox refusal would carry another code.
        exited = "exited during startup" in str(exc)
        code_1 = str(exc).rstrip().endswith("code 1")
        results[k2] = exited and code_1
        notes.append(f"{k2}: {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        results[k2] = False
        notes.append(f"{k2} launch: {type(exc).__name__}: {exc}")
        return
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)
    results[k2] = False
    notes.append(f"{k2}: browser started normally with "
                 "--enable-field-trial-config (RED build behaviour)")


def run_f3():
    vals, err = lib_shell.session(
        json.dumps({"navigator.hardwareConcurrency": 8}),
        ["navigator.hardwareConcurrency"])
    if err is not None:
        results["F3"] = False
        notes.append(f"F3: {type(err).__name__}: {err}")
        return
    results["F3"] = vals[0] == 8
    notes.append(f"F3: hardwareConcurrency = {vals[0]} (expect 8)")


def main():
    run_f1_f4()
    run_f2()
    run_f3()
    keys = ["F1", "F2", "F3", "F4"]
    # The same buildflag governs the chrome target (ChromeFeatureListCreator
    # -> the same VariationsFieldTrialCreator). When a chrome binary exists in
    # out/Default, run the two structural rows against it too; when it does
    # not, say so rather than reporting a PASS for a binary that was never run.
    if os.path.exists(lib_shell.CHROME):
        run_f1_f4(shell=lib_shell.CHROME, base_flags=lib_shell.CHROME_FLAGS,
                  k1="C1", k4="C4")
        run_f2(shell=lib_shell.CHROME, base_flags=lib_shell.CHROME_FLAGS,
               k2="C2")
        keys += ["C1", "C2", "C4"]
    else:
        notes.append("C1/C2/C4: SKIPPED -- no out/Default/chrome binary")
    for n in notes:
        print("note:", n)
    ok = True
    for k in keys:
        print(f"{k}: {'PASS' if results.get(k) else 'FAIL'}")
        ok = ok and bool(results.get(k))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
```

- [x] **Step 2: Push the script to the box and run it against the CURRENT binary (RED)**

Run:
```bash
pushfile scripts/verify_sp7_fieldtrial.py /home/lang/camoucrome-verify/verify_sp7_fieldtrial.py
runwsl 'cd ~/camoucrome-verify && venv/bin/python3 verify_sp7_fieldtrial.py; echo EXIT=$?'
```
Expected (RED):
```
note: F1: 'Applying FieldTrialTestingConfig' count = 1 (expect 0; RED build 1)
note: F2: browser started normally with --enable-field-trial-config (RED build behaviour)
note: F3: hardwareConcurrency = 8 (expect 8)
F1: FAIL
F2: FAIL
F3: PASS
F4: PASS
EXIT=1
```
If F1's count is 0 on the current build, the VLOG is not reaching stderr (wrong `--vmodule` module name, or `--enable-logging` form) — fix the flags until the RED shows count 1; a verify that cannot go red measures nothing. If F4 fails, find a line that IS always present in this build's stderr and substitute it.

- [ ] **Step 3: Commit the RED verify**

```bash
git add scripts/verify_sp7_fieldtrial.py
git commit -m "test(sp7): RED verify for the field-trial testing config (F1 count, F2 hard exit)"
```

---

### Task 2: Set the GN arg, rebuild, GREEN

**Files:**
- Modify (on the box): `~/chromium/src/out/Default/args.gn`
- Modify: `settings/build-args.gn`

**Interfaces:**
- Consumes: Task 1's script unchanged.
- Produces: `out/Default/content_shell` with `FIELDTRIAL_TESTING_ENABLED=0`; `settings/build-args.gn` carrying the arg for SP6.

- [x] **Step 1: Append the arg to the box's `args.gn` and regenerate**

Run:
```bash
runwsl 'cd ~/chromium/src && printf "\n# SP7: compile out fieldtrial_testing_config (verify_sp7_fieldtrial.py)\ndisable_fieldtrial_testing_config = true\n" >> out/Default/args.gn && gn gen out/Default && gn args out/Default --list=disable_fieldtrial_testing_config --short'
```
Expected: `Done. Made N targets ...` then `disable_fieldtrial_testing_config = true`.

- [x] **Step 2: Rebuild `content_shell` and confirm non-zero steps touching the creator**

Run (background if it exceeds the 10-minute Bash cap, as the codec rebuild did):
```bash
runwsl 'cd ~/chromium/src && autoninja -C out/Default content_shell 2>&1 | tail -5'
```
Expected: a non-zero step count; NOT `0 steps` / `no work to do`. Then:
```bash
runwsl 'cd ~/chromium/src && ls -la --time-style=+%H:%M out/Default/obj/components/variations/service/service/variations_field_trial_creator.o out/Default/content_shell | cat'
```
Expected: both timestamps within the rebuild window. If the `.o` timestamp is old, the buildflag header did not change — check `gn gen` actually rewrote `out/Default/gen/components/variations/service/buildflags.h` (`grep FIELDTRIAL_TESTING_ENABLED` should show `(0)`).

- [x] **Step 3: Rerun the verify (GREEN)**

Run:
```bash
runwsl 'cd ~/camoucrome-verify && venv/bin/python3 verify_sp7_fieldtrial.py; echo EXIT=$?'
```
Expected:
```
note: F1: 'Applying FieldTrialTestingConfig' count = 0 (expect 0; RED build 1)
note: F2: content_shell exited during startup, code 1
note: F3: hardwareConcurrency = 8 (expect 8)
F1: PASS
F2: PASS
F3: PASS
F4: PASS
EXIT=0
```

- [x] **Step 4: Regression sweep**

This change flips the defaults of ~700 features on Linux; the verify suite is the only regression surface the project has and each script runs in seconds to a minute, so run ALL of them, not a sample. First push every `scripts/verify_*.py` that is newer on the Mac than on the box (one `pushfile` per file), then:
```bash
runwsl 'cd ~/camoucrome-verify && for s in verify_*.py; do echo "== $s"; venv/bin/python3 $s 2>&1 | grep -E "^[A-Z][A-Z0-9-]*: (PASS|FAIL)$" | sort | uniq -c | awk "{print \$1, \$3}" | tr "\n" " "; echo; done'
```
Expected: for every script the PASS count equals its last recorded run in `.superpowers/sdd/progress.md` and the FAIL count is 0 (scripts whose ledger entry records a known harness-gated FAIL, e.g. a `chrome`-only row, keep exactly that count). A feature that the testing config had been enabling may change a Blink default; any new FAIL here is the slice's finding, not flake — record it in the measurement §8 before deciding whether the arg stays.

- [x] **Step 5: Persist the arg in `settings/build-args.gn`**

Append after the Widevine section:
```gn

# --- SP7: field-trial testing config (SP7 §4.2 / D3, resolved 2026-08-27) ---
# An unbranded build applies testing/variations/fieldtrial_testing_config.json at
# startup; real Chrome does not. That puts the fork's feature state at a third
# position matching neither seeded nor default Chrome, and the testing config is
# a public per-milestone file. Compile it out (FIELDTRIAL_TESTING_ENABLED=0) so
# the position is a property of the binary, not of whether a driver remembered
# --disable-field-trial-config. content_shell applies the config too
# (content/test/setup_field_trials.cc), so this is verified on the dev target:
# scripts/verify_sp7_fieldtrial.py (F1 VLOG count 0, F2 hard exit on
# --enable-field-trial-config). The seed fetch needs no arg: IsFetchingEnabled()
# is false in a non-branded build unless --variations-server-url is passed --
# a driver must never pass it.
disable_fieldtrial_testing_config = true
```

- [ ] **Step 6: Commit**

```bash
git add settings/build-args.gn
git commit -m "feat(sp7): compile out the field-trial testing config (disable_fieldtrial_testing_config=true)"
```

---

### Task 3: Record the result

**Files:**
- Modify: `docs/superpowers/measurements/2026-09-09-sp7-fieldtrial-config.md` (§8 Result)
- Modify: `docs/superpowers/plans/2026-09-09-completion-roadmap.md` (A1 item 1 → shipped; A1 item 2 → measured-off)
- Modify: `README.md` (one sentence in the "Shipped" paragraph after the codec build)
- Modify: `.superpowers/sdd/progress.md` (append the slice entry in the established style)

- [x] **Step 1: Fill §8 of the measurement**

Write: RED output verbatim (F1 count 1, F2 started), the rebuild step count and the `.o` timestamp, GREEN output verbatim, the regression-sweep result, and the commit hashes. Note explicitly that the `chrome` target is covered by the same buildflag but was not built here (B1).

- [x] **Step 2: Update the roadmap and README**

In the completion roadmap A1: item 1 becomes `**SHIPPED <date>** (<hash>, settings/build-args.gn, verify_sp7_fieldtrial.py)`; item 2 becomes `**measured-off** — IsFetchingEnabled() is false unbranded; driver must never pass --variations-server-url; re-verify on chrome under B1`. In README's shipped paragraph add: "SP7 also compiles out the field-trial testing config, so feature state is the build's defaults rather than the public per-milestone testing set."

- [ ] **Step 3: Ledger entry and commit**

Append to `.superpowers/sdd/progress.md` one paragraph: slice name, the GN lever with file:line, RED/GREEN counts, regression sweep, the `chrome`-target residual, and the driver constraint. Then:
```bash
git add docs/superpowers/measurements/2026-09-09-sp7-fieldtrial-config.md docs/superpowers/plans/2026-09-09-completion-roadmap.md README.md .superpowers/sdd/progress.md
git commit -m "docs(sp7): record the field-trial testing-config slice"
```
Present for push; do not push.

**Executed 2026-09-09 (deviations from the plan as written):** the sweep found `verify_sp1a.py` criterion 7 red; attributed by a control rebuild (arg false/true) and by reading the tree, baseline recaptured with provenance (measurement §8). The verify grew C1/C2/C4 rows that run the same two structural checks against `out/Default/chrome` when it exists; `chrome` was rebuilt with the arg and is 7/7. Commits await the user's go.

---

## Self-review

- Spec coverage: measurement §2 lever → Task 2; §3 content_shell applicability → Task 0 Step 2 + Task 1 RED; §4 seed fetch → recorded in build-args comment and roadmap (Task 2 Step 5, Task 3 Step 2), verification deferred to B1 by design; §5 F1–F4 → Task 1 script; §6 persistence → Task 2 Step 5.
- Placeholders: none; every code step carries its content.
- Names: `verify_sp7_fieldtrial.py`, `APPLY_LINE`, `EXIT_LINE`, `PRESENT_LINE`, `VLOG_FLAGS` used consistently; `lib_shell.launch/shutdown/session/STDERR_LOG/SHELL_FLAGS` match `scripts/lib_shell.py`.
