"""measure_page_feel: the page copy, the window rates and the verdicts, on synthetic records (no browser)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import measure_page_feel as P  # noqa: E402


def snap(idle_rate, move_rate, windows=20):
    """A run's log: `windows` 50 ms windows idle, then move, counting at the given rates (counts per ms)."""
    ev, cnt, t = [], 0.0, 0.0
    for ph, rate in (("idle", idle_rate), ("move", move_rate)):
        for _ in range(windows + 1):
            ev.append({"t": "spin", "cnt": cnt, "tms": t, "ph": ph})
            cnt += rate * 50
            t += 50
    return {"ev": ev}


def test_page_copy_keeps_the_probe_script_and_adds_the_worker():
    page = P.page_with_worker(3)
    assert "const N = 3;" in page and "SharedArrayBuffer" in page and page.rstrip().endswith("</script>")
    assert "__WORKERS__" not in page and "hardwareConcurrency" in P.page_with_worker(0)


def test_ratio_is_move_over_idle_and_needs_windows():
    assert abs(P.ratio(snap(100.0, 95.0)) - 0.95) < 1e-9
    assert P.ratio(snap(100.0, 95.0, windows=3)) is None


def test_verdicts():
    ctl = [0.99, 1.00, 1.01, 1.00, 0.995, 1.005]
    assert P.judge(ctl, [1.0, 0.99, 1.01, 1.0, 1.0, 0.995])[0] == "PASS"
    assert P.judge(ctl, [0.80, 0.81, 0.79, 0.80, 0.82, 0.80])[0] == "FAIL"      # a 20 % loss of the counter
    assert P.judge(ctl, [1.0, 1.0])[0] == "UNMEASURED"
