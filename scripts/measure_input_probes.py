#!/usr/bin/env python3
"""Input probes I1-I6 (plan 2026-11-21-input-probes.md): does input from a driver differ, to a page, from stock Chrome's
under OS input? Measures only; fixes are decided per row afterwards.

Arms (all on the Windows host, one launch per arm and run, every row in one page load, phases told to the page):
  ctl125, ctl1000  stock chrome.exe, Win32 SendInput (no CDP); 125 and 1000 Hz pointer, the control's envelope
  raw              fork, patchright, page.mouse/keyboard (humanize off), a path at 125 Hz
  rawh             the same with humanize:enabled
  human            fork + camoucrome.human (click only: rows I1-I3; the rest is n/a, no API)
  red              the planted bad arm: back-to-back moves, clickCount 1, no right click. Its I1 row cannot fail live: Chrome's
                   input router coalesces a burst to one move per frame; the synthetic fixture holds the planted case
                   (test_input_probe_rows). I1 has no live RED: rawh's old FAIL (.42) was the page's tick ring, not the browser
                   (measurements/2026-11-22-input-p0.md); I2 and I2b (coalesced list, stamp spacing) are what rawh fails live

  python measure_input_probes.py run --stock-exe PATH --fork-exe PATH --out DIR [--runs 6] [--arms ...] [--fork-version X]
  (CAMOU_WSL_USER names the WSL user that reads the build lock; the fork must be the pin in upstream.env or --fork-version)
  python measure_input_probes.py report DIR

Run in session 1 through scripts/windows/run-interactive.ps1, in the client venv. Verdicts: PASS, FAIL, UNMEASURED
(a launch with a GPU crash, a foreground that is not our browser, a rAF rate that is not the display's, a stray event
while parked, a missing surface)."""
import argparse
import http.server
import json
import math
import os
import pathlib
import statistics
import subprocess
import sys
import tempfile
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "client" / "python"))
import input_probe_rows as R  # noqa: E402

DPR = 1.25
WIN = (1000, 700)
POS = (360, 160)
ARMS = ("ctl125", "ctl1000", "raw", "rawh", "human", "red")
CTL = ("ctl125", "ctl1000")
PHASE_OF = {"I1": "move", "I2": "move", "I2b": "move", "I3": "move", "I4": "edge", "I5": "click", "I6": "key"}
PHASES = ("move", "edge", "click", "key")
FLUSH_S = 0.8       # the page posts every 300 ms and learns a phase on the reply


# ---------------------------------------------------------------- pure: paths
def minjerk(t):
    return 10 * t ** 3 - 15 * t ** 4 + 6 * t ** 5


def path(p0, p1, dur_ms, hz, bow=0.0):
    """[(t_ms, x, y)] in CSS px from p0 to p1, a minimum-jerk speed profile, one sample per 1000/hz ms. bow: sideways bulge."""
    n = max(2, int(dur_ms * hz / 1000))
    out = []
    for i in range(n + 1):
        s = minjerk(i / n)
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(dx, dy) or 1.0
        off = bow * math.sin(math.pi * s)
        out.append((i * dur_ms / n, p0[0] + dx * s - dy / L * off, p0[1] + dy * s + dx / L * off))
    return out


def move_routes(w, h):
    """The I1-I3 gesture: four sweeps across the viewport, 1.2 s each."""
    pts = [(0.15 * w, 0.25 * h), (0.85 * w, 0.30 * h), (0.80 * w, 0.80 * h), (0.20 * w, 0.75 * h), (0.15 * w, 0.25 * h)]
    return [(a, b, 1200, 60.0) for a, b in zip(pts, pts[1:])]


def edge_legs(w, h):
    """The I4 gesture: from the centre out across each edge, 40 px past it, and back."""
    c = (w / 2, h / 2)
    return [(c, (w + 40, h / 2)), (c, (-40, h / 2)), (c, (w / 2, h + 40)), (c, (w / 2, -40))]


