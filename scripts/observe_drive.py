"""Driven arms of the facebook tracking map: capture on the host, names and matches out.

Spec: docs/superpowers/specs/2026-10-29-fb-tracking-map-design.md (local). Runs on the Windows
host in the observe venv (Python 3.12, patchright, the client). Values never leave the host:
channels.json and matches.json carry names, counts, value classes and surface matches only.
"""
import argparse
import base64
import binascii
import collections
import gzip
import hashlib
import http.server
import json
import pathlib
import random
import re
import sys
import threading
import time
import urllib.parse
import zlib

ID_RE = re.compile(r"^\d{10,}$")


class Opaque:
    """A value that is not text (a multipart file part): only its length is known, and only the length is kept."""

    def __init__(self, n):
        self.n = n


def value_class(v):
    if isinstance(v, Opaque):
        return f"opaque<{v.n}>"
    if isinstance(v, bool):
        return "bool"
    if v is None:
        return "null"
    if isinstance(v, int):
        return "id" if len(str(abs(v))) >= 10 else "int"
    if isinstance(v, float):
        return "float"
    s = str(v)
    return "id" if ID_RE.match(s) else f"str<{len(s)}>"


def _json(s):
    try:
        v = json.loads(s)
    except (ValueError, TypeError):
        return None
    return v if isinstance(v, (dict, list)) else None


def _inflate(raw):
    for f in (gzip.decompress, zlib.decompress, lambda b: zlib.decompress(b, -15)):
        try:
            return f(raw)
        except (OSError, EOFError, zlib.error):
            pass
    return raw


def _boundary(raw, content_type):
    m = re.search(r'boundary="?([^";,\s]+)"?', content_type or "", re.I)
    if m:
        return m.group(1).encode()
    first = raw.split(b"\r\n", 1)[0]
    if first.startswith(b"--") and 2 < len(first) <= 200 and b" " not in first:
        return first[2:]
    return None


def multipart_parts(raw, boundary):
    """[(name, value)] of a multipart/form-data body; a part with a filename, or bytes that are not text, is an Opaque."""
    parts = []
    for chunk in raw.split(b"--" + boundary)[1:]:
        if chunk.startswith(b"--"):
            break  # the closing delimiter
        head, sep, body = chunk.lstrip(b"\r\n").partition(b"\r\n\r\n")
        disp = re.search(rb"content-disposition:[^\r\n]*", head, re.I)
        name = re.search(rb'(?<![A-Za-z])name="([^"]*)"', disp.group(0)) if disp else None
        if not sep or not name:
            continue
        body = body[:-2] if body.endswith(b"\r\n") else body
        try:
            value = Opaque(len(body)) if b"filename=" in disp.group(0) else body.decode("utf-8")
        except UnicodeDecodeError:
            value = Opaque(len(body))
        parts.append((name.group(1).decode("utf-8", "replace"), value))
    return parts


def decode_body(raw, content_type="", _b64=True):
    raw = _inflate(raw)
    boundary = _boundary(raw, content_type)
    if boundary:
        parts = multipart_parts(raw, boundary)
        if parts:
            return "multipart", parts
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return "opaque", None
    j = _json(text)
    if j is not None:
        return "json", j
    # base64 before form: its '=' padding parses as a form key; a real form fails validate on '&' and '%'
    if _b64:
        try:
            inner = base64.b64decode(text.strip(), validate=True)
        except (binascii.Error, ValueError):
            inner = b""
        if inner and inner != raw:
            kind, v = decode_body(inner, _b64=False)
            if kind != "opaque":
                return kind, v
    if "=" in text and not text.lstrip().startswith(("{", "[")):
        pairs = urllib.parse.parse_qsl(text, keep_blank_values=True)
        if pairs:
            return "form", pairs
    return "opaque", None


def walk(value, prefix=""):
    """[(path, leaf)]: dict keys joined by '.', list items as '[]'; a string that is JSON is walked into."""
    if isinstance(value, dict):
        out = []
        for k, v in value.items():
            out += walk(v, f"{prefix}.{k}" if prefix else str(k))
        return out
    if isinstance(value, list):
        out = []
        for v in value:
            out += walk(v, prefix + "[]")
        return out
    if isinstance(value, str):
        j = _json(value)
        if j is not None:
            return walk(j, prefix)
    return [(prefix, value)]


def fields(raw, content_type=""):
    kind, v = decode_body(raw, content_type)
    if kind == "json":
        return kind, walk(v)
    if kind in ("form", "multipart"):
        out = []
        for k, val in v:
            out += walk(val, k)
        return kind, out
    return kind, []


