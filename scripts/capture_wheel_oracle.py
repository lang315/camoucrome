"""SP2c oracle: how stock Chrome 156 on the Windows host shows a page real
mouse-wheel notches (SendInput, the Win32 path a physical wheel takes),
against the same binary scrolled over CDP. Writes
baselines/chrome-8078-wheel.json; exits 1 if the RED gate says the arms do
not differ (the probe measured nothing). Runs where winhost.py runs (the
Mac, with the buildpc ssh master up).

    capture_wheel_oracle.py --fork 'D:\\camou-win\\chromium\\src\\out\\Release\\chrome.exe'

is SP2c's host-native arm instead: the fork's build scrolled over CDP with
humanize on and off, compared leaf by leaf with the committed real3 arm;
writes nothing, exits 0 on a match, 1 on a mismatch, 2 if the RED fails,
3 if a launch was not measured (no CDP result, a GPU-process crash).
Run it from the console session: RDP turns client-area animation off."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gpu_gate  # noqa: E402
import winhost  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent.parent / "baselines" / "chrome-8078-wheel.json"

PAGE = """<!doctype html><meta charset=utf-8>
<body style="margin:0;height:20000px"><script>
window.log = {wheel: [], scroll: [], dpr: devicePixelRatio, ua: navigator.userAgent};
addEventListener('wheel', e => log.wheel.push({dx: e.deltaX, dy: e.deltaY, dz: e.deltaZ, mode: e.deltaMode,
  wdx: e.wheelDeltaX, wdy: e.wheelDeltaY, trusted: e.isTrusted, t: e.timeStamp}), {passive: true});
