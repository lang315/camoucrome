#!/usr/bin/env python3
"""Generate additions/camoucfg/observe_golden.json: synthetic inputs plus what the Python observe oracle
(observe_drive.py, sites/facebook.py) returns for each. The C++ decoder's unit tests check parity against it.

Everything is built here; nothing is captured. Output is byte-deterministic.
Dependency: pycryptodome (Crypto.Cipher.Blowfish) to build the `sjd` fixtures.
Usage: gen_observe_golden.py [--check]   (--check exits 1 when the file is stale)
"""
import base64
import collections
import gzip
import json
import pathlib
import random
import sys
import zlib

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import observe_drive as d  # noqa: E402
import sites  # noqa: E402
from Crypto.Cipher import Blowfish  # noqa: E402

OUT = HERE.parent / "additions" / "camoucfg" / "observe_golden.json"
SITE = sites.load("facebook")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/156.0.0.0 Safari/537.36 Synthetic")
UA = UA[:120].ljust(120, "x")
TRUTH = {"navigator.userAgent": UA, "navigator.languages": ["en-US", "en"], "navigator.hardwareConcurrency": 12,
         "navigator.deviceMemory": 16, "screen.width": 1517, "screen.height": 853, "screen.availWidth": 1517,
         "screen.availHeight": 813, "window.innerWidth": 1400, "window.innerHeight": 700,
         "window.outerWidth": 1517, "window.outerHeight": 813, "window.devicePixelRatio": 1.25,
         "timezone": "Pacific/Chatham", "timezoneOffset": -825, "connection.effectiveType": "4g",
         "uaData.mobile": False, "media.dynamicRangeHigh": False,
         "test.integralFloat": 2.0,
         "webgl.renderer": "ANGLE (Synthetic, Synthetic Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"}
rng = random.Random(1234)
b64e = lambda b: base64.b64encode(b).decode("ascii")
J = lambda o: json.dumps(o, separators=(",", ":")).encode()
BODY = J({"w": 1517, "h": 853, "tz": "Pacific/Chatham"})
ASID = "0123456789abcdefghijklmnopqrstuvwxyz"


def sjd_blob(asid, plain):
    key = (asid[19:23] + asid[24:36]).encode("ascii")
    iv = bytes(a ^ b for a, b in zip(key[:8], key[8:16]))
    plain += b"\x00" * (-len(plain) % 8)
    return b64e(Blowfish.new(key, Blowfish.MODE_CBC, iv).encrypt(plain))


SIGNALS = J({"12": ["Pacific/Chatham", 1517], "7": [True]})


def raw_deflate(b):
    c = zlib.compressobj(6, zlib.DEFLATED, -15)
    return c.compress(b) + c.flush()


def mp(parts, boundary="----B0UND"):
    """parts: [(content-disposition header bytes, body bytes)]"""
    out = b""
    for head, body in parts:
        out += b"--" + boundary.encode() + b"\r\nContent-Disposition: " + head + b"\r\n\r\n" + body + b"\r\n"
    return out + b"--" + boundary.encode() + b"--\r\n"


MPCT = "multipart/form-data; boundary=----B0UND"
fd = lambda n: b'form-data; name="' + n + b'"'
ff = lambda n, f: b'form-data; name="' + n + b'"; filename="' + f + b'"'
JCT = "application/json"
FORMCT = "application/x-www-form-urlencoded"
garbage = rng.randbytes(64)
file_rand = rng.randbytes(300)