# ---------------------------------------------------------------- server
class State:
    phase = "boot"
    snap = None


def serve(out_dir):
    out_dir = pathlib.Path(out_dir)
    st = State()
    page = (HERE / "input_probe" / "page.html").read_bytes()

    class H(http.server.BaseHTTPRequestHandler):
        def _send(self, body=b"", ctype="text/plain"):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/page.html"):
                self._send(page, "text/html; charset=utf-8")
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                st.snap = json.loads(body)
            except ValueError:
                pass
            self._send(st.phase.encode())

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, st


# ---------------------------------------------------------------- actors: one per driver
def sleep_until(t):
    while True:
        r = t - time.perf_counter()
        if r <= 0:
            return
        time.sleep(r - 0.002 if r > 0.004 else 0)


def play(points, fn):
    t0 = time.perf_counter()
    for t, x, y in points:
        sleep_until(t0 + t / 1000)
        fn(x, y)


class SendActor:
    """OS input. Coordinates are CSS px of the viewport; origin is the viewport's top-left in physical screen px."""

    def __init__(self, si, origin, hz):
        self.si, self.o, self.hz = si, origin, hz

    def at(self, x, y):
        return round(self.o[0] + x * DPR), round(self.o[1] + y * DPR)

    def move(self, x, y):
        self.si.move_to(*self.at(x, y))

    def sweep(self, p0, p1, dur, hz=None, bow=0.0):
        play(path(p0, p1, dur, self.hz), lambda x, y: self.move(x, y))

    def click(self, x, y, button="left", count=1, gap=120, hold=60):
        self.move(x, y)
        time.sleep(0.15)
        for i in range(count):
            self.si.down(button)
            time.sleep(hold / 1000)
            self.si.up(button)
            if i + 1 < count:
                time.sleep(gap / 1000)

    def key_hold(self, ms, delay, interval):
        self.si.key_down()
        t0 = time.perf_counter()
        nxt = t0 + delay / 1000
        while time.perf_counter() - t0 < ms / 1000:
            sleep_until(nxt)
            self.si.key_down()      # a repeat: the key is already down, so Windows flags it
            nxt += interval / 1000
        self.si.key_up()

    def park(self):
        w, h = self.si.screen()
        self.si.move_to(w - 2, h - 2)


class CdpActor:
    """patchright's page.mouse and keyboard. burst: the RED, moves back to back (steps) and a single clickCount."""

    def __init__(self, page, hz, burst=False):
        self.p, self.hz, self.burst = page, hz, burst

    def sweep(self, p0, p1, dur, hz=None, bow=0.0):
        if self.burst:
            self.p.mouse.move(*p0)
            self.p.mouse.move(*p1, steps=int(dur * self.hz / 1000))
        else:
            play(path(p0, p1, dur, self.hz), lambda x, y: self.p.mouse.move(x, y))

    def click(self, x, y, button="left", count=1, gap=120, hold=60):
        self.p.mouse.move(x, y)
        time.sleep(0.15)
        if self.burst:
            if button == "right":
                return      # RED: no right click at all
            for _ in range(count):
                self.p.mouse.click(x, y, click_count=1)
            return
        self.p.mouse.click(x, y, button=button, click_count=count, delay=hold)

    def key_hold(self, ms, delay, interval):
        kb = self.p.keyboard
        kb.down("a")
        t0 = time.perf_counter()
        nxt = t0 + delay / 1000
        while time.perf_counter() - t0 < ms / 1000:
            sleep_until(nxt)
            kb.down("a")        # patchright flags a key that is already down as autoRepeat
            nxt += interval / 1000
        kb.up("a")

    def park(self):
        pass


