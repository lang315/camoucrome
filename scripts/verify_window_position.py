"""Step 6 Task 6: the real window sits where window.screenX/Y say.

Per seed 1..5: generate a Windows identity, launch headed through the package
launcher, read the window's real bounds over CDP (Browser.getWindowForTarget on
the page's own session; no Runtime.enable) and window.screenX/Y from the page,
and compare. Expected: "5 of 5 seeds: bounds == reported".

RED: --no-position drops launch["position"] (the old launcher). Expected at
least 4 of 5 seeds differ. Run on the host in session 1 after the GPU-crash
gate; needs patchright and a chrome binary:

    python3 scripts/verify_window_position.py --executable <chrome> [--no-position]
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "client" / "python"))

SEEDS = range(1, 6)


def agree(bounds, reported):
    """True when CDP's (left, top) equals the page's (screenX, screenY)."""
    return (bounds["left"], bounds["top"]) == (reported[0], reported[1])


def tally(rows):
    """rows: [(seed, bounds, reported)] -> (agreeing, total)."""
    return sum(agree(b, r) for _, b, r in rows), len(rows)


def measure(exe, seed, use_position):
    from patchright.sync_api import sync_playwright
    from camoucrome import gen, launch
    g = gen.generate("windows", timezone="Europe/Paris", seed=seed)
    opts = {"window": g["launch"]["window"], "dpr": g["launch"]["dpr"]}
    if use_position:
        opts["position"] = g["launch"]["position"]
    with sync_playwright() as pw:
        ctx = launch(pw, exe, config=g["config"], headless=False, args=g["launch"]["args"], **opts)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("about:blank")
            bounds = ctx.new_cdp_session(page).send("Browser.getWindowForTarget")["bounds"]
            reported = page.evaluate("[window.screenX, window.screenY]")
            return seed, bounds, reported
        finally:
            ctx.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--executable", required=True)
    ap.add_argument("--no-position", action="store_true", help="RED: the old launcher, no --window-position")
    a = ap.parse_args()
    rows = [measure(a.executable, s, not a.no_position) for s in SEEDS]
    for seed, b, r in rows:
        print(f"seed {seed}: bounds ({b['left']}, {b['top']}) reported ({r[0]}, {r[1]})")
    ok, n = tally(rows)
    print(f"{ok} of {n} seeds: bounds == reported")
    want = (n - 4 >= ok) if a.no_position else (ok == n)  # RED: at least 4 of 5 differ
    sys.exit(0 if want else 1)


if __name__ == "__main__":
    main()