addEventListener('scroll', () => log.scroll.push({y: scrollY, t: performance.now()}), {passive: true});
</script>"""
EXPR = "JSON.stringify(window.log)"

# Window at a known place so a screen point is inside the page; scroll
# animation needs ~1 s to settle before the log is read.
WINDOW = ["--window-position=0,0", "--window-size=1000,800"]
SENDINPUT = r"""
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class CamouWheel {
  [StructLayout(LayoutKind.Sequential)] public struct MOUSEINPUT { public int dx, dy, mouseData; public uint dwFlags, time; public IntPtr dwExtraInfo; }
  [StructLayout(LayoutKind.Sequential)] public struct INPUT { public uint type; public MOUSEINPUT mi; }
  [DllImport("user32.dll")] public static extern uint SendInput(uint n, INPUT[] i, int size);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  public static uint Notch(int data) { var i = new INPUT[1]; i[0].mi.mouseData = data; i[0].mi.dwFlags = 0x0800; return SendInput(1, i, Marshal.SizeOf(typeof(INPUT))); }
}
"@
[CamouWheel]::SetCursorPos(500, 500) | Out-Null
Start-Sleep -Milliseconds 300
"""


def real_act(notches):
    # mouseData -120 = one notch towards the user = page scrolls down (deltaY > 0).
    sends = "\nStart-Sleep -Milliseconds 40\n".join("[CamouWheel]::Notch(-120) | Out-Null" for _ in range(notches))
    return SENDINPUT + sends + "\nStart-Sleep -Milliseconds 1500\n"


def cdp_act(delta_y):
    return ("Cdp-Send $ws @{ id = 7; method = \"Input.dispatchMouseEvent\"; params = @{ type = \"mouseWheel\"; "
            f"x = 300; y = 300; deltaX = 0; deltaY = {delta_y} }} }}\n"
            "for ($i = 0; $i -lt 10; $i++) { $m = Cdp-Recv $ws 5000; if ($m -and $m.StartsWith('{\"id\":7,')) { break } }\n"
            "Start-Sleep -Milliseconds 1500\n")


ARMS = {
    "real1": dict(act_ps=real_act(1), window_style="Normal", args=WINDOW),
    "real3": dict(act_ps=real_act(3), window_style="Normal", args=WINDOW),
    "real3_dsf1": dict(act_ps=real_act(3), window_style="Normal", args=WINDOW + ["--force-device-scale-factor=1"]),
    "cdp100": dict(act_ps=cdp_act(100), args=WINDOW),
    "cdp300": dict(act_ps=cdp_act(300), args=WINDOW),
}

HOST_FACTS = rf"""
"WHEELLINES=" + (Get-ItemProperty 'HKCU:\Control Panel\Desktop').WheelScrollLines
"APPLIEDDPI=" + (Get-ItemProperty 'HKCU:\Control Panel\Desktop\WindowMetrics' -ErrorAction SilentlyContinue).AppliedDPI
"CHROMEVER=" + (Get-Item '{winhost.CHROME}').VersionInfo.ProductVersion
"""


def summarize(log):
    w, s = log["wheel"], log["scroll"]
    return {
        "n_wheel": len(w),
        "dy": [e["dy"] for e in w],
        "wdy": [e["wdy"] for e in w],
        "modes": sorted({e["mode"] for e in w}),
        "trusted": all(e["trusted"] for e in w),
        "n_scroll": len(s),
        "scroll_ms": round(s[-1]["t"] - s[0]["t"]) if len(s) > 1 else 0,
        "final_y": s[-1]["y"] if s else 0,
        "dpr": log["dpr"],
    }


def _ratios(s):
    return [round(w / d, 3) for w, d in zip(s["wdy"], s["dy"]) if d]


def red_gate(arms):
    real, cdp = arms["real3"], arms["cdp300"]
    if real["n_wheel"] == 0:
        return ["real3: no wheel event reached the page (window not under the cursor, or SendInput failed)"]
    problems = []
    if real["n_wheel"] == cdp["n_wheel"]:
        problems.append(f"event count equal ({real['n_wheel']}): count does not separate the arms")
    if (ratios := _ratios(real)) == _ratios(cdp):
        problems.append(f"wheelDeltaY/deltaY ratios equal ({ratios})")
    if real["n_scroll"] == cdp["n_scroll"]:
        problems.append(f"scroll event counts equal ({real['n_scroll']}): no animation difference seen")
    return problems


EXACT = ["n_wheel", "dy", "wdy", "modes", "trusted", "final_y", "dpr"]
# The real arms themselves animate over 9-12 scroll events and 191-266 ms
# for 1-3 notches, so the animation leaves are a band around the real arm.
ANIMATION_BAND = (0.5, 1.5)


def compare(fork, real):
    """Each leaf where the fork's summary does not read like the real wheel's."""
    if real["n_wheel"] == 0:
        raise ValueError("the real arm saw no wheel event: nothing to compare against")
    problems =[f"{k}: fork {fork[k]} vs real {real[k]}" for k in EXACT if fork[k] != real[k]]
    lo, hi = ANIMATION_BAND
    for k in ("n_scroll", "scroll_ms"):
        if not lo * real[k] <= fork[k] <= hi * real[k]:
            problems.append(f"{k}: fork {fork[k]} outside {lo}-{hi} x real {real[k]}")
    return problems


def fork_arms(exe):
    """SP2c's host-native arm: the fork's chrome.exe scrolled over CDP, with
    humanize on and off (off is the RED: it must not read like the real wheel)."""
    real = json.loads(OUT.read_text())["arms"]["real3"]["summary"]
    verdict = 0
    for name, on in (("fork_off", False), ("fork_on", True)):
        # Explicit false, not an absent key: the session could carry a config of its own.
        env = {"CAMOU_CONFIG_STRICT": "1", "CAMOU_CONFIG": json.dumps({"humanize:enabled": on})}
        try:
            s = summarize(winhost.cdp_eval(PAGE, expression=EXPR, wait_ms=2500, act_ps=cdp_act(300),
                                           args=WINDOW, window_style="Normal", exe=exe, env=env))
        except (RuntimeError, gpu_gate.GpuCrashed) as e:
            print(f"UNMEASURED {name}: {e}")
            return 3
        problems = compare(s, real)
        print(name, json.dumps(s, sort_keys=True), flush=True)
        for p in problems:
            print("   ", p)
        if not on and (s["n_wheel"] == 0 or not problems):
            print("RED-GATE fork_off saw no wheel event or reads like the real wheel: measured nothing")
            return 2
        if on:
            verdict = 1 if problems else 0
            print("PASS" if not problems else f"FAIL {len(problems)} leaf/leaves", "fork_on vs real3")
    return verdict


def main():
    if "--fork" in sys.argv:
        if len(sys.argv) != 3 or sys.argv[1] != "--fork":
            print("usage: capture_wheel_oracle.py --fork <chrome.exe>")
            return 2
        return fork_arms(sys.argv[2])
    facts =dict(line.split("=", 1) for line in winhost.powershell(HOST_FACTS).splitlines() if "=" in line)
    arms = {}
    for name, kw in ARMS.items():
        raw = winhost.cdp_eval(PAGE, expression=EXPR, wait_ms=2500, **kw)
        arms[name] = {"log": raw, "summary": summarize(raw)}
        print(name, json.dumps(arms[name]["summary"]), flush=True)
    problems = red_gate({k: v["summary"] for k, v in arms.items()})
    for p in problems:
        print("RED-GATE", p)
    if problems:
        return 1
    OUT.write_text(json.dumps({"host": facts, "arms": arms}, indent=1, sort_keys=True) + "\n")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
