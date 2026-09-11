"""SP7 phone-home verify: a fresh headless `chrome` on about:blank makes NO
outbound request to a non-loopback host within the observation window.

P1 zero outbound hosts (RED build, measured 2026-09-09: 8 hosts -- component
   updater + gvt1 downloads, GCM checkin/register3, accounts ListAccounts,
   network time, omnibox AIM eligibility, spellcheck dictionary).
P2 probe capability: the same netlog carries >= 1 loopback request -- the
   page is navigated to a local echo server right after launch, so chrome
   itself issues one URLRequest we can see (the DevTools /json/version poll
   is INBOUND and never appears in the netlog; the first draft assumed it
   would). An empty host set is then not an empty capture. Assert presence
   before absence.
P3 control: the fork's config layer still works on this binary
   (navigator.hardwareConcurrency override), so P1 is about THIS build.

Mechanism: --log-net-log writes every URLRequest (REQUEST_ALIVE carries the
URL) regardless of DNS or TLS outcome, so this measures intent to connect,
not reachability -- a box with no route still reports the attempt. The
window is WINDOW_SECONDS after the DevTools port answers; the RED capture
showed every caller firing within 2.5 s and the component updater's second
wave at ~60 s, so 75 s covers both.

Measurement: docs/superpowers/measurements/2026-09-09-sp7-phone-home.md
P4 X-Client-Data on google.com over two launches on one profile: absent both
   times (stock sends it on the second launch, from the seed the first stored).
"""
import json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import echo_server
import lib_shell

WINDOW_SECONDS = int(os.environ.get("SP7_PHONEHOME_WINDOW", "75"))
NETLOG = f"/tmp/camoucrome_sp7_netlog.{os.getpid()}.json"
LOOPBACK = re.compile(r"^(127\.\d+\.\d+\.\d+|localhost|\[::1\])(:\d+)?$")

results = {}
notes = []


def parse_hosts(path):
    """Returns (external_hosts: {host: count}, loopback_count). A netlog cut
    off by process kill lacks its closing bracket; repair before parsing."""
    raw = open(path, "r", encoding="utf-8", errors="replace").read()
    if not raw.rstrip().endswith("}"):
        raw = raw.rstrip().rstrip(",") + "]}"
    d = json.loads(raw)
    types = {v: k for k, v in d["constants"]["logEventTypes"].items()}
    external, loopback = {}, 0
    for ev in d["events"]:
        if types.get(ev.get("type")) != "REQUEST_ALIVE":
            continue
        url = (ev.get("params") or {}).get("url")
        if not url:
            continue
        m = re.match(r"^[a-z]+://([^/?#]+)", url)
        if not m:
            continue
        host = m.group(1)
        if LOOPBACK.match(host):
            loopback += 1
        else:
            external[host] = external.get(host, 0) + 1
    return external, loopback


def run_p1_p2():
    if not os.path.exists(lib_shell.CHROME):
        results["P1"] = results["P2"] = False
        notes.append("P1/P2: no out/Default/chrome binary")
        return
    proc = stop = None
    try:
        base_url, _headers_for, stop = echo_server.start(lib_shell.ACCEPT_CH)
        proc = lib_shell.launch(
            None, shell=lib_shell.CHROME,
            extra_flags=[*lib_shell.CHROME_FLAGS, f"--log-net-log={NETLOG}",
                         "--net-log-capture-mode=Default"])
        # One loopback URLRequest, issued by chrome, for P2.
        lib_shell.evaluate(proc, ["1"], navigate_to=base_url)
        time.sleep(WINDOW_SECONDS)
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        results["P1"] = results["P2"] = False
        notes.append(f"P1/P2 launch: {type(exc).__name__}: {exc}")
        return
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)
        if stop is not None:
            stop()
    try:
        external, loopback = parse_hosts(NETLOG)
    except Exception as exc:  # noqa: BLE001
        results["P1"] = results["P2"] = False
        notes.append(f"P1/P2 netlog parse: {type(exc).__name__}: {exc}")
        return
    finally:
        try:
            os.remove(NETLOG)
        except OSError:
            pass
    results["P2"] = loopback >= 1
    if not results["P2"]:
        notes.append("P2: netlog holds no loopback request; P1's empty set is "
                     "not evidence")
    results["P1"] = results["P2"] and not external
    notes.append(f"P1: external hosts in {WINDOW_SECONDS}s = "
                 f"{json.dumps(dict(sorted(external.items())))} (expect {{}})")
    notes.append(f"P2: loopback requests = {loopback}")