HTTP_IN = [
    ("json-plain", JCT, J({"w": 1517, "h": 853, "tz": "Pacific/Chatham", "dpr": 1.25, "m": False, "n": None,
                            "ids": [12345678901, "98765432109"]})),
    # base::Value keeps no int/float token kind: 2.0 stays a float, a JSON integer past int32 is a big int
    ("number-classes", JCT, J({"dpr": 2.0, "i32max": 2147483647, "above32": 2147483648, "neg": -2147483649,
                                "mid": 10**15, "big": 10**16})),
    ("integral-float-match", JCT, J({"a": "2.0", "b": "2", "c": 2.0, "d": 2})),
    ("gzip-json", JCT, gzip.compress(BODY, mtime=0)),
    ("zlib-json", JCT, zlib.compress(BODY, 6)),
    ("raw-deflate-json", JCT, raw_deflate(BODY)),
    ("json-in-string", JCT, J({"d": '{"w":1517,"x":"[1,2]"}'})),
    ("b64-json", "", b64e(BODY).encode()),
    ("b64-of-gzip-json", "", b64e(gzip.compress(BODY, mtime=0)).encode()),
    ("form-plus-percent", FORMCT, b"res=1517x853&tz=Pacific%2FChatham&q=a+b&blank&%zz=1"),
    ("multipart-strings", MPCT, mp([(fd(b"w"), b"1517"), (fd(b"tz"), b"Pacific/Chatham"), (fd(b"res"), b"1517x853")])),
    ("multipart-no-ct", "", mp([(fd(b"w"), b"1517"), (fd(b"h"), b"853")])),
    ("multipart-zlib-part", MPCT, mp([(fd(b"post_0"), zlib.compress(BODY, 6)), (fd(b"x"), b"1")])),
    ("multipart-file-json", MPCT, mp([(ff(b"f", b"a.json"), BODY)])),
    ("multipart-file-opaque", MPCT, mp([(ff(b"f", b"a.bin"), file_rand)])),
    ("multipart-filename-before-name", MPCT, mp([(b'form-data; filename="a"; name="b"', BODY)])),
    ("sjd-ok", JCT, J({"asid": ASID, "sjd": sjd_blob(ASID, SIGNALS)})),
    ("sjd-bad-key", JCT, J({"asid": "z" * 36, "sjd": sjd_blob(ASID, SIGNALS)})),
    ("sjd-short-asid", JCT, J({"asid": "short", "sjd": sjd_blob(ASID, SIGNALS)})),
    ("ua-substr", JCT, J({"u": UA + " suffix"})),
    ("languages-joined", JCT, J({"l": "en-US,en"})),
    ("tz-negated", JCT, J({"o": 825})),
    ("str-number", JCT, J({"w": "1517"})),
    ("weak-small", JCT, J({"c": 12, "e": "4g"})),
    ("bool-field", JCT, J({"mobile": False, "hdr": False, "x": True})),
    ("truncated-gzip", JCT, gzip.compress(BODY, mtime=0)[:-3]),
    ("garbage", "", garbage),
    ("empty", "", b""),
    ("utf8-invalid-name", MPCT, mp([(fd(b"\xff"), b"1517")])),
    ("nul-text", "", b"abc\x00def=1\x00"),
]


def srt(pairs):
    return sorted(pairs)


def http_case(name, ct, raw):
    stats = collections.Counter()
    kind, fl = d.fields(raw, ct, SITE, stats)
    matches, bools = [], []
    for p, v in fl:
        matches += [[p, s, e, w] for s, e, w in d.match(v, TRUTH)]
        bools += [[p, s] for s in d.bool_matches(v, TRUTH)]
    return {"name": name, "ct": ct, "b64": b64e(raw), "kind": kind,
            "fields": srt([p, d.value_class(v)] for p, v in fl), "matches": srt(matches), "bools": srt(bools),
            "sjd": [stats["decoded"], stats["failed"]]}


def pub(topic, payload, qos=0):
    body = len(topic).to_bytes(2, "big") + topic + (b"\x00\x07" if qos else b"") + payload
    return mqtt(3, qos << 1, body)


def mqtt(t, flags, body):
    n, vl = len(body), b""
    while True:
        c, n = n % 128, n // 128
        vl += bytes([c | (128 if n else 0)])
        if not n:
            break
    return bytes([t << 4 | flags]) + vl + body


def chunk(t, payload, sid=b"\x00\x01"):
    return bytes([t]) + sid + len(payload).to_bytes(3, "little") + payload


connect = mqtt(1, 0, b"\x00\x04MQTT\x04\x80\x00\x3c\x00\x02id" + len(BODY).to_bytes(2, "big") + BODY)
cutpub = pub(b"/t/x", BODY)
WS_IN = [
    ("text-json", 1, BODY),
    ("text-garbage", 1, b"\xff\xfe\x00garbage"),
    ("keepalive-09", 2, b"\x09"),
    ("keepalive-0a", 2, b"\x0a"),
    ("mqtt-publish-json", 2, pub(b"/t/x", BODY, qos=1)),
    ("mqtt-connect-username", 2, connect),
    ("mqtt-two-packets", 2, pub(b"/t/a", BODY) + pub(b"/t/b", J({"h": 853}))),
    ("mqtt-cut", 2, pub(b"/t/a", BODY) + cutpub[:5]),
    ("mqtt-short-connack", 2, b"\x20\x01\x00"),
    ("gw-0d-json", 2, chunk(0x0d, b"\x00\x01" + BODY)),
    ("gw-0d-json-header", 2, chunk(0x0d, b"\x00\x01\x01\x02\x03" + BODY)),
    ("gw-0d-mqtt", 2, chunk(0x0d, b"\x00\x01" + pub(b"/t/x", BODY))),
    ("gw-0c-ack", 2, chunk(0x0c, b"\x00\x05")),
    ("gw-two-chunks", 2, chunk(0x0d, b"\x00\x01" + BODY) + chunk(0x0c, b"\x00\x06")),
    ("gw-rest", 2, chunk(0x0d, b"\x00\x01" + BODY) + b"\x00\x01\x02\x03"),
    ("binary-garbage", 2, garbage),
]


