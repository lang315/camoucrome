"""Windows: a renderer-consumed key under the REAL sandbox.

This is the first verification that can see the project's only Windows-specific
bug, and the reason it is a separate script is that every other one is blind to
it. Windows launches renderers and utilities with `SetFilterEnvironment(true)`;
`CreateFilteredEnvironment()` (`sandbox/win/src/broker_services.cc`) passes only
Path, SystemDrive, SystemRoot, TEMP, TMP, LOCALAPPDATA and
CHROME_CRASHPAD_PIPE_NAME. Every `CAMOU_*` variable was dropped, so every
renderer-side spoof fell back to the real value, and
`measurements/2026-09-24-review-triage.md:183` records the shape exactly:
`navigator.hardwareConcurrency` read the real 16 under the default sandbox and
the spoofed 3 under `--no-sandbox`. Linux has no such filter, so no WSL run can
reproduce it. The fix is the `windows-sandbox-env` patch.

`lib_shell.launch()` passed `--no-sandbox` unconditionally until this script
needed it not to, which means the fix shipped in September and was never
re-measured by anything committed. W1 is that measurement.

W2 is W1's control and the reason W1 is not a test that measures nothing: the
same sandboxed launch with no config at all must report the machine's real core
count. If W1's spoofed value were coming from anywhere but the config -- a
hardcoded default, a stale profile, a value this script supplied -- W2 would
report it too.

W3 is the `--no-sandbox` path, which is what every other verification exercises;
it fails only if the config layer itself is broken, which tells you W1's failure
is about the sandbox rather than about configuration.

A1 and A2 are the audio service, the one other process type that reads the
config (media/audio/audio_manager_base.cc, windows-behaviour-ii): on Windows it
runs in a sandboxed utility process, so the same filter could strip
audio:sampleRate there. A1: under {"audio:sampleRate": 22050} a sandboxed
launch's AudioContext reports 22050. A2: with no config it reports anything
else, the device's own rate, so A1 cannot pass on a default.

Run on the Windows host, in the directory holding lib_shell.py:
  $env:CAMOU_OUT='D:\\camou-win\\chromium\\src\\out\\Release'
  <venv>\\Scripts\\python.exe verify_windows_sandbox_env.py

RED, seen 2026-10-03: with CAMOU_OUT pointing at a directory holding no binary,
every row fails and the script exits 1.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_shell  # noqa: E402

SPOOFED = 3
CONFIG = json.dumps({"navigator.hardwareConcurrency": SPOOFED})
HC = "navigator.hardwareConcurrency"
# The same blob-worker probe verify_sp0.py:9-16 uses, copied rather than imported
# because importing that module would execute its browser work. Conventions rule 3
# is why the worker rows exist at all: a surface exposed to both a window and a
# worker must report identical values in both, and on Windows the two live in
# different processes, so the environment filter could plausibly reach one and not
# the other.
WORKER_HC = """
() => new Promise(resolve => {
  const src = 'self.postMessage(navigator.hardwareConcurrency)';
  const url = URL.createObjectURL(new Blob([src], {type: 'text/javascript'}));
  const w = new Worker(url);
  w.onmessage = e => resolve(e.data);
})
"""
EXPECTED = 7  # W1-W5, A1, A2

results = {}
notes = []
main_cfg = worker_cfg = real = worker_real = None


def read(config, sandbox):
    """(main-thread value, worker value, error) from ONE launch.

    Both expressions go through a single session so the two values come from the
    same process tree; two launches could differ for a reason that has nothing to
    do with worker parity.
    """
    values, err = lib_shell.session(config, [HC, WORKER_HC],
                                    shell=lib_shell.CHROME,
                                    extra_flags=lib_shell.CHROME_FLAGS,
                                    sandbox=sandbox)
    if err is not None:
        return None, None, f"{type(err).__name__}: {err}"
    return values[0], values[1], None


# W1. The measurement. A sandboxed renderer must see the configured value, which
#     it can only do if CAMOU_CONFIG survived CreateFilteredEnvironment().
main_cfg, worker_cfg, err = read(CONFIG, True)
results["W1"] = main_cfg == SPOOFED
notes.append(f"W1: sandboxed + config, main -> {main_cfg!r} (expect {SPOOFED})"
             f"{'; ' + err if err else ''}")

# W2. The control. Same launch, no config: this must be the machine's real core
#     count, and it must NOT be SPOOFED, or W1 proves nothing.
real, worker_real, err = read(None, True)
results["W2"] = real is not None and real != SPOOFED
notes.append(f"W2: sandboxed, no config, main -> {real!r} "
             f"(expect anything but {SPOOFED}){'; ' + err if err else ''}")

# W3. The path every other verification uses. Separates "the sandbox broke it"
#     from "the config layer is broken".
value, _, err = read(CONFIG, False)
results["W3"] = value == SPOOFED
notes.append(f"W3: --no-sandbox + config, main -> {value!r} (expect {SPOOFED})"
             f"{'; ' + err if err else ''}")

# W4. Worker parity under the spoof (conventions rule 3). A renderer and a
#     dedicated worker are different processes on Windows, so the environment
#     filter could reach one and not the other; this is the row that would catch
#     that.
results["W4"] = worker_cfg == SPOOFED and worker_cfg == main_cfg
notes.append(f"W4: sandboxed + config, worker -> {worker_cfg!r} "
             f"(expect {SPOOFED}, and equal to main {main_cfg!r})")

# W5. Worker parity WITHOUT a config, so W4 cannot pass by both values happening
#     to be the spoof: unconfigured, the worker must agree with the main thread on
#     the real value too.
results["W5"] = worker_real is not None and worker_real == real
notes.append(f"W5: sandboxed, no config, worker -> {worker_real!r} "
             f"(expect equal to main {real!r})")

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

for n in notes:
    print("note:", n)
if len(results) != EXPECTED:
    sys.exit(f"expected {EXPECTED} rows, built {len(results)}: a row was added or "
             "removed without updating EXPECTED")
for k in ("W1", "W2", "W3", "W4", "W5", "A1", "A2"):
    print(f"{k}: {'PASS' if results[k] else 'FAIL'}")
print(f"{sum(results.values())} PASS {EXPECTED - sum(results.values())} FAIL")
sys.exit(0 if all(results.values()) else 1)