def gesture(actor, phase, w, h, kb):
    """One phase's gesture. Returns False when this arm has no gesture for the phase (n/a)."""
    if phase == "move":
        for a, b, d, _ in move_routes(w, h):
            actor.sweep(a, b, d)
    elif phase == "edge":
        for c, e in edge_legs(w, h):
            actor.sweep(c, e, 450)
            time.sleep(0.25)
            actor.sweep(e, c, 450)
            time.sleep(0.25)
    elif phase == "click":
        c = (w / 2, h / 2)
        actor.click(*c, button="right")
        time.sleep(0.8)
        actor.click(*c, count=2)
        time.sleep(0.8)
        actor.click(*c, count=3)
    elif phase == "key":
        actor.key_hold(1500, kb[0], kb[1])
    return True


# ---------------------------------------------------------------- runs
def split(snap, row):
    """The log of one row: events of its phase, all rAF ticks."""
    ph = PHASE_OF[row]
    return {"meta": snap["meta"], "raf": snap["raf"], "ev": [e for e in snap["ev"] if e.get("ph") == ph]}


def idle_strays(snap):
    """Moves while no gesture runs and the window is up: the idle phase and the end phase. A stray pointer emits its own.
    (The boot phase is not counted: a cursor under a window that is being created makes one; run_arm parks the cursor
    before every launch, and rec["boot_moves"] says how many arrived anyway.)"""
    return sum(1 for e in snap["ev"] if e.get("ph") in ("idle", "end") and e["t"] in ("mousemove", "pointermove"))


def adapter_kind(name):
    """A display adapter's name as a class only: the GPU string of the host never reaches a run file."""
    n = (name or "").lower()
    return "vdd" if "virtual display" in n else "rdp" if "remote display" in n else "gpu"


def screens():
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Add-Type -AssemblyName System.Windows.Forms; [Windows.Forms.Screen]::AllScreens | % { 'screen ' + $_.Bounds.Width + 'x' + $_.Bounds.Height }; "
                          "(Get-CimInstance Win32_VideoController | ? CurrentRefreshRate | % { $_.CurrentRefreshRate + 'Hz|' + $_.Name })"],
                         capture_output=True, text=True, timeout=60).stdout.split("\n")
    return [(ln.split("|")[0] + " " + adapter_kind(ln.split("|", 1)[1])) if "|" in ln else ln.strip() for ln in out if ln.strip()]


def running_exe(udd):
    """(path, file version) of the browser process whose command line holds this profile, or None."""
    q = udd.replace("'", "''")
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"Get-CimInstance Win32_Process | ? {{ $_.CommandLine -and $_.CommandLine.Contains('{q}') -and $_.CommandLine -notmatch '--type=' }} "
                          "| select -First 1 | % { $_.ExecutablePath + '|' + (Get-Item $_.ExecutablePath).VersionInfo.FileVersion }"],
                         capture_output=True, text=True, timeout=60).stdout.strip()
    return tuple(out.split("|", 1)) if "|" in out else None


def wrong_browser(udd, want_exe, want_prefix, pin_exact, port=None):
    """Why the browser that runs is not the one the arm names, or None. The path of the running process must be the
    configured one, its file version the pin (fork) or the pin's build (stock; any patch of it), and, with a debug port,
    /json/version must say the same version."""
    got = running_exe(udd)
    if not got:
        return "no browser process found for this profile"
    path, ver = got
    if os.path.normcase(os.path.realpath(path)) != os.path.normcase(os.path.realpath(want_exe)):
        return f"the running browser is {path}, not {want_exe}"
    ok = ver == want_prefix if pin_exact else ver.startswith(want_prefix.rsplit(".", 1)[0] + ".")
    if not ok:
        return f"the running browser is version {ver}, expected {'exactly ' if pin_exact else 'build '}{want_prefix}"
    if port:
        import urllib.request
        v = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=10))["Browser"]
        if not v.endswith("/" + ver):
            return f"/json/version says {v}, the file says {ver}"
    return None


def foreground_is(si, pid_set):
    return si.foreground_pid() in pid_set


