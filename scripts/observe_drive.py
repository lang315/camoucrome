"""Driven arms of the facebook tracking map: capture on the host, names and matches out.

Spec: docs/superpowers/specs/2026-10-29-fb-tracking-map-design.md (local). Runs on the Windows
host in the observe venv (Python 3.12, patchright, the client). Values never leave the host:
channels.json and matches.json carry names, counts, value classes and surface matches only.
"""
import base64
import binascii
import gzip
import json
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
