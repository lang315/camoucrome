"""pwdrive: the driver probes through our Python client (camoucrome.launcher.launch on patchright).
Same CLI and result file as the Go drivers; modes l9 and headers only."""
import argparse
import json
import pathlib
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "client" / "python"))
from camoucrome import launcher  # noqa: E402


def acts(page):
    return {
        "focus": ("Page.focus", lambda: page.focus("#a")),
        "type": ("Page.type", lambda: page.type("#a", "ab")),
        "blur": ("Locator.blur", lambda: page.locator("#a").blur()),
        "click": ("Page.click", lambda: page.click("#btn")),
        "select": ("Locator.select_text", lambda: page.locator("#a").select_text()),
        "scroll": ("Mouse.wheel", lambda: (page.mouse.move(70, 160), page.mouse.wheel(0, 40))),
    }


def route(page, cond):
    """Returns the undo; the override rebuilds the header dict, as a Playwright user does."""
    if cond == "plain":
        return lambda: None
    if cond == "route":
        page.route("**/*", lambda r: r.continue_())
    else:
        page.route("**/*", lambda r: r.continue_(headers={**r.request.headers, "X-Probe": "1"}))
    return lambda: page.unroute("**/*")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--mode", required=True, choices=["l9", "headers"])
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--args-json")
    ap.add_argument("--env-json")
    a = ap.parse_args()
    res = {"driver": "patchright", "acts": {}, "error": None, "text": None, "methods": {}}
    from patchright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = launcher.launch(pw, a.exe, user_data_dir=a.profile, headless=False)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(a.url, wait_until="load")
            if a.mode == "l9":
                page.wait_for_selector("#ready", state="attached")
                for name, (via, fn) in acts(page).items():
                    try:
                        fn()
                        res["acts"][name] = "ok:" + via
                    except Exception as e:  # noqa: BLE001 - recorded, the next action still runs
                        res["acts"][name] = f"error:{type(e).__name__}: {e}"[:200]
                    page.wait_for_timeout(400)
                page.wait_for_timeout(1500)
            else:
                u = urllib.parse.urlparse(a.url)
                for cond in ("plain", "route", "override"):
                    undo = route(page, cond)
                    res["acts"][cond] = "ok:route"
                    page.goto(u._replace(query="c=" + cond).geturl(), wait_until="load")
                    page.wait_for_timeout(3500)  # not time.sleep: the sync API runs route handlers only while it is pumped
                    undo()
        except Exception as e:  # noqa: BLE001
            res["error"] = f"{type(e).__name__}: {e}"[:300]
        finally:
            ctx.close()
    pathlib.Path(a.out).write_text(json.dumps(res))
    return 1 if res["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
