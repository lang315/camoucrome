"""observe_drive.py on hand-made fixtures (no browser)."""
import base64
import gzip
import json
import pathlib
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import observe_drive as d  # noqa: E402


def test_value_class_keeps_no_value():
    assert d.value_class(True) == "bool"
    assert d.value_class(8) == "int"
    assert d.value_class(1.5) == "float"
    assert d.value_class(None) == "null"
    assert d.value_class("100012345678901") == "id"
    assert d.value_class(100012345678901) == "id"
    assert d.value_class("hello") == "str<5>"


def test_form_body_with_a_json_value_is_walked():
    q = json.dumps([{"events": [{"name": "a", "dm": 8}]}])
    raw = urllib.parse.urlencode({"__a": "1", "q": q}).encode()
    kind, f = d.fields(raw)
    assert kind == "form"
    assert ("__a", "1") in f
    assert ("q[].events[].name", "a") in f
    assert ("q[].events[].dm", 8) in f


def test_json_body_nested_dicts_and_lists():
    raw = json.dumps({"a": {"b": [1, 2]}, "c": "x"}).encode()
    kind, f = d.fields(raw)
    assert kind == "json"
    assert f == [("a.b[]", 1), ("a.b[]", 2), ("c", "x")]


def test_gzip_and_base64_are_tried_once():
    inner = json.dumps({"k": "v"}).encode()
    assert d.fields(gzip.compress(inner)) == ("json", [("k", "v")])
    assert d.fields(base64.b64encode(inner)) == ("json", [("k", "v")])


def test_opaque_body():
    assert d.fields(b"\x00\x01\x02\xff") == ("opaque", [])
    assert d.fields(b"just some words") == ("opaque", [])


def _mqtt_str(s):
    b = s.encode()
    return len(b).to_bytes(2, "big") + b


def _packet(ptype, flags, body):
    return bytes([(ptype << 4) | flags, len(body)]) + body


def test_mqtt_publish_topic_and_payload():
    body = _mqtt_str("/t_ms") + b'{"a":1}'
    assert d.mqtt_packets(_packet(3, 0, body)) == [{"type": "PUBLISH", "topic": "/t_ms", "payload": b'{"a":1}'}]


def test_mqtt_publish_qos1_skips_the_packet_id():
    body = _mqtt_str("/x") + b"\x00\x07" + b"{}"
    assert d.mqtt_packets(_packet(3, 2, body))[0]["payload"] == b"{}"


def test_mqtt_connect_username_is_the_payload():
    var = _mqtt_str("MQIsdp") + bytes([3, 0x80 | 0x02]) + b"\x00\x3c"
    body = var + _mqtt_str("client") + _mqtt_str('{"u":"100012345678901"}')
    p = d.mqtt_packets(_packet(1, 0, body))
    assert p == [{"type": "CONNECT", "topic": "", "payload": b'{"u":"100012345678901"}'}]


def test_two_packets_in_one_frame():
    f = _packet(12, 0, b"") + _packet(3, 0, _mqtt_str("/a") + b"x")
    assert [p["type"] for p in d.mqtt_packets(f)] == ["PINGREQ", "PUBLISH"]


def test_not_mqtt_or_truncated_gives_nothing():
    assert d.mqtt_packets(b"\x00\x05ab") == []
    assert d.mqtt_packets(bytes([0x30, 10]) + b"abc") == []
    assert d.mqtt_packets(b"") == []


TRUTH = {"navigator.userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
         "navigator.deviceMemory": 8, "navigator.hardwareConcurrency": 8, "navigator.languages": ["en-US", "en"],
         "screen.width": 1920, "screen.height": 1080, "window.innerWidth": 1280, "window.innerHeight": 720,
         "timezone": "Europe/Berlin", "timezoneOffset": -60, "window.devicePixelRatio": 1.25}


def test_exact_and_string_forms():
    assert ("timezone", "exact", False) in d.match("Europe/Berlin", TRUTH)
    assert ("screen.width", "str", False) in d.match("1920", TRUTH)
    assert ("window.devicePixelRatio", "exact", False) in d.match(1.25, TRUTH)


def test_ua_substring_needs_20_chars():
    assert ("navigator.userAgent", "substr", False) in d.match("AppleWebKit/537.36 (KHTML", TRUTH)
    assert all(s != "navigator.userAgent" for s, _, _ in d.match("Chrome", TRUTH))