def tree_pids(pid):
    """The browser process and its descendants (the foreground window belongs to one of them)."""
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"$p=@({pid});do{{$n=(Get-CimInstance Win32_Process|?{{$p -contains $_.ParentProcessId -and $p -notcontains $_.ProcessId}}).ProcessId;$p+=$n}}while($n);$p -join ','"],
                         capture_output=True, text=True, timeout=60).stdout.strip()
    return {int(x) for x in out.split(",") if x} | {pid}


def wait_snap(st, pred, timeout=20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if st.snap and pred(st.snap):
            return True
        time.sleep(0.1)
    return False


def set_phase(st, name):
    st.phase = name
    time.sleep(FLUSH_S)


def run_arm(arm, i, a, srv, st, out):
    """One launch. Returns the record written to out/<arm>-<i>.json."""
    from camoucrome import launcher, human
    import gpu_gate
    rec = {"arm": arm, "run": i, "unmeasured": None}
    url = f"http://127.0.0.1:{srv.server_port}/page.html?arm={arm}&run={i}"
    udd = tempfile.mkdtemp(prefix="input-probe-")
    st.snap, st.phase = None, "boot"
    proc = ctx = pw = None
    try:
        import input_probe_sendinput as si
        si.aware()
        si.park()           # the OS cursor off the window's future place, so no arm starts with a pointer under it
        kb = (500, 33)
        if arm in CTL:
            kb = si.keyboard_timing()
            port = free_port()
            argv = [a.stock_exe, *launcher.BASE_ARGS, f"--user-data-dir={udd}", f"--remote-debugging-port={port}",
                    f"--window-size={WIN[0]},{WIN[1]}", f"--window-position={POS[0]},{POS[1]}",
                    f"--force-device-scale-factor={DPR}", url]
            proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            from patchright.sync_api import sync_playwright
            pw = sync_playwright().start()
            cfg = {"humanize:enabled": arm in ("rawh", "human"), "input:deviceGrid": True}  # the launcher's own default, pinned so the arms measure the shipped config
            ctx = launcher.launch(pw, a.fork_exe, config=cfg, user_data_dir=udd, window=WIN, position=POS, dpr=DPR, headless=False)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(url)
        if not wait_snap(st, lambda s: len(s["raf"]) > 20):
            rec["unmeasured"] = "the page never reported"
            return rec
        want_exe = a.stock_exe if arm in CTL else a.fork_exe
        why = wrong_browser(udd, want_exe, a.fork_version, pin_exact=arm not in CTL, port=port if arm in CTL else None)
        rec["exe_version"] = (running_exe(udd) or (None, None))[1]
        if why:
            rec["unmeasured"], rec["abort"] = f"wrong browser: {why}", True
            return rec
        f = R.frame_ms({"raf": st.snap["raf"]})
        rec["raf_ms"] = f
        if not (f and R.FRAME_OK[0] <= f <= R.FRAME_OK[1]):
            rec["unmeasured"], rec["abort"] = f"rAF interval {f} ms is not the 60 Hz display's", True
            return rec
        st.phase = "idle"
        time.sleep(FLUSH_S)
        meta = st.snap["meta"]
        w, h = meta["iw"], meta["ih"]
        rec["window"] = [w, h]
        rec["screens"] = screens()
        if arm in CTL:
            pids = tree_pids(proc.pid)
            # calibrate: put the cursor on the window, read where the page saw it, derive the viewport's origin
            st.phase = "cal"
            time.sleep(FLUSH_S)
            si.move_to(POS[0] + 300, POS[1] + 300)
            time.sleep(0.2)
            si.move_to(POS[0] + 320, POS[1] + 310)
            if not wait_snap(st, lambda s: any(e["ph"] == "cal" and e["t"] == "mousemove" for e in s["ev"])):
                rec["unmeasured"] = "calibration move never reached the page"
                return rec
            time.sleep(FLUSH_S)
            e = [e for e in st.snap["ev"] if e["ph"] == "cal" and e["t"] == "mousemove"][-1]
            origin = (POS[0] + 320 - e["x"] * DPR, POS[1] + 310 - e["y"] * DPR)
            hz = 125 if arm == "ctl125" else 1000
            actor = SendActor(si, origin, hz)
            rec["origin"], rec["foreground_ok"] = list(origin), foreground_is(si, pids)
            if not rec["foreground_ok"]:
                rec["unmeasured"] = "the foreground window is not the launched browser"
                return rec
            actor.park()
            time.sleep(0.5)
        else:
            actor = CdpActor(page, 125, burst=(arm == "red"))
        for ph in PHASES:
            if arm == "human" and ph != "move":
                continue            # no human API for edge, right/multi click, key repeat: n/a
            set_phase(st, ph)
            if arm == "human":
                for _ in range(6):
                    human.click(page, "#t")
            else:
                if arm in CTL and not foreground_is(si, pids):
                    rec["unmeasured"] = f"foreground left the browser before {ph}"
                    return rec
                gesture(actor, ph, w, h, kb)
                if arm in CTL and not foreground_is(si, pids):
                    rec["unmeasured"] = f"focus lost during {ph}"
                    return rec
            time.sleep(0.4)
        set_phase(st, "end")
        rec["keyboard"] = list(kb)
        if arm in CTL:
            crashes = gpu_gate.read_port_status(port)[0]
        else:
            crashes = gpu_gate.read_ctx(ctx) if hasattr(gpu_gate, "read_ctx") else None
            crashes = crashes[0] if isinstance(crashes, tuple) else crashes
        rec["gpu_crashes"] = crashes
        if crashes != 0:
            rec["unmeasured"] = f"gpu-crash={'unknown' if crashes is None else crashes}"
        rec["snap"] = st.snap
        rec["boot_moves"] = sum(1 for e in st.snap["ev"] if e.get("ph") == "boot" and e["t"] == "pointermove")
        if idle_strays(st.snap):
            rec["unmeasured"] = f"{idle_strays(st.snap)} stray move(s) outside the gestures"
        return rec
    except Exception as ex:   # noqa: BLE001 - any failure of a launch is that launch's UNMEASURED, never a missing record
        rec["unmeasured"] = f"error: {type(ex).__name__}: {ex}"[:300]
        return rec
    finally:
        try:
            if ctx:
                ctx.close()
            if pw:
                pw.stop()
        except Exception:
            pass
        if proc:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        (out / f"{arm}-{i}.json").write_text(json.dumps(rec), encoding="utf-8")


def free_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


BUILD_LOCK = "$HOME/actions-runner/_work/camoucrome/camoucrome/scripts/build_lock.sh"


def launch_problem():
    """Why a launch may not start now, or None: the box's build lock is held, a stray chrome runs, or the proxy is on.
    A refusal waits, it is never bypassed."""
    user = os.environ.get("CAMOU_WSL_USER")
    if not user:
        return "CAMOU_WSL_USER is not set (the WSL user that reads the build lock)"
    lock = subprocess.run(["wsl.exe", "-d", "Ubuntu-24.04", "-u", user, "--", "bash", "-c", f"bash {BUILD_LOCK} status input-probes"],
                          capture_output=True, text=True, timeout=60).stdout.strip().splitlines()[:1]
    if not lock or lock[0].strip() != "free":
        return f"build_lock is not free: {lock[0].strip() if lock else 'unreadable'}"
    ps = subprocess.run(["powershell", "-NoProfile", "-Command",
                         "(Get-Process chrome -ErrorAction SilentlyContinue | Measure-Object).Count; "
                         "(Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings').ProxyEnable"],
                        capture_output=True, text=True, timeout=60).stdout.split()
    if ps[:1] != ["0"]:
        return f"{ps[:1]} chrome process(es) running"
    if ps[1:2] != ["0"]:
        return "ProxyEnable is not 0"
    return None


def pinned_version():
    f = ROOT / "upstream.env"
    if f.is_file():
        for ln in f.read_text(encoding="utf-8").splitlines():
            if ln.startswith("CHROMIUM_TAG="):
                return ln.split("=", 1)[1].strip()
    return None


def cmd_run(a):
    if os.name != "nt":
        sys.exit("UNMEASURED: the probes run on the Windows host")
    import gpu_gate
    gpu_gate.require_interactive()
    a.fork_version = a.fork_version or pinned_version()
    if not a.fork_version:
        sys.exit("UNMEASURED: no pin (upstream.env CHROMIUM_TAG or --fork-version)")
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    srv, st = serve(out)
    arms = a.arms.split(",")
    # interleave: run i of every arm before run i+1, so a slow drift hits every arm alike
    for i in range(a.runs):
        for arm in arms:
            for _ in range(60):
                why = launch_problem()
                if not why:
                    break
                print("waiting:", why, flush=True)
                time.sleep(10)
            else:
                sys.exit(f"UNMEASURED: {why}")
            r = run_arm(arm, i, a, srv, st, out)
            print(arm, i, r.get("unmeasured") or "ok", "raf_ms=%s" % r.get("raf_ms"), "gpu_crashes=%s" % r.get("gpu_crashes"), flush=True)
            if r.get("abort"):
                sys.exit("ABORT: " + r["unmeasured"])
    return 0


def load(d):
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(pathlib.Path(d).glob("*-*.json"))]
    return recs