MQTT_TYPES = {1: "CONNECT", 2: "CONNACK", 3: "PUBLISH", 4: "PUBACK", 8: "SUBSCRIBE", 9: "SUBACK",
              10: "UNSUBSCRIBE", 11: "UNSUBACK", 12: "PINGREQ", 13: "PINGRESP", 14: "DISCONNECT"}


def _varint(b, i):
    mult, val = 1, 0
    while True:
        c = b[i]
        i += 1
        val += (c & 127) * mult
        if not c & 128:
            return val, i
        mult *= 128
        if mult > 128 ** 3:
            raise ValueError("bad length")


def _mstr(b, i):
    n = int.from_bytes(b[i:i + 2], "big")
    if i + 2 + n > len(b):
        raise ValueError("truncated")
    return b[i + 2:i + 2 + n], i + 2 + n


def mqtt_packets(frame):
    out, i = [], 0
    try:
        while i < len(frame):
            t, flags = frame[i] >> 4, frame[i] & 15
            n, j = _varint(frame, i + 1)
            body, i = frame[j:j + n], j + n
            if len(body) != n or t not in MQTT_TYPES:
                return []
            p = {"type": MQTT_TYPES[t], "topic": "", "payload": b""}
            if t == 3:
                topic, k = _mstr(body, 0)
                if (flags >> 1) & 3:
                    k += 2
                p["topic"], p["payload"] = topic.decode("utf-8", "replace"), body[k:]
            elif t == 1:
                _, k = _mstr(body, 0)
                cflags = body[k + 1]
                _, k = _mstr(body, k + 4)
                if cflags & 0x04:
                    _, k = _mstr(body, k)
                    _, k = _mstr(body, k)
                if cflags & 0x80:
                    p["payload"], k = _mstr(body, k)
            out.append(p)
    except (ValueError, IndexError):
        return []
    return out


PAIRS = {"screen": ("screen.width", "screen.height"), "screen.avail": ("screen.availWidth", "screen.availHeight"),
         "window.inner": ("window.innerWidth", "window.innerHeight"),
         "window.outer": ("window.outerWidth", "window.outerHeight")}
UA_KEYS = ("navigator.userAgent",)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _weak(v):
    # shortcut: a whole number below 100 equals many surfaces by chance; reported apart, not dropped
    return _num(v) and float(v).is_integer() and abs(v) < 100


def match(value, truth):
    if isinstance(value, (bool, Opaque)) or value is None or value == "":
        return []
    out = []
    for surface, t in truth.items():
        if t is None or isinstance(t, bool):
            continue
        if value == t and type(value) is type(t) or (_num(value) and _num(t) and value == t):
            out.append((surface, "exact", _weak(value)))
        elif _num(t) and isinstance(value, str) and value == str(t):
            out.append((surface, "str", _weak(t)))
        elif surface in UA_KEYS and isinstance(value, str) and len(value) >= 20 and (value in t or t in value):
            out.append((surface, "substr", False))
        elif isinstance(t, list) and all(isinstance(x, str) for x in t) and value == ",".join(t):
            out.append((surface, "joined", False))
        if surface == "timezoneOffset" and _num(value) and _num(t) and t != 0 and value == -t:
            out.append((surface, "tzoffset-neg", _weak(value)))
    for name, (w, h) in PAIRS.items():
        if truth.get(w) is not None and isinstance(value, str) and value in (f"{truth[w]}x{truth[h]}", f"{truth[w]}*{truth[h]}"):
            out.append((name, "WxH", False))
    return out



def read_jsonl(path):
    out = []
    p = pathlib.Path(path)
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue  # a driver killed mid-write leaves a cut last line
    return out


def endpoint(url):
    s = urllib.parse.urlsplit(url)
    host = s.hostname or "?"
    try:
        host = f"{host}:{s.port}" if s.port else host
    except ValueError:
        pass
    return host + s.path


def _b64(s):
    return base64.b64decode(s) if s else b""


def _add_fields(slot, pairs):
    for path, v in pairs:
        f = slot.setdefault(path, {"count": 0, "classes": {}})
        f["count"] += 1
        c = value_class(v)
        f["classes"][c] = f["classes"].get(c, 0) + 1


