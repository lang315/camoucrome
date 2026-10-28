#!/usr/bin/env python3
"""Item 13 on the Windows host: Pixelscan flags a time zone that contradicts the exit IP ("Timezone spoofed"); an
identity generated from the exit IP is not flagged (spec 2026-10-24-step5-layer3-design.md, 8.8).

Run in the interactive session (run-interactive.ps1; tell mygo first), in the client venv with camoucrome[geoip]:
  python verify_geoip_pixelscan.py [--red-zone Asia/Tokyo]
Needs CAMOU_FORK_EXE, CAMOU_GEOIP_DB (a DB-IP Lite file on the host, outside any repo), and the stock Chrome of
measure_step2. Three loads of one page, one session: stock (must not be flagged: else the page flags something else and
the other two prove nothing), the fork with a contradicting zone (RED: must be flagged), the fork generated from the host's
own exit IP (GREEN: must not). Prints verdicts only -- never the IP, zone or country of the host."""
import argparse
import os
import re
import sys

SPOOFED = re.compile(r"Timezone spoofed", re.I)


def verdict(stock, red, green):
    """(exit code, line). A text of None never settled: UNMEASURED, neither pass nor fail."""
    if None in (stock, red, green):
        return 3, "UNMEASURED: a Pixelscan load never settled"
    flagged = lambda t: bool(SPOOFED.search(t))  # noqa: E731
    if flagged(stock):
        return 1, "FAIL: stock Chrome is flagged too, so the page flags something else and RED/GREEN prove nothing"
    if not flagged(red):
        return 1, "FAIL: RED did not trip -- a contradicting zone is not flagged, this check measures nothing"
    if flagged(green):
        return 1, "FAIL: the identity generated from the exit IP is still flagged"
    return 0, "PASS: stock clean, contradicting zone flagged (RED), zone from the exit IP clean (GREEN)"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--red-zone", help="default: Asia/Tokyo, or America/Los_Angeles if that is the host's own zone")
    a = ap.parse_args(argv)
    import gpu_gate
    gpu_gate.require_interactive()
    from patchright.sync_api import sync_playwright
    import measure_step2 as m2
    from camoucrome import gen, geoip
    db = os.environ["CAMOU_GEOIP_DB"]
    ip = geoip.exit_ip()
    zone = geoip.lookup(ip, db)["timezone"]
    red_zone = a.red_zone or ("Asia/Tokyo" if zone != "Asia/Tokyo" else "America/Los_Angeles")
    if geoip.check_zone(red_zone, zone) is None:
        sys.exit(f"precondition: --red-zone {red_zone} has the host's UTC offset; pick a zone that contradicts it")
    stock = os.path.join(os.environ.get("CAMOU_STOCK_APP", m2.STOCK_APP), "chrome.exe")
    arms = {"stock": m2.Arm("stock", stock, None),
            "red": m2.Arm("red", os.environ["CAMOU_FORK_EXE"], gen.generate("windows", seed=1, timezone=red_zone)),
            "green": m2.Arm("green", os.environ["CAMOU_FORK_EXE"], gen.generate("windows", seed=1, exit_ip=ip, geoip_db=db))}
    print("exit IP resolved; identities generated")
    texts = {}
    with sync_playwright() as pw:
        for name, arm in arms.items():
            with m2.opened(pw, arm, "headed") as ctx:
                page = m2.first_page(ctx)
                page.goto(m2.DETECTORS["pixelscan"], wait_until="load", timeout=60000)
                texts[name] = m2.settle(page)
            print(f"{name}: {'settled' if texts[name] is not None else 'never settled'}")
    code, line = verdict(texts["stock"], texts["red"], texts["green"])
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
