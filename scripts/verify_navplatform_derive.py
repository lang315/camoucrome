"""Verifies navigator.platform derives from the claimed OS when unset.

RED (before the NavigatorBase::platform() derive): a Windows/Mac UA with no
navigator.platform key leaks the Linux build host's "Linux x86_64" -- so
RP-DERIVE/RP-MAC/RP-WORKER FAIL, the invariant cases PASS. GREEN: all pass.

Structured like verify_sp5a.py: any fault in one session becomes FAIL lines,
never a traceback that discards results already collected.
"""

import json
import sys

import lib_shell

WIN = {"ua:osInfo": "Windows NT 10.0; Win64; x64"}
MAC = {"ua:osInfo": "Macintosh; Intel Mac OS X 10_15_7"}
LINUX = {"ua:osInfo": "X11; Linux x86_64"}
ANDROID = {"ua:osInfo": "Linux; Android 10; K"}
EXPLICIT = {"navigator.platform": "FreeBSD amd64"}

# Read navigator.platform inside a dedicated Worker. NavigatorBase::platform()
# is the only hook a worker reaches (no window, no DevTools override), so this
# is what proves the derive is placed on the shared path, not the window path.
WORKER = r"""(async () => {
  const src = 'self.onmessage=()=>{postMessage(navigator.platform)};';
  const url = URL.createObjectURL(new Blob([src], {type: 'application/javascript'}));
  const w = new Worker(url);
  const p = await new Promise((res) => { w.onmessage = (e) => res(e.data); w.postMessage(0); });
  w.terminate();
  return p;
})()"""

results = {}
notes = []


def failed(keys, label, exc):
    for key in keys:
        results[key] = False
    notes.append(f"{label}: {type(exc).__name__}: {exc}")


def read(cfg, expr="navigator.platform"):
    config = json.dumps(cfg) if cfg is not None else None
    values, err = lib_shell.session(config, [expr])
    return (None, err) if err else (values[0], None)


# --- RP-DERIVE: Windows claim, no platform key -> "Win32" (strong: != host) ---
D = "RP-DERIVE windows UA without platform key derives Win32"
v, e = read(WIN)
if e:
    failed([D], "windows session", e)
else:
    results[D] = v == "Win32"
    notes.append(f"windows -> {v!r}")

# --- RP-MAC: Mac claim -> "MacIntel" (strong: != Linux host) ---
M = "RP-MAC macintosh UA without platform key derives MacIntel"
v, e = read(MAC)
if e:
    failed([M], "mac session", e)
else:
    results[M] = v == "MacIntel"
    notes.append(f"mac -> {v!r}")

# --- RP-WORKER: derive reaches a worker (shared-path placement) ---
W = "RP-WORKER worker navigator.platform under windows UA is Win32"
v, e = read(WIN, WORKER)
if e:
    failed([W], "worker session", e)
else:
    results[W] = v == "Win32"
    notes.append(f"worker(windows) -> {v!r}")

# --- RP-ANDROID: Linux-family derive fires and differs from the Linux host ---
# Android's frozen reduced platform is "Linux armv8l", != the host's
# "Linux x86_64" -- a differ-guaranteed control (CLAUDE.md #4) proving the Linux
# family derives, not merely coincides with the host as RP-LINUX does here.
A = "RP-ANDROID android claim derives Linux armv8l (differs from linux host)"
v, e = read(ANDROID)
if e:
    failed([A], "android session", e)
else:
    results[A] = v == "Linux armv8l"
    notes.append(f"android -> {v!r}")

# --- RP-EXPLICIT (invariant): a configured platform wins over the derive ---
X = "RP-EXPLICIT configured navigator.platform wins over derive"
v, e = read(EXPLICIT)
if e:
    failed([X], "explicit session", e)
else:
    results[X] = v == "FreeBSD amd64"
    notes.append(f"explicit -> {v!r}")

# --- RP-NONE (invariant): no config -> host value, derive did NOT fire ---
# Non-empty and not one of the derived literals proves the fallback stayed the
# host default rather than deriving spuriously. Host string not hardcoded.
N = "RP-NONE unconfigured keeps host platform (no spurious derive)"
host_none, e = read(None)
if e:
    failed([N], "unconfigured session", e)
else:
    results[N] = bool(host_none) and host_none not in ("Win32", "MacIntel")
    notes.append(f"none -> {host_none!r}")

# --- RP-LINUX: Linux claim yields "Linux x86_64" (derive coincides with host) ---
# On this Linux host the derived Linux literal ("Linux x86_64") equals the
# unconfigured host value, so this cannot distinguish derive-fired from
# derive-skipped -- RP-ANDROID above is the control that proves the Linux-family
# derive actually fires. Kept as a coherence check: a Linux claim must read
# "Linux x86_64", and it fails closed if the derive returned Win32 or "".
L = "RP-LINUX linux claim reads Linux x86_64 (matches host on this box)"
v, e = read(LINUX)
if e:
    failed([L], "linux session", e)
elif host_none is None:
    results[L] = False
    notes.append("linux: RP-NONE host value unavailable to compare against")
else:
    results[L] = v == host_none
    notes.append(f"linux -> {v!r} (host {host_none!r})")

for name, ok in sorted(results.items()):
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
for note in notes:
    print(f"      {note}")

sys.exit(0 if results and all(results.values()) else 1)