def _frame_units(fr):
    """[(topic, field pairs)] of one frame: MQTT packets, else a JSON text frame, else one opaque unit."""
    raw = _b64(fr["payload_b64"])
    if fr.get("opcode") == 2:
        pk = mqtt_packets(raw)
        if pk:
            return [(p["topic"] or p["type"], fields(p["payload"])[1]) for p in pk]
        return [("(opaque)", [])]
    kind, f = fields(raw)
    return [("(text)" if kind != "opaque" else "(opaque)", f)]


def build_channels(requests, frames, arm):
    eps = {}
    missing = 0
    for r in requests:
        e = eps.setdefault(endpoint(r["url"]), {"count": 0, "bytes": 0, "kinds": {}, "initiators": {}, "fields": {},
                                                "via": {}})
        e["count"] += 1
        if r.get("via"):
            e["via"][r["via"]] = e["via"].get(r["via"], 0) + 1  # how the body was captured: event, getRequestPostData, route
        if r.get("missing"):
            kind, pairs = "missing", []
            missing += 1
        else:
            raw = _b64(r["body_b64"])
            e["bytes"] += len(raw)
            kind, pairs = fields(raw, r.get("content_type", ""))
        e["kinds"][kind] = e["kinds"].get(kind, 0) + 1
        ini = endpoint(r["initiator"]) if r.get("initiator") else "(no script)"
        e["initiators"][ini] = e["initiators"].get(ini, 0) + 1
        _add_fields(e["fields"], pairs)
    ws = {}
    for fr in frames:
        w = ws.setdefault(endpoint(fr["url"]), {"frames_sent": 0, "frames_received": 0, "bytes_sent": 0,
                                                "bytes_received": 0, "topics": {}})
        n = len(_b64(fr["payload_b64"]))
        w["frames_" + fr["dir"]] += 1
        w["bytes_" + fr["dir"]] += n
        for topic, pairs in _frame_units(fr):
            t = w["topics"].setdefault(topic, {"count": 0, "fields": {}})
            t["count"] += 1
            _add_fields(t["fields"], pairs)
    return {"arm": arm, "posts_captured": len(requests), "posts_missing": missing, "endpoints": eps, "ws": ws}


def build_matches(requests, frames, truth):
    n = collections.Counter()
    for r in requests:
        if not r.get("missing"):
            for path, v in fields(_b64(r["body_b64"]), r.get("content_type", ""))[1]:
                for s, enc, weak in match(v, truth):
                    n[(endpoint(r["url"]), path, s, enc, weak)] += 1
    for fr in frames:
        for topic, pairs in _frame_units(fr):
            for path, v in pairs:
                for s, enc, weak in match(v, truth):
                    n[(endpoint(fr["url"]) + " " + topic, path, s, enc, weak)] += 1
    return [{"endpoint": e, "field": f, "surface": s, "encoding": enc, "weak": weak, "count": c}
            for (e, f, s, enc, weak), c in sorted(n.items())]


def write_outputs(out_dir, arm):
    out_dir = pathlib.Path(out_dir)
    reqs = read_jsonl(out_dir / "capture" / "requests.jsonl")
    frames = read_jsonl(out_dir / "capture" / "ws.jsonl")
    tp = out_dir / "truth.json"
    truth = json.loads(tp.read_text(encoding="utf-8")) if tp.exists() else {}
    (out_dir / "channels.json").write_text(json.dumps(build_channels(reqs, frames, arm), indent=1, sort_keys=True), encoding="utf-8")
    (out_dir / "matches.json").write_text(json.dumps(build_matches(reqs, frames, truth), indent=1), encoding="utf-8")