def cmd_report(a):
    recs = load(a.dir)
    by = {}
    for r in recs:
        by.setdefault(r["arm"], []).append(r)

    def measured(rs):
        return [r for r in rs if not r.get("unmeasured") and r.get("snap")]

    # one control group per pointer rate, never pooled
    ctl = {arm: measured(by.get(arm, [])) for arm in CTL}
    lines = ["| row | arm | n | verdict | detail |", "|---|---|---|---|---|"]
    for row in R.ROWS:
        for arm, rs in by.items():
            if arm in CTL:
                continue
            good = measured(rs)
            if arm == "human" and PHASE_OF[row] != "move":
                lines.append(f"| {row} | {arm} | 0 | n/a (no API) | |")
                continue
            if not good:
                why = "; ".join(sorted({r.get("unmeasured") or "no snapshot" for r in rs}))
                lines.append(f"| {row} | {arm} | 0 | UNMEASURED | {why} |")
                continue
            v = R.judge(row, {g: [split(r["snap"], row) for r in rs_] for g, rs_ in ctl.items()}, [split(r["snap"], row) for r in good])
            if "_" in v:
                lines.append(f"| {row} | {arm} | {len(good)} | UNMEASURED | {v['_'][1]} |")
                continue
            det = "; ".join(f"{k}={x[0]} {x[1]} [{x[2]}]" for k, x in v.items() if k != "_row")
            lines.append(f"| {row} | {arm} | {len(good)} | {R.row_verdict(v)} | per rate: {v['_row'][2]}; {det} |")
    lines += ["", "red's I1 cannot fail live (Chrome coalesces a burst to one move per frame); the planted case is the "
              "synthetic fixture. I1 is UNMEASURED when fewer than 90 % of the moves lie inside the tick log. I6's key timing is authored by the harness in every arm and is INFO, not judged."]
    text = "\n".join(lines)
    (pathlib.Path(a.dir) / "table.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--stock-exe", required=True)
    r.add_argument("--fork-exe", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--runs", type=int, default=6)
    r.add_argument("--arms", default=",".join(ARMS))
    r.add_argument("--fork-version", default=None, help="the pinned build (default: CHROMIUM_TAG of upstream.env)")
    p = sub.add_parser("report")
    p.add_argument("dir")
    a = ap.parse_args(argv)
    return cmd_run(a) if a.cmd == "run" else cmd_report(a)


if __name__ == "__main__":
    sys.exit(main())
