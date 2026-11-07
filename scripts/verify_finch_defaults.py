"""finch-stable-defaults: the fork matches stock Chrome 156 on the features stock's variations seed changes.

Stock Chrome gets these from its Finch seed; the fork has no seed and builds with
disable_fieldtrial_testing_config, so it runs Chromium's compiled defaults. Expected values are
what stock 156.0.8078.80 (seeded) measured on 2026-11-07
(docs/superpowers/measurements/2026-11-07-finch-feature-gap.md). No config key: stock behaves
this way for every user, so nothing is spoofed (rule 5 is not involved).

Raw `chrome` (stock with the two env words above), no CAMOU_CONFIG, a loopback http page (a secure context).
RED on a build without the finch-stable-defaults patch: F1-F5b FAIL.

F1  XMLRustForNonXslt off: DOMParser reports libxml2's text, "Opening and ending tag mismatch".
F2  BrowsingTopics off: no document.browsingTopics, no browsing-topics / interest-cohort policy.
F3  Fledge + AdInterestGroupAPI off: none of the 13 ad-auction Navigator members.
F4  ConversionMeasurement off: no attributionSrc on a/area/img/script, no setAttributionReporting.
F5a DeprecateUnload on: 'unload' is not in document.featurePolicy.allowedFeatures().
F5b the same, in behaviour: an unload handler does not run on a top-level navigation
    (a pagehide beacon does, so the navigation happened and beacons work).
F7  the levers still work: --enable-features=BrowsingTopics,ConversionMeasurement,Fledge,
    AdInterestGroupAPI,XMLRustForNonXslt turns those five back on, and
    --disable-features=DeprecateUnload brings 'unload' back (RED for a flip that hard-codes it).
F8  the five Blink flags stay off under --enable-experimental-web-platform-features (chrome://flags
    "Experimental Web Platform features"), as in stock: they are "test" status, not "experimental"
    (RED on the experimental-status build: the flag turned all five back on in the fork).
F6  ConfigureQuicHints on (HOST ONLY, needs the internet; CAMOU_FINCH_QUIC=1): a cold profile's
    first navigation to https://www.google.com/robots.txt negotiates h3.
"""
import http.server
import os
import sys
import threading
import time

import lib_shell

QUIC = os.environ.get("CAMOU_FINCH_QUIC") == "1"
# The stock control: CAMOU_EXE=<stock chrome.exe> CAMOU_FINCH_PROFILE=<a profile that has fetched its
# seed>. Without a seed, stock runs compiled defaults too and the control would measure nothing.
PROFILE = os.environ.get("CAMOU_FINCH_PROFILE") or None
EXPECTED_ROWS = 9 if QUIC else 8

NAV_MEMBERS = ["joinAdInterestGroup", "leaveAdInterestGroup", "runAdAuction", "updateAdInterestGroups",
               "clearOriginJoinedAdInterestGroups", "createAuctionNonce", "canLoadAdAuctionFencedFrame",
               "deprecatedURNToURL", "deprecatedReplaceInURN", "getInterestGroupAdAuctionData",
               "adAuctionComponents", "protectedAudience", "deprecatedRunAdAuctionEnforcesKAnonymity"]
PAGE = (b"<!doctype html><title>finch</title><script>"
        b"addEventListener('unload', () => navigator.sendBeacon('/unloaded'));"
        b"addEventListener('pagehide', () => navigator.sendBeacon('/pagehide'));"
        b"</script>")

F1 = "new DOMParser().parseFromString('<a><b></a>', 'text/xml').querySelector('div').textContent"
F2 = ("[('browsingTopics' in document), document.featurePolicy.features().filter(f => "
      "f == 'browsing-topics' || f == 'interest-cohort')]")
F3 = f"{NAV_MEMBERS!r}.filter(n => n in navigator)"
F4 = ("[['HTMLAnchorElement', 'HTMLAreaElement', 'HTMLImageElement', 'HTMLScriptElement']"
      ".filter(n => 'attributionSrc' in window[n].prototype), 'setAttributionReporting' in XMLHttpRequest.prototype]")
F5 = "document.featurePolicy.allowedFeatures().includes('unload')"
NAVIGATE = "setTimeout(() => { location.href = '/other'; }, 0); 1"


def serve():
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            self.wfile.write(PAGE)

        def do_POST(self):
            seen.append(self.path)
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}/", seen, server