FORK_CONFIG = {"humanize:enabled": True, "ua:osInfo": "Windows NT 10.0; Win64; x64", "ua:platform": "Windows"}
CHECKPOINT_PARTS = ("/checkpoint", "/login", "/recover", "two_step_verification")
TRUTH_JS = """async () => {
  const n = navigator, s = screen, c = n.connection || {}, ua = n.userAgentData;
  const he = ua ? await ua.getHighEntropyValues(["architecture", "bitness", "model", "platformVersion", "fullVersionList"]) : {};
  return {"navigator.userAgent": n.userAgent, "navigator.platform": n.platform, "navigator.vendor": n.vendor,
    "navigator.language": n.language, "navigator.languages": [...n.languages],
    "navigator.hardwareConcurrency": n.hardwareConcurrency, "navigator.deviceMemory": n.deviceMemory,
    "navigator.maxTouchPoints": n.maxTouchPoints,
    "screen.width": s.width, "screen.height": s.height, "screen.availWidth": s.availWidth,
    "screen.availHeight": s.availHeight, "screen.colorDepth": s.colorDepth,
    "window.devicePixelRatio": devicePixelRatio, "window.innerWidth": innerWidth, "window.innerHeight": innerHeight,
    "window.outerWidth": outerWidth, "window.outerHeight": outerHeight,
    "timezone": Intl.DateTimeFormat().resolvedOptions().timeZone, "timezoneOffset": new Date().getTimezoneOffset(),
    "connection.effectiveType": c.effectiveType, "connection.rtt": c.rtt, "connection.downlink": c.downlink,
    "uaData.platform": ua ? ua.platform : null, "uaData.mobile": ua ? ua.mobile : null,
    "uaData.brands": ua ? ua.brands.map(b => ({brand: b.brand, version: b.version})) : null,
    "uaData.architecture": he.architecture || null, "uaData.bitness": he.bitness || null, "uaData.model": he.model || null,
    "uaData.platformVersion": he.platformVersion || null,
    "uaData.fullVersionList": he.fullVersionList ? he.fullVersionList.map(b => ({brand: b.brand, version: b.version})) : null};
}"""


def is_checkpoint(url):
    path = urllib.parse.urlsplit(url).path
    return any(p in path for p in CHECKPOINT_PARTS)


def host_in(url, hosts):
    h = urllib.parse.urlsplit(url).hostname or ""
    return any(h == x or (x.startswith(".") and h.endswith(x)) for x in hosts)


# The telemetry paths whose bodies CDP does not carry (sendBeacon and keepalive Blobs): ctx.route reads them. Nothing else is routed.
ROUTE_PATHS = ("/ajax/bz", "/ajax/bnzai", "/ajax/qm/")
ROUTE_RE = re.compile(r"^https?://[^/]+/ajax/(?:bz|bnzai|qm/)")


def is_route_path(url):
    path = urllib.parse.urlsplit(url).path
    return any(path.startswith(p) for p in ROUTE_PATHS)


