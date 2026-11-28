"""What a launch leaves behind: owner-only profile dirs, the sweep of a killed
client's temp dirs, and the browser stderr redacted out of an error. The Go
(atrest.go, core/atrest.go) and Node (atrest.js) clients do the same."""
import json
import os
import re
import shutil
import sys
import tempfile
import time

# TEMP_PREFIX, CRASH_KIND and STALE_AFTER mirror settings/launcher.json launch.temp_dirs; tests/test_launcher.py
# asserts it.
TEMP_PREFIX = "camoucrome-"
CRASH_KIND = "crash-"
STALE_AFTER = 3600.0  # seconds since the dir last changed
REDACTED = "<redacted>"
# camoucrome-<pid>-<rand> (a temp profile) and camoucrome-crash-<pid>-<rand>, <pid> the launching client's.
# The scripts' own camoucrome-<word>- dirs and the pid-less names of older clients never match.
_OWNED = re.compile(re.escape(TEMP_PREFIX) + "(?:" + re.escape(CRASH_KIND) + r")?([0-9]+)-[^/\\]+\Z")
# A quoted segment shaped like a key name (every settings/keys.json name is) is kept on a camoucfg: line unless
# it is a configured value, and so is an invariant id: both are public constants the operator needs.
_KEY_SHAPED = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:[.:][A-Za-z0-9_]+)+\Z")


def makedirs(path):
    """os.makedirs with every directory it creates owner-only (0700; Python's own gives the mode to the leaf
    only). An existing directory keeps its mode. Windows ignores the mode."""
    path = os.path.abspath(path)
    if os.path.isdir(path):
        return
    parent = os.path.dirname(path)
    if parent != path:
        makedirs(parent)
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        if not os.path.isdir(path):
            raise


def mkdtemp(kind=""):
    """A temp dir named for this process (kind "" for a profile, CRASH_KIND for crash dumps), so sweep() can tell
    a killed client's leftovers from a live one's. mkdtemp makes it 0700."""
    return tempfile.mkdtemp(prefix=f"{TEMP_PREFIX}{kind}{os.getpid()}-")


def _alive(pid):
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes as w
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.argtypes, k.OpenProcess.restype = [w.DWORD, w.BOOL, w.DWORD], w.HANDLE
        k.GetExitCodeProcess.argtypes, k.GetExitCodeProcess.restype = [w.HANDLE, w.LPDWORD], w.BOOL
        k.CloseHandle.argtypes, k.CloseHandle.restype = [w.HANDLE], w.BOOL
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.get_last_error() != 87  # ERROR_INVALID_PARAMETER: no such process; anything else keeps
        code = w.DWORD()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return not ok or code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)  # POSIX only: on Windows os.kill terminates
    except ProcessLookupError:
        return False
    except OSError:
        return True  # EPERM: another user's live process
    return True


def _browser_running(d):
    if sys.platform == "win32":
        # Chrome holds <profile>/lockfile open without delete sharing while it runs: the remove fails then.
        try:
            os.remove(os.path.join(d, "lockfile"))
        except FileNotFoundError:
            return False
        except OSError:
            return True
        return False
    try:
        link = os.readlink(os.path.join(d, "SingletonLock"))  # "<host>-<pid>", left behind by a killed browser
    except OSError:
        return False
    pid = link.rpartition("-")[2]
    return not pid.isdigit() or _alive(int(pid))


def _protected(keep):
    """The (st_dev, st_ino) of keep, resolved, and of every dir above it, so sweep() spares a candidate that is
    the caller's dir or holds it however either is spelled (a symlink, /var vs /private/var, an 8.3 name, case).
    keep may not exist yet: its deepest existing ancestor stands in. None on any doubt."""
    p = os.path.abspath(keep)
    while True:
        try:
            os.stat(p)
            break
        except FileNotFoundError:
            if os.path.dirname(p) == p:
                return None
            p = os.path.dirname(p)
        except OSError:
            return None
    p, ids = os.path.realpath(p), set()
    while True:
        try:
            st = os.stat(p)
        except OSError:
            return None
        ids.add((st.st_dev, st.st_ino))
        if os.path.dirname(p) == p:
            return ids
        p = os.path.dirname(p)


