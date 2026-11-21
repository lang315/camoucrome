"""The OS-level input injector of the input probes' control: Win32 SendInput, no CDP. Windows only (the module imports
anywhere; every call needs ctypes.windll). What it does NOT do: it does not auto-repeat a held key (injected input never
does; Windows leaves typematic to the keyboard), so key_hold() authors the repeats with the host's own keyboard delay
and speed settings, and the row says so."""
import ctypes
import os
import time

if os.name == "nt":
    from ctypes import wintypes
    U = ctypes.windll.user32
    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR)]

    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

MOVE, LDOWN, LUP, RDOWN, RUP, ABSOLUTE = 0x1, 0x2, 0x4, 0x8, 0x10, 0x8000
KEYUP, SCANCODE = 0x2, 0x8
SC_A = 0x1E
SPI_GETKEYBOARDDELAY, SPI_GETKEYBOARDSPEED = 0x16, 0xA


def aware():
    """Per-monitor DPI aware, so every coordinate here is a physical pixel."""
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))


def _send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    if U.SendInput(len(inputs), arr, ctypes.sizeof(INPUT)) != len(inputs):
        raise OSError("SendInput injected fewer events than asked (blocked by UIPI or a secure desktop?)")


def _mouse(flags, x=0, y=0):
    return INPUT(0, _U(mi=MOUSEINPUT(x, y, 0, flags, 0, 0)))


def _key(sc, up=False):
    return INPUT(1, _U(ki=KEYBDINPUT(0, sc, SCANCODE | (KEYUP if up else 0), 0, 0)))


def screen():
    return U.GetSystemMetrics(0), U.GetSystemMetrics(1)


def park():
    """The cursor to the primary screen's bottom-right corner, clear of the probe window."""
    w, h = screen()
    move_to(w - 2, h - 2)


def move_to(x, y):
    """Absolute move to a physical pixel of the primary screen (the 0..65535 grid rounded up so the pixel is exact)."""
    w, h = screen()
    _send(_mouse(MOVE | ABSOLUTE, -(-int(x) * 65536 // w), -(-int(y) * 65536 // h)))


def down(button="left"):
    _send(_mouse(LDOWN if button == "left" else RDOWN))


def up(button="left"):
    _send(_mouse(LUP if button == "left" else RUP))


def key_down(sc=SC_A):
    _send(_key(sc))


def key_up(sc=SC_A):
    _send(_key(sc, True))


def keyboard_timing():
    """(delay ms, interval ms) of the host's typematic settings: delay 0..3 is 250/500/750/1000 ms, speed 0..31 is 2.5..30 Hz."""
    d, s = ctypes.c_uint(), ctypes.c_uint()
    U.SystemParametersInfoW(SPI_GETKEYBOARDDELAY, 0, ctypes.byref(d), 0)
    U.SystemParametersInfoW(SPI_GETKEYBOARDSPEED, 0, ctypes.byref(s), 0)
    return 250 * (d.value + 1), 1000.0 / (2.5 + s.value * 27.5 / 31)


def sleep_until(t):
    """Wall-clock wait to time.perf_counter() value t: sleep for the coarse part, spin the last 2 ms."""
    while True:
        r = t - time.perf_counter()
        if r <= 0:
            return
        time.sleep(r - 0.002 if r > 0.004 else 0)


def play(points, fn):
    """points: [(t_ms, x, y)] with t from 0; fn(x, y) at each one, on schedule."""
    t0 = time.perf_counter()
    for t, x, y in points:
        sleep_until(t0 + t / 1000)
        fn(x, y)


def foreground_pid():
    pid = wintypes.DWORD()
    U.GetWindowThreadProcessId(U.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value