def test_composite_sizes_and_joined_languages():
    assert ("screen", "WxH", False) in d.match("1920x1080", TRUTH)
    assert ("window.inner", "WxH", False) in d.match("1280x720", TRUTH)
    assert ("navigator.languages", "joined", False) in d.match("en-US,en", TRUTH)


def test_timezone_offset_both_signs():
    assert ("timezoneOffset", "exact", True) in d.match(-60, TRUTH)
    assert ("timezoneOffset", "tzoffset-neg", True) in d.match(60, TRUTH)


def test_small_numbers_are_weak_and_a_near_miss_does_not_match():
    m = d.match(8, TRUTH)
    assert ("navigator.deviceMemory", "exact", True) in m
    assert ("navigator.hardwareConcurrency", "exact", True) in m
    assert d.match(1921, TRUTH) == []
    assert d.match("1920x1081", TRUTH) == []
    assert d.match(True, TRUTH) == []


def _req(url, body, initiator="https://static.xx.fbcdn.net/rsrc.php/v3/a.js", missing=False):
    return {"url": url, "method": "POST", "content_type": "application/x-www-form-urlencoded",
            "body_b64": "" if missing else base64.b64encode(body).decode(), "missing": missing, "initiator": initiator}


def _frame(url, direction, payload, opcode=2):
    return {"url": url, "dir": direction, "opcode": opcode, "payload_b64": base64.b64encode(payload).decode()}


CANARY = "CANARY-7f3a9c"


def _fixture():
    q = json.dumps([{"name": CANARY + "-name", "dm": 8, "uid": "100012345678901", "tz": "Europe/Berlin"}])
    reqs = [_req("https://www.facebook.com/ajax/bz?__a=1&tok=" + CANARY, urllib.parse.urlencode({"q": q}).encode()),
            _req("https://www.facebook.com/ajax/bz", urllib.parse.urlencode({"q": q}).encode()),
            _req("https://www.facebook.com/ajax/bnzai", b"", missing=True)]
    pub = _packet(3, 0, _mqtt_str("/t_ms") + json.dumps({"payload": CANARY}).encode())
    frames = [_frame("wss://gateway.facebook.com/ws/realtime?x=" + CANARY, "sent", pub),
              _frame("wss://gateway.facebook.com/ws/realtime", "received", b"\x00\x01binary")]
    return reqs, frames


def test_channels_count_fields_classes_and_missing_bodies():
    reqs, frames = _fixture()
    c = d.build_channels(reqs, frames, "3w")
    bz = c["endpoints"]["www.facebook.com/ajax/bz"]
    assert bz["count"] == 2 and bz["kinds"] == {"form": 2}
    assert bz["fields"]["q[].dm"] == {"count": 2, "classes": {"int": 2}}
    assert bz["fields"]["q[].uid"]["classes"] == {"id": 2}
    assert bz["initiators"] == {"static.xx.fbcdn.net/rsrc.php/v3/a.js": 2}
    assert c["endpoints"]["www.facebook.com/ajax/bnzai"]["kinds"] == {"missing": 1}
    assert (c["posts_captured"], c["posts_missing"]) == (3, 1)
    ws = c["ws"]["gateway.facebook.com/ws/realtime"]
    assert (ws["frames_sent"], ws["frames_received"]) == (1, 1)
    assert ws["topics"]["/t_ms"]["fields"]["payload"]["count"] == 1
    assert ws["topics"]["(opaque)"]["count"] == 1


def test_matches_carry_surface_and_weak_flag():
    reqs, frames = _fixture()
    m = d.build_matches(reqs, frames, TRUTH)
    assert {"endpoint": "www.facebook.com/ajax/bz", "field": "q[].tz", "surface": "timezone",
            "encoding": "exact", "weak": False, "count": 2} in m
    assert any(r["field"] == "q[].dm" and r["surface"] == "navigator.deviceMemory" and r["weak"] for r in m)


def test_value_canary_never_reaches_a_leaving_file(tmp_path):
    reqs, frames = _fixture()
    cap = tmp_path / "capture"
    cap.mkdir()
    (cap / "requests.jsonl").write_text("\n".join(json.dumps(r) for r in reqs) + '\n{"url": "cut', encoding="utf-8")
    (cap / "ws.jsonl").write_text("\n".join(json.dumps(f) for f in frames) + "\n", encoding="utf-8")
    (tmp_path / "truth.json").write_text(json.dumps(TRUTH), encoding="utf-8")
    d.write_outputs(tmp_path, "3w")
    for name in ("channels.json", "matches.json"):
        text = (tmp_path / name).read_text(encoding="utf-8")
        assert CANARY not in text, name
        assert "100012345678901" not in text, name
    assert json.loads((tmp_path / "channels.json").read_text())["posts_captured"] == 3