def run_p3():
    vals, err = lib_shell.session(
        json.dumps({"navigator.hardwareConcurrency": 8}),
        ["navigator.hardwareConcurrency"], shell=lib_shell.CHROME,
        extra_flags=lib_shell.CHROME_FLAGS)
    if err is not None:
        results["P3"] = False
        notes.append(f"P3: {type(err).__name__}: {err}")
        return
    results["P3"] = vals[0] == 8
    notes.append(f"P3: hardwareConcurrency = {vals[0]} (expect 8)")


def run_p4():
    """X-Client-Data on a Google host (SP7 'still open', B1). Stock Chrome sends
    the header only from a profile that already holds a variations seed with
    ids, so a fresh profile proves nothing: measured 2026-09-11 on stock
    Chrome 153 on the box's Windows host, two launches on one temp profile,
    launch 1 -> no header on google.com/generate_204, launch 2 -> x-client-data
    present (scripts/winhost.py cdp_headers). The fork, same two-launch shape:
    no header either time, and no request to the variations/update hosts."""
    import tempfile
    from playwright.sync_api import sync_playwright
    prof = tempfile.mkdtemp(prefix="camoucrome-p4-")
    seen = []
    for launch in (1, 2):
        proc = None
        try:
            proc = lib_shell.launch(None, shell=lib_shell.CHROME,
                                    extra_flags=lib_shell.CHROME_FLAGS + [f"--user-data-dir={prof}"])
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{proc.cdp_port}")
                context = browser.contexts[0]
                page = context.pages[0] if context.pages else context.new_page()
                cdp = context.new_cdp_session(page)
                reqs, extra = {}, []
                cdp.on("Network.requestWillBeSent", lambda e: reqs.__setitem__(e["requestId"], e["request"]["url"]))
                cdp.on("Network.requestWillBeSentExtraInfo", lambda e: extra.append(e))
                cdp.send("Network.enable")
                try:
                    page.goto("https://www.google.com/generate_204", wait_until="load", timeout=30000)
                except Exception as nav:  # noqa: BLE001  204 No Content aborts the navigation; the request was sent
                    if "ERR_ABORTED" not in str(nav):
                        raise
                page.wait_for_timeout(20000 if launch == 1 else 8000)
                for e in extra:
                    seen.append((launch, reqs.get(e["requestId"], "?"), {k.lower() for k in e["headers"]}))
        except Exception as exc:  # noqa: BLE001
            notes.append(f"P4 launch {launch}: {type(exc).__name__}: {exc}")
            results["P4"] = False
            return
        finally:
            if proc is not None:
                lib_shell.shutdown(proc)
    hosts = sorted({re.match(r"^[a-z]+://([^/?#]+)", u).group(1) for _, u, _ in seen if re.match(r"^[a-z]+://([^/?#]+)", u)})
    xcd = [(l, u[:60]) for l, u, h in seen if "x-client-data" in h]
    bad_hosts = [h for h in hosts if h in ("clientservices.googleapis.com", "update.googleapis.com")]
    results["P4"] = bool(seen) and not xcd and not bad_hosts
    notes.append(f"P4: {len(seen)} requests over two launches on one profile, hosts={hosts}, x-client-data on {xcd} (stock M153: on launch 2), variations/update hosts {bad_hosts}")


def main():
    run_p1_p2()
    run_p3()
    run_p4()
    for n in notes:
        print("note:", n)
    ok = True
    for k in ("P1", "P2", "P3", "P4"):
        print(f"{k}: {'PASS' if results.get(k) else 'FAIL'}")
        ok = ok and bool(results.get(k))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
