"""Driven arms of the facebook tracking map: capture on the host, names and matches out.

Spec: docs/superpowers/specs/2026-10-29-fb-tracking-map-design.md (local). Runs on the Windows
host in the observe venv (Python 3.12, patchright, the client). Values never leave the host:
channels.json and matches.json carry names, counts, value classes and surface matches only.
"""
import base64
import binascii
import collections
import gzip
import json
import pathlib
import re
import urllib.parse
import zlib

ID_RE = re.compile(r"^\d{10,}$")


def value_class(v):
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


def decode_body(raw, _b64=True):
    raw = _inflate(raw)
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


def fields(raw):
    kind, v = decode_body(raw)
    if kind == "json":
        return kind, walk(v)
    if kind == "form":
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
    if isinstance(value, bool) or value is None or value == "":
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
        e = eps.setdefault(endpoint(r["url"]), {"count": 0, "bytes": 0, "kinds": {}, "initiators": {}, "fields": {}})
        e["count"] += 1
        if r.get("missing"):
            kind, pairs = "missing", []
            missing += 1
        else:
            raw = _b64(r["body_b64"])
            e["bytes"] += len(raw)
            kind, pairs = fields(raw)
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
            for path, v in fields(_b64(r["body_b64"]))[1]:
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