def sweep(keep=None):
    """Removes the temp profiles and crash dirs a killed client left (a profile holds Preferences with the
    identity's languages; a crash dir, minidumps with CAMOU_CONFIG). Only this client family's names; never
    `keep` (the caller's profile) or a dir that holds it. Liveness: the client's pid is in the name, so one kill(0) / OpenProcess per
    candidate, no file to open, and a pid that names any live process keeps the dir; a profile is kept too while
    its SingletonLock / lockfile says a browser outlived the client. Failures are ignored."""
    root = tempfile.gettempdir()
    spared = _protected(keep) if keep else set()
    if spared is None:
        return  # never delete on doubt
    now = time.time()
    try:
        names = os.listdir(root)
    except OSError:
        return
    for name in names:
        m = _OWNED.match(name)
        d = os.path.join(root, name)
        if not m:
            continue
        try:
            st = os.lstat(d)
            if (not os.path.isdir(d) or os.path.islink(d) or (st.st_dev, st.st_ino) in spared
                    or now - st.st_mtime < STALE_AFTER
                    or (hasattr(os, "getuid") and st.st_uid != os.getuid())
                    or _alive(int(m.group(1))) or _browser_running(d)):
                continue
            shutil.rmtree(d, ignore_errors=True)  # one pass: a locked dir must not stall the launch
        except Exception:  # noqa: BLE001 -- a sweep failure is never fatal
            continue


def _joined(env, name):
    if name in env:
        return env[name]
    parts, n = [], 1
    while f"{name}_{n}" in env:
        parts.append(env[f"{name}_{n}"])
        n += 1
    return "".join(parts)


def _leaves(v, out):
    if isinstance(v, dict):
        for x in v.values():
            _leaves(x, out)
    elif isinstance(v, list):
        for x in v:
            _leaves(x, out)
    elif v is not None:
        out.add(json.dumps(v) if not isinstance(v, str) else v)


def redact(text, env):
    """text (the browser's stderr, or an error that carries it) with the identity taken out, line structure kept:
    every CAMOU_CONFIG* / CAMOU_PRESET* string of env; every config and preset value of 3+ characters where it
    stands as a whole token; and on a camoucfg: log line, every quoted segment that is neither a key name nor an
    invariant id, plus a validator's unquoted "It should be <value>." (a derived value no config leaf holds)."""
    raws = sorted({v for k, v in env.items() if re.fullmatch(r"CAMOU_(CONFIG|PRESET)(_[0-9]+)?", k) and v},
                  key=len, reverse=True)
    keys, leaves = set(), set()
    for name in ("CAMOU_CONFIG", "CAMOU_PRESET"):
        try:
            doc = json.loads(_joined(env, name) or "null")
        except ValueError:
            continue
        if isinstance(doc, dict):
            keys.update(doc)
        _leaves(doc, leaves)
    words = sorted((v for v in leaves if len(v) >= 3 and v not in keys), key=len, reverse=True)
    token = re.compile("|".join(r"(?<![A-Za-z0-9_])" + re.escape(w) + r"(?![A-Za-z0-9_])" for w in words)) if words else None
    out = []
    for line in text.split("\n"):
        for r in raws:
            line = line.replace(r, REDACTED)
        if "camoucfg:" in line:
            line = re.sub(r"(It should be ).+?(\. Not repaired)", r"\1" + REDACTED + r"\2", line)
            line = re.sub(r"(invariant )?'([^'\n]*)'", lambda m: m.group(0) if m.group(1) or m.group(2) in keys or (
                _KEY_SHAPED.match(m.group(2)) and m.group(2) not in leaves) else f"{m.group(1) or ''}'{REDACTED}'", line)
        if token:
            line = token.sub(REDACTED, line)
        out.append(line)
    return "\n".join(out)


def redact_error(exc, env):
    """Redacts exc's text in place (args, and a Playwright Error's message and stack) and returns it, so the
    caller still gets the driver's own exception type."""
    try:
        if exc.args and isinstance(exc.args[0], str):
            exc.args = (redact(exc.args[0], env),) + exc.args[1:]
        for a in ("_message", "_stack"):
            v = getattr(exc, a, None)
            if isinstance(v, str):
                setattr(exc, a, redact(v, env))
    except Exception:  # noqa: BLE001 -- the launch error is what the caller must see
        pass
    return exc
