"""The Device-Memory client hints carry the value navigator.deviceMemory reads.

Raw `chrome` (content_shell may have no ClientHintsControllerDelegate and send
no hint at all), CAMOU_CONFIG, a loopback origin (a secure context). The root
answers with Accept-CH and Critical-CH, so the navigation is retried with the
hint; the page then fetches /sub and starts a dedicated worker that fetches /w.
Two arms: N (no config) and C (navigator.deviceMemory 4, which differs from any
real value of 8 or more). RED on a build whose hint reads the real memory: H1
and H2 send the real value in arm C while JS reads 4.

H0 arm C's JS reads 4 and arm N's does not (else the arms cannot differ).
H1 the retried navigation sends both hints, equal to JS, in both arms.
H2 the subresource sends both hints, equal to JS, in both arms.
H3 the worker fetch: arm N decides whether stock sends the hint there; arm C
   must match that presence and, when sent, equal the worker's deviceMemory.
H4 the first navigation request (before opt-in) sends neither hint.
G (not a row) ns per navigator.deviceMemory read, per arm.
"""
import http.server
import json
import sys
import threading

import lib_shell

EXPECTED_ROWS = 5
NAMES = ("sec-ch-device-memory", "device-memory")

PAGE = """async () => {
  await fetch('/sub');
  const src = 'onmessage = async e => { await fetch(e.data + "/w");' +
              ' postMessage(navigator.deviceMemory); };';
  const w = new Worker(URL.createObjectURL(new Blob([src])));
  const wjs = await new Promise(r => { w.onmessage = e => r(e.data); w.postMessage(location.origin); });
  let s = 0;
  const t0 = performance.now();
  for (let i = 0; i < 1000000; i++) s += navigator.deviceMemory;
  const ns = (performance.now() - t0) * 1e6 / 1000000;
  return JSON.stringify({js: navigator.deviceMemory, wjs, ns, s});
}"""


def run(config):
    records = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            records.append((self.path, {k.lower(): v for k, v in self.headers.items()}))
            self.send_response(200)
            self.send_header("Accept-CH", "Sec-CH-Device-Memory, Device-Memory")
            self.send_header("Critical-CH", "Sec-CH-Device-Memory")
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<!doctype html><title>dm</title>")

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        values, err = lib_shell.session(json.dumps(config) if config else None, [PAGE],
                                        navigate_to=f"http://127.0.0.1:{server.server_port}/",
                                        shell=lib_shell.CHROME, extra_flags=lib_shell.CHROME_FLAGS)
    finally:
        server.shutdown()
        server.server_close()
    if err is not None or not values or values[0] is None:
        return None, records, str(err)[:200]
    return json.loads(values[0]), records, None


def hints(records, path, which):
    """The hint headers of the first (0) or last (-1) request to path, or None."""
    hits = [h for p, h in records if p == path]
    if not hits:
        return None
    return {n: hits[which].get(n) for n in NAMES}


def fmt(v):
    return "%g" % v


def rows():
    arms = {name: run(cfg) for name, cfg in (("N", None), ("C", {"navigator.deviceMemory": 4}))}
    for name, (page, records, err) in arms.items():
        print(f"  arm {name}: page {page}, error {err}")
        for path in ("/", "/sub", "/w"):
            print(f"    {path}: first {hints(records, path, 0)}, last {hints(records, path, -1)}")
    n, c = arms["N"][0], arms["C"][0]
    ok = n is not None and c is not None
    if ok:
        print(f"  G navigator.deviceMemory ns/read: N {n['ns']:.1f}, C {c['ns']:.1f}")
    yield "H0 arm C's JS reads 4 and arm N's does not", ok and c["js"] == 4 and n["js"] != 4, (n, c)

    def same(path, key):
        return all(a is not None and hints(r, path, -1) == {k: fmt(a[key]) for k in NAMES}
                   for a, r, _ in arms.values())
    yield "H1 the retried navigation sends both hints, equal to JS, in both arms", ok and same("/", "js"), None
    yield "H2 the subresource sends both hints, equal to JS, in both arms", ok and same("/sub", "js"), None
    wn, wc = hints(arms["N"][1], "/w", -1), hints(arms["C"][1], "/w", -1)
    present = wn is not None and any(wn.values())
    h3 = ok and wn is not None and wc is not None and (
        (present and wn == {k: fmt(n["wjs"]) for k in NAMES} and wc == {k: fmt(c["wjs"]) for k in NAMES})
        or (not present and not any(wc.values())))
    print(f"  H3 stock sends the hint from a worker: {present}")
    yield "H3 the worker fetch matches stock's presence and, when sent, equals the worker's value", h3, None
    yield "H4 the first navigation request sends neither hint", ok and all(
        hints(r, "/", 0) == {k: None for k in NAMES} for _, r, _ in arms.values()), None


def main():
    results = list(rows())
    for name, ok, seen in results:
        print(f"{'PASS' if ok else 'FAIL'} {name}" + ("" if ok or seen is None else f" {seen!r}"))
    if len(results) != EXPECTED_ROWS:
        print(f"FAIL expected {EXPECTED_ROWS} rows, ran {len(results)}")
        return 1
    if all(ok for _, ok, _ in results):
        print("ALL_PASS")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
