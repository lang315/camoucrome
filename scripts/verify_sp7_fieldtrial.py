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