class Recorder:
    """One CDP session with Network.enable only (never Runtime.enable). Raw data goes to capture/ and resources/.

    A POST body reaches requests.jsonl one of three ways, recorded as `via`: the event itself, Network.getRequestPostData
    (queued by the handler, fetched in drain(), never inside a handler), or ctx.route for the ROUTE_PATHS, where the route
    handler reads post_data_buffer and forwards the request unmodified. With route on, those paths are written by the
    route only: the event gives their initiator, paired by URL in arrival order (shortcut: two requests to one URL that
    swap order swap initiators; upgrade if the map needs it), and an event no route ever answers is a `missing` record."""

    def __init__(self, out, post_hosts, resource_hosts, doc_hosts, route=True):
        self.cap = out / "capture"
        self.res = out / "resources"
        for p in (self.cap, self.res / "js", self.res / "html"):
            p.mkdir(parents=True, exist_ok=True)
        self.req_f = open(self.cap / "requests.jsonl", "a", encoding="utf-8")
        self.ws_f = open(self.cap / "ws.jsonl", "a", encoding="utf-8")
        self.post_hosts, self.resource_hosts, self.doc_hosts = post_hosts, resource_hosts, doc_hosts
        self.route = route
        self.ws_url, self.wanted, self.done = {}, {}, []
        self.pending = {}                                  # requestId -> record waiting for getRequestPostData
        self.inits = collections.defaultdict(list)         # endpoint -> [(url, content_type, initiator)] of routed paths
        self.routed = collections.defaultdict(list)        # endpoint -> [record] read by the route, waiting for an initiator

    def attach(self, cdp):
        self.cdp = cdp
        cdp.send("Network.enable", {"maxPostDataSize": 4 << 20})
        cdp.on("Network.requestWillBeSent", self.on_request)
        cdp.on("Network.responseReceived", self.on_response)
        cdp.on("Network.loadingFinished", lambda e: self.done.append(e["requestId"]) if e["requestId"] in self.wanted else None)
        cdp.on("Network.webSocketCreated", lambda e: self.ws_url.__setitem__(e["requestId"], e["url"]))
        cdp.on("Network.webSocketFrameSent", lambda e: self.on_frame(e, "sent"))
        cdp.on("Network.webSocketFrameReceived", lambda e: self.on_frame(e, "received"))

    def _write(self, rec):
        self.req_f.write(json.dumps(rec) + "\n")
        self.req_f.flush()  # a killed driver leaves whole lines, at worst one cut

    def on_request(self, e):
        r = e["request"]
        if r.get("method") != "POST" or not host_in(r["url"], self.post_hosts):
            return
        entries = r.get("postDataEntries") or []
        if entries:
            body = b"".join(base64.b64decode(x.get("bytes", "")) for x in entries)
        else:
            body = r.get("postData", "").encode("utf-8") if "postData" in r else None
        stack = (e.get("initiator") or {}).get("stack") or {}
        frames = stack.get("callFrames") or []
        ctype = (r.get("headers") or {}).get("Content-Type", "")
        initiator = frames[0]["url"] if frames else (e.get("initiator") or {}).get("url", "")
        if self.route and is_route_path(r["url"]):
            self.inits[endpoint(r["url"])].append((r["url"], ctype, initiator))
            return
        rec = {"url": r["url"], "method": "POST", "content_type": ctype,
               "body_b64": base64.b64encode(body).decode() if body else "", "missing": body is None and bool(r.get("hasPostData")),
               "initiator": initiator, "via": "" if body is None and r.get("hasPostData") else "event"}
        if rec["missing"]:
            self.pending[e["requestId"]] = rec
        else:
            self._write(rec)

    def on_route(self, route):
        """ctx.route handler for ROUTE_PATHS: read the body, record it, forward the request unmodified, always."""
        try:
            req = route.request
            if req.method == "POST" and host_in(req.url, self.post_hosts):
                try:
                    body = req.post_data_buffer
                except Exception:  # noqa: BLE001 - a body the route cannot read is a missing record, not a blocked request
                    body = None
                self.routed[endpoint(req.url)].append({
                    "url": req.url, "method": "POST", "content_type": (req.headers or {}).get("content-type", ""),
                    "body_b64": base64.b64encode(body).decode() if body else "", "missing": body is None,
                    "initiator": "", "via": "route"})
        except Exception:  # noqa: BLE001
            pass
        finally:
            route.continue_()

    def _pair_routes(self):
        for key, recs in self.routed.items():
            inits = self.inits[key]
            while recs and inits:
                rec = recs.pop(0)
                rec["initiator"] = inits.pop(0)[2]
                self._write(rec)

    def on_response(self, e):
        t, url = e.get("type"), e["response"]["url"]
        if (t == "Script" and host_in(url, self.resource_hosts)) or (t == "Document" and host_in(url, self.doc_hosts)):
            self.wanted[e["requestId"]] = "js" if t == "Script" else "html"

    def on_frame(self, e, direction):
        url = self.ws_url.get(e["requestId"], "")
        if not host_in(url, [".facebook.com"]):
            return
        r = e["response"]
        data = r.get("payloadData", "")
        payload = data if r.get("opcode") == 2 else base64.b64encode(data.encode("utf-8")).decode()
        self.ws_f.write(json.dumps({"url": url, "dir": direction, "opcode": r.get("opcode"), "payload_b64": payload}) + "\n")

    def drain(self):
        """Fetches finished resource bodies; called between steps, never inside an event handler."""
        while self.done:
            rid = self.done.pop()
            kind = self.wanted.pop(rid, None)
            try:
                b = self.cdp.send("Network.getResponseBody", {"requestId": rid})
            except Exception:  # noqa: BLE001 - an evicted body is a missing file, not a failed arm
                continue
            raw = base64.b64decode(b["body"]) if b.get("base64Encoded") else b["body"].encode("utf-8")
            ext = "js" if kind == "js" else "html"
            (self.res / kind / f"{hashlib.sha256(raw).hexdigest()}.{ext}").write_bytes(raw)
        for rid in list(self.pending):
            rec = self.pending.pop(rid)
            try:
                b = self.cdp.send("Network.getRequestPostData", {"requestId": rid})
                raw = base64.b64decode(b["postData"]) if b.get("base64Encoded") else b["postData"].encode("utf-8")
                rec.update(body_b64=base64.b64encode(raw).decode(), missing=False, via="getRequestPostData")
            except Exception:  # noqa: BLE001 - an evicted body stays a `missing` record, counted in the report
                pass
            self._write(rec)
        self._pair_routes()

    def close(self):
        """The last records: routed bodies no event came for, and events no route answered (missing)."""
        for rid in list(self.pending):
            self._write(self.pending.pop(rid))
        self._pair_routes()
        for recs in self.routed.values():
            for rec in recs:
                self._write(rec)
        for inits in self.inits.values():
            for url, ctype, initiator in inits:
                self._write({"url": url, "method": "POST", "content_type": ctype, "body_b64": "", "missing": True,
                             "initiator": initiator, "via": ""})
        self.req_f.close()
        self.ws_f.close()


