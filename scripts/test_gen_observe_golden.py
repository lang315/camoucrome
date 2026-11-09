import json, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]

def test_golden_is_current():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_observe_golden.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

def test_golden_covers_every_encoding():
    g = json.loads((ROOT / "additions" / "camoucfg" / "observe_golden.json").read_text())
    kinds = {c["kind"] for c in g["http"]}
    assert kinds == {"json", "form", "multipart", "opaque"}
    names = {c["name"] for c in g["http"]} | {c["name"] for c in g["ws"]}
    for want in ("gzip-json", "zlib-json", "raw-deflate-json", "multipart-zlib-part", "multipart-file-json",
                 "multipart-file-opaque", "b64-json", "form-plus-percent", "json-in-string", "sjd-ok",
                 "sjd-bad-key", "mqtt-publish-json", "mqtt-cut", "gw-0d-json", "gw-0d-mqtt", "gw-0c-ack",
                 "keepalive-09", "text-json", "truncated-gzip", "garbage"):
        assert want in names, want
    assert len(g["b64"]) >= 12 and len(g["inflate"]) >= 10

def test_nothing_captured():
    text = (ROOT / "additions" / "camoucfg" / "observe_golden.json").read_text()
    for banned in ("facebook.com", "c_user", "fbcdn"):
        assert banned not in text
