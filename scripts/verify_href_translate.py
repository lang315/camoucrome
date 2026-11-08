"""HTMLAnchorElement.prototype.hrefTranslate on the fork's chrome (Finch gap item B2).

Stock Chrome exposes hrefTranslate (HrefTranslate is stable and depends on the
TranslateService runtime feature, which //chrome switches on from
translate_service_available). The fork has no Google API key, so
TranslateService::IsAvailable was false and the attribute was missing; the patch
href-translate-without-key sets the web preference from the "Offer to translate"
preference alone. It must not make translate itself work: no key, so no translate
bubble and no request to a translate host.

Every run is this one binary. The control run adds --disable-blink-features=HrefTranslate,
which is the state of the binary before the patch as far as a page can tell.

V0 RED by construction: the control run reports the attribute absent. A V1 that
   passed there would measure nothing.
V1 normal run: 'hrefTranslate' is an accessor (get and set) on the prototype,
   getter and setter print [native code], Object.keys(window) equals the control's.
V2 the attribute reflects: default '', set 'fr' -> attribute 'fr', removeAttribute -> ''.
V3 no new network: click a link carrying hrefTranslate in both runs (the link did
   navigate, both servers saw /next), record every URL the browser requested
   (--log-net-log) and require hosts(normal) - hosts(control) empty, and no host
   with "translate" in it in the normal run. Compared with the control run, not
   with a fixed list, so a background request both runs make does not matter.

Run with the chrome binary (lib_shell.CHROME, CAMOU_EXE overrides); content_shell
cannot see the patch.
"""
import hashlib
import http.server
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.parse

import lib_shell

PAGE = (b"<!doctype html><html lang='fr'><title>t</title><body>"
        b"<p>Bonjour tout le monde, ceci est une page en francais.</p>"
        b"<a id='a' href='/next' hrefTranslate='de'>next</a></body></html>")
NEXT = b"<!doctype html><title>next</title><p>next</p>"

PROBE = """() => {
  const p = HTMLAnchorElement.prototype;
  const d = Object.getOwnPropertyDescriptor(p, 'hrefTranslate');
  const a = document.createElement('a');
  const before = a.hrefTranslate;
  a.hrefTranslate = 'fr';
  const attrSet = a.getAttribute('hrefTranslate');
  const afterSet = a.hrefTranslate;
  a.removeAttribute('hrefTranslate');
  return {
    has: 'hrefTranslate' in p,
    accessor: !!(d && d.get && d.set),
    getStr: d && d.get ? Function.prototype.toString.call(d.get) : null,
    setStr: d && d.set ? Function.prototype.toString.call(d.set) : null,
    keys: Object.keys(window).join(','),
    before, attrSet, afterSet, afterRemove: a.hrefTranslate,
  };
}"""


def serve():
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            body = NEXT if self.path == "/next" else PAGE
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen


def hosts_in(netlog_path):
    """Hosts of every URL the netlog names. Tolerant: the file is cut when the browser is terminated."""
    text = open(netlog_path, errors="replace").read()
    text = text.split('"events":', 1)[-1]
    urls = set(re.findall(r'"url":"([^"]+)"', text))
    return {urllib.parse.urlsplit(u).hostname or u for u in urls}


def run(extra):
    srv, seen = serve()
    netlog = tempfile.mktemp(prefix="href-translate-netlog-")
    flags = lib_shell.CHROME_FLAGS + ["--enable-logging=stderr", f"--log-net-log={netlog}"] + extra
    proc = None
    try:
        proc = lib_shell.launch(None, shell=lib_shell.CHROME, extra_flags=flags)
        url = f"http://127.0.0.1:{srv.server_port}/"
        probe = lib_shell.evaluate(proc, [PROBE, "() => document.getElementById('a').click()"], navigate_to=url)
        time.sleep(3)  # let the click navigate and its requests reach the log
    finally:
        if proc is not None:
            lib_shell.shutdown(proc)
        srv.shutdown()
    hosts = hosts_in(netlog) if os.path.exists(netlog) else None
    if os.path.exists(netlog):
        os.unlink(netlog)
    return probe[0], hosts, list(seen)


def main():
    lines = []

    def check(name, ok, detail=""):
        lines.append(f"{'PASS' if ok else 'FAIL'}  {name} {detail}".rstrip())

    try:
        on, hosts_on, seen_on = run([])
        off, hosts_off, seen_off = run(["--disable-blink-features=HrefTranslate"])
    except Exception as exc:  # noqa: BLE001 - any fault is UNMEASURED, never a pass
        print(f"UNMEASURED  {type(exc).__name__}: {exc}")
        return 2

    check("V0 control run has no hrefTranslate (RED by construction)", not off["has"], f"has={off['has']}")
    check("V1 hrefTranslate is an accessor on HTMLAnchorElement.prototype", on["has"] and on["accessor"],
          f"has={on['has']} accessor={on['accessor']}")
    check("V1 getter and setter are [native code]",
          bool(on["getStr"]) and bool(on["setStr"]) and "[native code]" in on["getStr"] and "[native code]" in on["setStr"],
          f"get={on['getStr']!r} set={on['setStr']!r}")
    check("V1 Object.keys(window) equals the control's", on["keys"] == off["keys"],
          hashlib.sha256(on["keys"].encode()).hexdigest()[:12] + " vs " + hashlib.sha256(off["keys"].encode()).hexdigest()[:12])
    check("V2 reflects", (on["before"], on["attrSet"], on["afterSet"], on["afterRemove"]) == ("", "fr", "fr", ""),
          f"{(on['before'], on['attrSet'], on['afterSet'], on['afterRemove'])}")

    navigated = "/next" in seen_on and "/next" in seen_off
    if hosts_on is None or hosts_off is None or not navigated:
        lines.append(f"UNMEASURED  V3 netlog or navigation missing (netlog on={hosts_on is not None} off={hosts_off is not None}, "
                     f"/next seen on={'/next' in seen_on} off={'/next' in seen_off})")
    else:
        extra = sorted(hosts_on - hosts_off)
        translate = sorted(h for h in hosts_on if "translate" in h)
        check("V3 no host requested by the normal run that the control did not request", not extra,
              f"extra={extra} normal={len(hosts_on)} control={len(hosts_off)}")
        check("V3 no translate host in the normal run", not translate, f"{translate}")
    print("\n".join(lines))
    if any(l.startswith("UNMEASURED") for l in lines):
        return 2
    return 1 if any(l.startswith("FAIL") for l in lines) else 0


if __name__ == "__main__":
    sys.exit(main())