def ws_case(name, op, raw):
    units, partial = d._frame_units({"opcode": op, "payload_b64": b64e(raw)}, SITE)
    return {"name": name, "opcode": op, "b64": b64e(raw), "partial": partial,
            "units": [[t, srt([p, d.value_class(v)] for p, v in fl)] for t, fl in units]}


def sjd_cases():
    ev = lambda asid, blob: {"asid": asid, "sjd": blob}
    nonascii = ASID[:19] + "éééé" + ASID[23:]
    cases = [("ok", ev(ASID, sjd_blob(ASID, SIGNALS))),
             ("ciphertext-not-multiple-of-8", ev(ASID, b64e(b"1234567"))),
             ("non-base64", ev(ASID, "!!not base64!!")),
             ("plaintext-not-json", ev(ASID, sjd_blob(ASID, b"not json at all"))),
             ("plaintext-list", ev(ASID, sjd_blob(ASID, J([1, 2])))),
             ("non-list-value", ev(ASID, sjd_blob(ASID, J({"1": [1], "2": "x"})))),
             ("non-ascii-key", ev(nonascii, sjd_blob(ASID, SIGNALS)))]
    return [{"name": n, "event": e, "doc": SITE.hooks.decode_sjd(e)} for n, e in cases]


def b64_cases():
    out = []
    for s in ["YQ", "YQ=", "YQ==", "YR==", "YWJj", "YQ===", "=", "YQ==YQ==", "Y===", "YWI=", "YWJj=", "YW Jj", ""]:
        try:
            r = b64e(base64.b64decode(s, validate=True))
        except Exception:
            r = None
        out.append({"in": s, "out_b64": r})
    return out


def inflate_cases():
    data = b"hello synthetic body " * 4
    codecs = {"gzip": lambda b: gzip.compress(b, mtime=0), "zlib": lambda b: zlib.compress(b, 6), "raw": raw_deflate}
    ins = [("empty", b"")]
    for c, f in codecs.items():
        x = f(data)
        ins += [(f"{c}-exact", x), (f"{c}-junk", x + b"junk"), (f"{c}-nuls", x + b"\x00\x00"),
                (f"{c}-truncated", x[:-3]), (f"{c}-two-members", x + f(data))]
    return [{"name": n, "in_b64": b64e(x), "out_b64": None if d._inflate(x) == x else b64e(d._inflate(x))}
            for n, x in ins]


def divergent_cases():
    ins = [("big-int-precision", "Python keeps 9007199254740993, C++ holds 9007199254740992: base::Value stores a "
            "JSON integer past int32 as a double, so digits past 2^53 are lost", b'{"a":9007199254740993}'),
           ("integral-float-past-int32", "Python float, C++ id: an integral float written with a point or exponent "
            "past int32 (JS never writes one) reads as a big integer", b'{"a":1000000000000000.0}'),
           ("json-depth-300", "Python json, C++ opaque: base::JSONReader's depth limit", b"[" * 300 + b"]" * 300),
           ("unicode-digits-id", "Python id, C++ str<10>: Python's \\d matches Unicode digits",
            '{"a":"١٢٣٤٥٦٧٨٩٠"}'.encode())]
    out = []
    for n, why, raw in ins:
        k, fl = d.fields(raw, "", SITE)
        out.append({"name": n, "why": why, "ct": "", "b64": b64e(raw), "kind": k,
                    "fields": srt([p, d.value_class(v)] for p, v in fl),
                    "text": srt([p, str(v)] for p, v in fl)})
    return out


def build():
    g = {"truth": TRUTH, "http": [http_case(*c) for c in HTTP_IN], "ws": [ws_case(*c) for c in WS_IN],
         "sjd": sjd_cases(), "b64": b64_cases(), "inflate": inflate_cases(), "divergent": divergent_cases()}
    return json.dumps(g, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    text = build()
    if "--check" in sys.argv:
        have = OUT.read_text(encoding="utf-8") if OUT.exists() else None
        if have != text:
            print(f"{OUT.name} is stale: {len(have or '')} bytes on disk, {len(text)} generated")
            sys.exit(1)
    else:
        OUT.write_text(text, encoding="utf-8")
