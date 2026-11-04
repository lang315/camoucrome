"""CPU pin (C3): a claim of N cores below the host's is enforced by affinity, so timing on the host cannot show more.

The driver subprocess spawns Chrome, so it is pinned to N of its allowed CPUs right before the launch call and
restored right after; Chrome and its children inherit the mask. A lock serialises pin-launch-restore, because two
overlapping launches would restore each other's mask. Masks are sets of CPU numbers."""
import asyncio
import os
import random
import sys
import threading
import weakref

_lock = threading.Lock()
_alocks = weakref.WeakKeyDictionary()  # one asyncio.Lock per event loop


def get_mask(pid):
    """The CPUs `pid` may run on, or None where the platform has no affinity API."""
    if sys.platform == "linux":
        return set(os.sched_getaffinity(pid))
    if sys.platform == "win32":
        return _win_mask(pid)
    # shortcut: macOS has no CPU affinity API, so a claim below the host's cores is not enforced there; revisit if a macOS host is supported
    return None


def set_mask(pid, cpus):
    if sys.platform == "linux":
        # sched_setaffinity is per thread; a thread made later inherits from its creator, but the driver's pool already exists
        try:
            tids = [int(t) for t in os.listdir(f"/proc/{pid}/task")]
        except OSError:
            tids = [pid]
        for tid in tids:
            os.sched_setaffinity(tid, cpus)
    elif sys.platform == "win32":
        _win_mask(pid, cpus)


def _win_mask(pid, cpus=None):
    """Read (cpus None) or set a process's affinity; shortcut: one processor group, so at most 64 CPUs, upgrade for a bigger host."""
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = wintypes.HANDLE
    h = k.OpenProcess(0x0400 | 0x0200, False, pid)  # QUERY_INFORMATION | SET_INFORMATION
    if not h:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        proc, system = ctypes.c_size_t(), ctypes.c_size_t()
        if not k.GetProcessAffinityMask(h, ctypes.byref(proc), ctypes.byref(system)):
            raise ctypes.WinError(ctypes.get_last_error())
        if cpus is None:
            return {i for i in range(64) if proc.value >> i & 1}
        if not k.SetProcessAffinityMask(h, ctypes.c_size_t(sum(1 << c for c in cpus))):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        k.CloseHandle(h)


def driver_pid(playwright):
    """The pid of the driver subprocess behind a patchright playwright object (sync and async share the path), or None."""
    try:
        return playwright._impl_obj._connection._transport._proc.pid
    except AttributeError:
        return None


def engage(playwright, n, rng=random):
    """Pins the driver to n of its allowed CPUs when n is below them. Returns the mask to restore, or None when
    nothing was pinned. Raises RuntimeError (fail closed) when a needed pin cannot be set."""
    own = get_mask(os.getpid())  # the driver inherited this mask
    if own is None or n >= len(own):
        return None
    pid = driver_pid(playwright)
    if pid is None:
        raise RuntimeError(f"cannot pin to {n} CPUs: no driver subprocess pid on {type(playwright).__name__} "
                           "(pass pin_cpu_cores=False to launch unpinned)")
    try:
        allowed = get_mask(pid)
        set_mask(pid, set(rng.sample(sorted(allowed), n)))
    except Exception as e:
        raise RuntimeError(f"cannot pin driver pid {pid} to {n} CPUs: {e}") from e
    return pid, allowed


def release(saved):
    if saved:
        pid, allowed = saved
        try:
            set_mask(pid, allowed)
        except Exception as e:
            raise RuntimeError(f"cannot restore driver pid {pid} to its {len(allowed)} CPUs: {e}") from e


def apply(playwright, n, call):
    with _lock:
        saved = engage(playwright, n)
        try:
            return call()
        finally:
            release(saved)


async def apply_async(playwright, n, call):
    async with _alocks.setdefault(asyncio.get_running_loop(), asyncio.Lock()):
        saved = engage(playwright, n)
        try:
            return await call()
        finally:
            release(saved)