TRUTH_PAGE = b"<!doctype html><title>t</title>"


class _TruthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(TRUTH_PAGE)))
        self.end_headers()
        self.wfile.write(TRUTH_PAGE)

    def log_message(self, *args):
        pass


def truth_page(explicit):
    """(server or None, url) of the page the ground truth is read in. About:blank is no secure context, so
    navigator.deviceMemory and navigator.userAgentData read null there (measured on the box, 2026-10-29); a facebook.com
    page would file the driver's own reads under facebook's section of the observer. So by default an empty page is served
    on 127.0.0.1 (a secure context, no outside request, its own observer section); --truth-url overrides it."""
    if explicit:
        return None, explicit
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _TruthHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}/"


def stop_truth_page(srv):
    if srv is not None:
        srv.shutdown()
        srv.server_close()


def read_truth(ctx, url):
    page = ctx.new_page()
    try:
        page.goto(url)
        return page.evaluate(TRUTH_JS)
    finally:
        page.close()


def scroll(page, seconds, rng, rec):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        page.mouse.wheel(0, 100)
        page.wait_for_timeout(int(rng.uniform(0.6, 2.5) * 1000))
        rec.drain()


def run(a):
    from patchright.sync_api import sync_playwright
    from camoucrome.launcher import launch
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    extra = json.loads(pathlib.Path(a.chrome_args).read_text(encoding="utf-8")) if a.chrome_args else []
    rec = Recorder(out, a.post_hosts.split(","), a.resource_hosts.split(","), a.doc_hosts.split(","), route=not a.no_route)
    rc = 0
    with sync_playwright() as pw:
        ctx = launch(pw, a.exe, config=FORK_CONFIG if a.fork else None, user_data_dir=a.profile,
                     headless=a.headless, args=extra)
        try:
            # --no-truth: only verify_observe_drive uses it, to show the matcher row goes RED without ground truth
            truth_srv, truth_url = truth_page(a.truth_url)
            try:
                (out / "truth.json").write_text(json.dumps({} if a.no_truth else read_truth(ctx, truth_url)), encoding="utf-8")
            finally:
                stop_truth_page(truth_srv)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            rec.attach(ctx.new_cdp_session(page))
            if not a.no_route:
                ctx.route(ROUTE_RE, rec.on_route)  # exactly the ROUTE_PATHS; the handler forwards every request unmodified
            vp = page.viewport_size or {"width": 1280, "height": 720}
            page.mouse.move(vp["width"] / 2, vp["height"] / 2)
            rng = random.Random()
            for url in a.url:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(int(a.settle * 1000))
                if a.expect_session and is_checkpoint(page.url):
                    print("CHECKPOINT " + endpoint(page.url), flush=True)
                    rc = 4
                    break
                scroll(page, a.wheel, rng, rec)
                if a.headless:
                    print("TITLE=" + page.title(), flush=True)  # the dry-run page counts wheel events into document.title
            page.wait_for_timeout(3000)  # the last beacons of the section leave
            rec.drain()
        finally:
            rec.close()
            try:
                ctx.close()
            finally:
                write_outputs(out, a.arm)  # a killed arm still leaves a partial channels.json to diagnose
    return rc


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--arm", required=True)
    ap.add_argument("--exe", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--url", action="append", required=True)
    ap.add_argument("--settle", type=float, default=20)
    ap.add_argument("--wheel", type=float, default=40)
    ap.add_argument("--fork", action="store_true")
    ap.add_argument("--chrome-args")
    ap.add_argument("--expect-session", action="store_true")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--truth-url", default=None,
                    help="page the ground truth is read in; default: an empty page served on 127.0.0.1 (a secure context)")
    ap.add_argument("--no-truth", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--no-route", action="store_true", help=argparse.SUPPRESS)  # only verify_observe_drive: D6's RED
    ap.add_argument("--post-hosts", default="www.facebook.com,web.facebook.com,graph.facebook.com,www.fbsbx.com,gateway.facebook.com")
    ap.add_argument("--resource-hosts", default="static.xx.fbcdn.net,connect.facebook.net")
    ap.add_argument("--doc-hosts", default="www.facebook.com")
    return ap.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    try:
        return run(a)
    except Exception as exc:  # noqa: BLE001 - recon.ps1 reads the exit code; the type names the failure
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