def test_checkpoint_urls():
    for u in ("https://www.facebook.com/checkpoint/1501092823525282/", "https://www.facebook.com/login/?next=x",
              "https://www.facebook.com/recover/initiate/", "https://www.facebook.com/two_step_verification/two_factor/"):
        assert d.is_checkpoint(u), u
    assert not d.is_checkpoint("https://www.facebook.com/")
    assert not d.is_checkpoint("https://www.facebook.com/watch/")


def test_host_lists_match_exact_hosts_and_suffixes():
    assert d.host_in("https://www.facebook.com/ajax/bz", ["www.facebook.com"])
    assert not d.host_in("https://evil.com/www.facebook.com", ["www.facebook.com"])
    assert d.host_in("wss://edge-chat.facebook.com/x", [".facebook.com"])


def test_module_imports_without_patchright():
    import subprocess
    code = "import observe_drive, sys; assert 'patchright' not in sys.modules and 'camoucrome' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], cwd=pathlib.Path(__file__).resolve().parent, check=True)


def test_truth_page_defaults_to_a_local_secure_origin():
    # about:blank reads deviceMemory and userAgentData as null; facebook.com would file the driver's reads under its own
    # section; so with no --truth-url the driver serves an empty page on 127.0.0.1 (a secure context, no outside request)
    import urllib.request
    a = d.parse_args(["--arm", "x", "--exe", "e", "--profile", "p", "--out", "o", "--url", "u"])
    assert a.truth_url is None
    srv, url = d.truth_page(a.truth_url)
    try:
        assert url.startswith("http://127.0.0.1:")
        assert urllib.request.urlopen(url).read() == b"<!doctype html><title>t</title>"
    finally:
        d.stop_truth_page(srv)


def test_an_explicit_truth_url_is_kept_and_starts_no_server():
    srv, url = d.truth_page("https://example.invalid/t")
    assert srv is None and url == "https://example.invalid/t"
    d.stop_truth_page(srv)  # nothing to stop


BOUNDARY = "----WebKitFormBoundaryAbC123xyz"


def _multipart(parts, boundary=BOUNDARY):
    out = b""
    for name, value, filename in parts:
        disp = f'form-data; name="{name}"' + (f'; filename="{filename}"' if filename else "")
        out += f"--{boundary}\r\nContent-Disposition: {disp}\r\n\r\n".encode() + value + b"\r\n"
    return out + f"--{boundary}--\r\n".encode()


MULTIPART = _multipart([
    ("__a", b"1", None),
    ("q", json.dumps([{"name": CANARY + "-mp", "dm": 8}]).encode(), None),
    ("upload", b"\x89PNG\r\n\x1a\n" + b"\x00" * 40, "blob.png"),
])


def test_multipart_parts_are_named_by_their_name_attribute_and_walked():
    kind, f = d.fields(MULTIPART, "multipart/form-data; boundary=" + BOUNDARY)
    assert kind == "multipart"
    assert ("__a", "1") in f
    assert ("q[].name", CANARY + "-mp") in f and ("q[].dm", 8) in f
    paths = [p for p, _ in f]
    assert "upload" in paths and not any("Boundary" in p or "Content-Disposition" in p for p in paths)


def test_a_file_part_is_opaque_with_its_length():
    _, f = d.fields(MULTIPART, "multipart/form-data; boundary=" + BOUNDARY)
    (v,) = [v for p, v in f if p == "upload"]
    assert d.value_class(v) == "opaque<48>"


def test_multipart_is_recognised_by_its_first_line_without_a_content_type():
    assert d.fields(MULTIPART)[0] == "multipart"
    assert d.fields(b"--just a dash line\r\nbut no parts")[0] == "opaque"


def test_the_boundary_and_the_canary_never_reach_channels_for_a_multipart_post():
    req = _req("https://www.facebook.com/ajax/mp", MULTIPART)
    req["content_type"] = "multipart/form-data; boundary=" + BOUNDARY
    c = d.build_channels([req], [], "x")
    ep = c["endpoints"]["www.facebook.com/ajax/mp"]
    assert ep["kinds"] == {"multipart": 1} and ep["fields"]["upload"]["classes"] == {"opaque<48>": 1}
    text = json.dumps(c) + json.dumps(d.build_matches([req], [], TRUTH))
    assert "Boundary" not in text and CANARY not in text