def probes():
    url, seen, server = serve()
    proc = None
    try:
        proc = lib_shell.launch("{}", shell=lib_shell.CHROME, extra_flags=lib_shell.CHROME_FLAGS, user_data_dir=PROFILE)
        values = lib_shell.evaluate(proc, [F1, F2, F3, F4, F5], navigate_to=url)
        lib_shell.evaluate(proc, [NAVIGATE])
        time.sleep(3)
        return values, list(seen), None
    except Exception as exc:  # noqa: BLE001 - any fault must become a FAIL
        return None, [], str(exc)[:200]
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)
        server.shutdown()
        server.server_close()


OVERRIDE = ["--enable-features=BrowsingTopics,ConversionMeasurement,Fledge,AdInterestGroupAPI,XMLRustForNonXslt",
            "--disable-features=DeprecateUnload"]
F7 = ("[new DOMParser().parseFromString('<a><b></a>', 'text/xml').querySelector('div').textContent.includes('Unexpected closing tag'),"
      " 'browsingTopics' in document, 'attributionSrc' in HTMLAnchorElement.prototype,"
      " 'joinAdInterestGroup' in navigator, document.featurePolicy.allowedFeatures().includes('unload')]")


def overridden():
    """The same page with the base features named on the command line."""
    url, _, server = serve()
    proc = None
    try:
        proc = lib_shell.launch("{}", shell=lib_shell.CHROME, extra_flags=lib_shell.CHROME_FLAGS + OVERRIDE, user_data_dir=PROFILE)
        return lib_shell.evaluate(proc, [F7], navigate_to=url)[0], None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)[:200]
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)
        server.shutdown()
        server.server_close()


def experimental():
    """F1-F4's expressions under the experimental web platform switch. Stock ignores it for these five."""
    url, _, server = serve()
    proc = None
    try:
        proc = lib_shell.launch("{}", shell=lib_shell.CHROME,
                                extra_flags=lib_shell.CHROME_FLAGS + ["--enable-experimental-web-platform-features"],
                                user_data_dir=PROFILE)
        return lib_shell.evaluate(proc, [F1, F2, F3, F4], navigate_to=url), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)[:200]
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)
        server.shutdown()
        server.server_close()


def quic():
    """Cold profile, first load of www.google.com: the protocol the navigation negotiated."""
    proc = None
    try:
        proc = lib_shell.launch("{}", shell=lib_shell.CHROME, extra_flags=lib_shell.CHROME_FLAGS, user_data_dir=PROFILE)
        return lib_shell.evaluate(
            proc, ["performance.getEntriesByType('navigation')[0].nextHopProtocol"],
            navigate_to="https://www.google.com/robots.txt")[0], None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)[:200]
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)


def rows():
    values, seen, err = probes()
    v = values or [None] * 5
    yield "F1 DOMParser error text is libxml2's", isinstance(v[0], str) and "Opening and ending tag mismatch" in v[0], (v[0], err)
    yield "F2 no browsingTopics, no topics policy features", v[1] == [False, []], (v[1], err)
    yield "F3 none of the 13 ad-auction Navigator members", v[2] == [], (v[2], err)
    yield "F4 no attributionSrc, no setAttributionReporting", v[3] == [[], False], (v[3], err)
    yield "F5a 'unload' not in allowedFeatures()", v[4] is False, (v[4], err)
    yield ("F5b unload handler does not run on navigation (pagehide beacon does)",
           err is None and "/pagehide" in seen and "/unloaded" not in seen, (seen, err))
    on, oerr = overridden()
    yield "F7 --enable-features/--disable-features turn the six back on", on == [True] * 5, (on, oerr)
    ex, eerr = experimental()
    ex = ex or [None] * 4
    yield ("F8 the five flags stay off under --enable-experimental-web-platform-features",
           isinstance(ex[0], str) and "Opening and ending tag mismatch" in ex[0] and ex[1] == [False, []] and ex[2] == []
           and ex[3] == [[], False], (ex, eerr))
    if QUIC:
        proto, qerr = quic()
        yield "F6 first load of www.google.com is h3 (host only)", proto == "h3", (proto, qerr)


def main():
    results = list(rows())
    for name, ok, seen in results:
        print(f"{'PASS' if ok else 'FAIL'} {name}" + ("" if ok else f" (seen, error) = {seen!r}"))
    if len(results) != EXPECTED_ROWS:  # a dropped row must fail
        print(f"FAIL expected {EXPECTED_ROWS} rows, ran {len(results)}")
        return 1
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
