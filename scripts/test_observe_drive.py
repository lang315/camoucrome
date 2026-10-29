"""observe_drive.py on hand-made fixtures (no browser)."""
import base64
import gzip
import json
import pathlib
import sys
import urllib.parse
import zlib

import pytest

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


# --- request bodies CDP does not carry: getRequestPostData, then ctx.route on the telemetry paths -------------------------

class FakeCdp:
    def __init__(self, post_data=None, fail=False):
        self.calls, self.post_data, self.fail = [], post_data or {}, fail

    def send(self, method, params=None):
        self.calls.append((method, params))
        if method == "Network.getRequestPostData":
            if self.fail or params["requestId"] not in self.post_data:
                raise RuntimeError("No resource with given identifier found")
            return {"postData": self.post_data[params["requestId"]]}
        return {}

    def on(self, *a):
        pass


class FakeRequest:
    def __init__(self, url, body, method="POST", headers=None):
        self.url, self.method, self.headers = url, method, headers or {"content-type": "text/plain"}
        self._body = body

    @property
    def post_data_buffer(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeRoute:
    def __init__(self, request):
        self.request, self.continued = request, 0

    def continue_(self):
        self.continued += 1


def _event(rid, url, has_post_data=True, post_data=None, script="https://static.xx.fbcdn.net/rsrc.php/v3/a.js"):
    r = {"url": url, "method": "POST", "headers": {"Content-Type": "text/plain"}, "hasPostData": has_post_data}
    if post_data is not None:
        r["postData"] = post_data
    return {"requestId": rid, "request": r, "initiator": {"stack": {"callFrames": [{"url": script}]}}}


def _recorder(tmp_path, cdp, route=True):
    rec = d.Recorder(tmp_path, ["www.facebook.com"], [], [], route=route)
    rec.cdp = cdp
    return rec


def _records(tmp_path):
    return d.read_jsonl(tmp_path / "capture" / "requests.jsonl")


def test_a_body_in_the_event_is_recorded_via_event(tmp_path):
    rec = _recorder(tmp_path, FakeCdp())
    rec.on_request(_event("1", "https://www.facebook.com/ajax/other", post_data="a=1"))
    rec.drain()
    rec.close()
    (r,) = _records(tmp_path)
    assert r["via"] == "event" and not r["missing"] and base64.b64decode(r["body_b64"]) == b"a=1"


def test_a_body_missing_from_the_event_is_fetched_by_get_request_post_data(tmp_path):
    cdp = FakeCdp(post_data={"7": "q=" + CANARY})
    rec = _recorder(tmp_path, cdp)
    rec.on_request(_event("7", "https://www.facebook.com/ajax/other"))
    assert _records(tmp_path) == []  # not inside the handler: the fetch happens in drain()
    rec.drain()
    rec.close()
    (r,) = _records(tmp_path)
    assert r["via"] == "getRequestPostData" and not r["missing"] and CANARY.encode() in base64.b64decode(r["body_b64"])
    assert ("Network.getRequestPostData", {"requestId": "7"}) in cdp.calls


def test_a_body_nothing_can_fetch_stays_missing_and_counted(tmp_path):
    rec = _recorder(tmp_path, FakeCdp(fail=True))
    rec.on_request(_event("9", "https://www.facebook.com/ajax/other"))
    rec.drain()
    rec.close()
    (r,) = _records(tmp_path)
    assert r["missing"] is True and r["via"] == ""
    assert d.build_channels([r], [], "x")["posts_missing"] == 1


def test_route_captures_the_telemetry_paths_and_pairs_the_event_initiator(tmp_path):
    rec = _recorder(tmp_path, FakeCdp())
    url = "https://www.facebook.com/ajax/bnzai"
    rec.on_request(_event("3", url, script="https://static.xx.fbcdn.net/rsrc.php/v3/beacon.js"))  # a Blob: no body in the event
    route = FakeRoute(FakeRequest(url, b'{"u":"' + CANARY.encode() + b'"}'))
    rec.on_route(route)
    assert route.continued == 1  # forwarded unmodified
    rec.drain()
    rec.close()
    (r,) = _records(tmp_path)
    assert r["via"] == "route" and r["missing"] is False
    assert r["initiator"] == "https://static.xx.fbcdn.net/rsrc.php/v3/beacon.js"
    c = d.build_channels([r], [], "x")
    ep = c["endpoints"]["www.facebook.com/ajax/bnzai"]
    assert (c["posts_captured"], c["posts_missing"]) == (1, 0) and ep["via"] == {"route": 1}
    assert ep["fields"]["u"]["classes"] == {"str<%d>" % len(CANARY): 1}


def test_a_route_that_never_fired_leaves_the_event_counted_as_missing(tmp_path):
    rec = _recorder(tmp_path, FakeCdp())
    rec.on_request(_event("4", "https://www.facebook.com/ajax/qm/"))
    rec.drain()
    assert _records(tmp_path) == []  # may still be paired with a route that has not run yet
    rec.close()
    (r,) = _records(tmp_path)
    assert r["missing"] is True and r["url"].endswith("/ajax/qm/")


def test_route_comes_first_or_second_and_a_failing_read_still_forwards(tmp_path):
    rec = _recorder(tmp_path, FakeCdp())
    url = "https://www.facebook.com/ajax/bz"
    route = FakeRoute(FakeRequest(url, b"a=1"))
    rec.on_route(route)           # route before the event
    rec.on_request(_event("5", url))
    bad = FakeRoute(FakeRequest(url, RuntimeError("no body")))
    rec.on_route(bad)             # a read that raises
    other = FakeRoute(FakeRequest("https://elsewhere.example/x", b"z"))
    rec.on_route(other)           # not a post host: nothing recorded
    rec.close()
    assert route.continued == bad.continued == other.continued == 1
    recs = _records(tmp_path)
    assert sorted((r["via"], r["missing"]) for r in recs) == [("route", False), ("route", True)]
    assert recs[0]["initiator"] or recs[1]["initiator"]  # the one event's initiator went to one of them


def test_without_route_the_telemetry_paths_use_the_event_and_the_fetch(tmp_path):
    rec = _recorder(tmp_path, FakeCdp(post_data={"8": "k=v"}), route=False)
    rec.on_request(_event("8", "https://www.facebook.com/ajax/bz"))
    rec.drain()
    rec.close()
    (r,) = _records(tmp_path)
    assert r["via"] == "getRequestPostData"


# --- WebSocket frames: tolerant MQTT parse and the structural shape ------------------------------------------------------

def test_mqtt_parse_keeps_whole_packets_at_the_front_and_counts_the_rest():
    whole = _packet(3, 0, _mqtt_str("/t_ms") + b"{}")
    pk, partial = d.mqtt_parse(whole + b"\x30\x09abc")             # a trailing partial packet
    assert [p["topic"] for p in pk] == ["/t_ms"] and partial == 5
    pk, partial = d.mqtt_parse(whole + _packet(12, 0, b"") + b"\x01")
    assert [p["type"] for p in pk] == ["PUBLISH", "PINGREQ"] and partial == 1


def test_mqtt_parse_a_frame_that_starts_mid_packet_is_all_partial():
    pk, partial = d.mqtt_parse(b"\x00\x05hello world")
    assert pk == [] and partial == 13
    assert d.mqtt_parse(b"") == ([], 0)


def test_more_mqtt_types_are_recognised():
    for t, name in ((5, "PUBREC"), (6, "PUBREL"), (7, "PUBCOMP"), (15, "AUTH")):
        assert d.mqtt_packets(_packet(t, 0, b"\x00\x01"))[0]["type"] == name


def test_a_packet_shorter_than_its_type_can_be_is_not_a_packet():
    assert d.mqtt_parse(b"\x20\x00") == ([], 2) and d.mqtt_parse(b"\x60\x00") == ([], 2)
    assert d.mqtt_parse(b"\xc0\x00")[0][0]["type"] == "PINGREQ"


def test_mqtt_packets_still_gives_nothing_for_a_frame_with_a_remainder():
    assert d.mqtt_packets(_packet(3, 0, _mqtt_str("/a") + b"x") + b"\x30\x09abc") == []


def _ws_fixture():
    sock = "wss://gateway.facebook.com/ws/realtime"
    pub = _packet(3, 0, _mqtt_str("/t_ms") + json.dumps({"payload": CANARY}).encode())
    return [
        _frame(sock, "sent", pub),                                          # exact
        _frame(sock, "received", pub + b"\x30\x09abc"),                     # a whole packet, then a partial one (5 bytes)
        _frame(sock, "received", b"\x00\x05midpacket"),                     # starts mid-packet (11 bytes)
        _frame(sock, "received", bytes([0x30, 10]) + b"abc"),               # declared length longer than the frame (5 bytes)
        _frame(sock, "received", b"\x30\xff\xff\xff\xff\xff"),              # a length that never ends (6 bytes)
        _frame(sock, "sent", json.dumps({"op": CANARY}).encode(), opcode=1),   # text, JSON object
        _frame(sock, "received", b"42[\"x\"]", opcode=1),                   # text, digit first
    ]


def test_ws_shape_counts_frames_by_opcode_first_byte_length_and_first_char_class():
    c = d.build_channels([], _ws_fixture(), "x")
    ws = c["ws"]["gateway.facebook.com/ws/realtime"]
    shape = ws["shape"]
    assert shape["opcodes"] == {"1": 2, "2": 5}
    assert shape["first_byte"] == {"0x30": 4, "0x00": 1}
    assert shape["mqtt_length"] == {"exact": 1, "trailing": 2, "short": 1, "invalid": 1}
    assert shape["first_char"] == {"json-object": 1, "digit": 1}
    assert ws["topics"]["/t_ms"]["count"] == 2 and ws["topics"]["(partial)"]["count"] == 1
    assert ws["topics"]["(opaque)"]["count"] == 4 and ws["topics"]["(text)"]["count"] == 1
    assert ws["partial_bytes"] == 5 + 11 + 5 + 6


def test_ws_shape_holds_no_payload_bytes_beyond_the_first_byte():
    frames = _ws_fixture()
    text = json.dumps(d.build_channels([], frames, "x")) + json.dumps(d.build_matches([], frames, TRUTH))
    assert CANARY not in text and "midpacket" not in text


# --- compressed multipart parts (bnzai and bz: the file part post_0 is a zlib stream of JSON) -----------------------------
def _post0_body(inner, compress=zlib.compress):
    return _multipart([("__a", b"1", None), ("post_0", compress(inner), "post_0")])


POST0 = json.dumps([{"name": CANARY + "-z", "dm": 8, "uid": "100012345678901"}]).encode()


def test_a_zlib_file_part_of_json_is_walked_under_its_part_name():
    kind, f = d.fields(_post0_body(POST0), "multipart/form-data; boundary=" + BOUNDARY)
    assert kind == "multipart"
    assert ("post_0[].name", CANARY + "-z") in f and ("post_0[].dm", 8) in f
    assert not any(isinstance(v, d.Opaque) for _, v in f)


def test_gzip_and_raw_deflate_parts_are_walked_too():
    def raw_deflate(b):
        c = zlib.compressobj(wbits=-15)
        return c.compress(b) + c.flush()
    for packer in (gzip.compress, raw_deflate):
        _, f = d.fields(_post0_body(POST0, packer), "multipart/form-data; boundary=" + BOUNDARY)
        assert ("post_0[].dm", 8) in f, packer


def test_a_compressed_file_part_that_is_not_json_stays_opaque_with_its_length():
    packed = zlib.compress(b"plain text, not JSON " * 4)
    _, f = d.fields(_post0_body(b"plain text, not JSON " * 4), "multipart/form-data; boundary=" + BOUNDARY)
    (v,) = [v for p, v in f if p == "post_0"]
    assert d.value_class(v) == f"opaque<{len(packed)}>"


def test_a_compressed_part_without_a_filename_is_walked_too():
    body = _multipart([("q", zlib.compress(POST0), None)])
    _, f = d.fields(body, "multipart/form-data; boundary=" + BOUNDARY)
    assert ("q[].dm", 8) in f


def test_the_canary_inside_a_compressed_part_never_reaches_a_leaving_file(tmp_path):
    req = _req("https://www.facebook.com/ajax/bnzai", _post0_body(POST0))
    req["content_type"] = "multipart/form-data; boundary=" + BOUNDARY
    c = d.build_channels([req], [], "x")
    ep = c["endpoints"]["www.facebook.com/ajax/bnzai"]
    assert ep["fields"]["post_0[].uid"]["classes"] == {"id": 1}
    m = d.build_matches([req], [], TRUTH)
    assert any(r["field"] == "post_0[].dm" and r["surface"] == "navigator.deviceMemory" for r in m)
    text = json.dumps(c) + json.dumps(m)
    assert CANARY not in text and "100012345678901" not in text


# --- the gateway's WebSocket framing: [type 0x0c-0x0f][2-byte stream id][3-byte LE length][payload], chunks back to back --
def _gw(b0, payload, sid=b"\x01\x02"):
    return bytes([b0]) + sid + len(payload).to_bytes(3, "little") + payload


GW = "wss://gateway.facebook.com/ws/lightspeed"


def _gw_topics(frames):
    return d.build_channels([], frames, "x")["ws"]["gateway.facebook.com/ws/lightspeed"]["topics"]


def test_single_byte_frames_are_keepalives_keyed_by_their_byte():
    t = _gw_topics([_frame(GW, "sent", b"\x09"), _frame(GW, "received", b"\x0a"), _frame(GW, "received", b"\x0a")])
    assert t["09/(single)"]["count"] == 1 and t["0a/(single)"]["count"] == 2
    assert "(opaque)" not in t


def test_a_type_0c_chunk_carries_mqtt_at_offset_6():
    pub = _packet(3, 0, _mqtt_str("/t_ms") + json.dumps({"payload": CANARY, "dm": 8}).encode())
    t = _gw_topics([_frame(GW, "received", _gw(0x0c, pub))])
    assert t["0c//t_ms"]["count"] == 1 and t["0c//t_ms"]["fields"]["payload"]["count"] == 1
    assert "(opaque)" not in t


def test_a_type_0d_chunk_skips_two_prefix_bytes_before_its_json():
    t = _gw_topics([_frame(GW, "sent", _gw(0x0d, b"\x01\x00" + json.dumps({"k": CANARY, "dm": 8}).encode()))])
    assert t["0d/(json)"]["fields"]["dm"] == {"count": 1, "classes": {"int": 1}}


def test_a_type_0f_chunk_carries_json_at_offset_6_and_a_frame_may_hold_two_chunks():
    one, two = json.dumps({"a": 1}).encode(), json.dumps({"b": 2}).encode()
    t = _gw_topics([_frame(GW, "received", _gw(0x0f, one) + _gw(0x0f, two))])
    assert t["0f/(json)"]["count"] == 2 and set(t["0f/(json)"]["fields"]) == {"a", "b"}


def test_a_two_byte_type_0c_chunk_is_an_ack_counter_not_an_empty_mqtt_packet():
    t = _gw_topics([_frame(GW, "sent", _gw(0x0c, b"\x05\x00")), _frame(GW, "received", _gw(0x0c, b"\x20\x00"))])
    assert t == {"0c/(ack)": {"count": 2, "fields": {}}}


def test_a_type_0d_chunk_with_a_binary_header_before_its_json_is_counted_by_that_header_length():
    body = json.dumps({"k": CANARY, "dm": 8}).encode()
    t = _gw_topics([_frame(GW, "sent", _gw(0x0d, b"\x01\x80\x2c\x18\xc6\x2d" + body)),    # 4 bytes after the 2-byte prefix
                    _frame(GW, "sent", _gw(0x0d, b"\x02\x80\x3c\x16\x4a\x18\x0d" + body))])  # 5 bytes
    assert t["0d/(json+4)"]["fields"]["dm"]["count"] == 1 and t["0d/(json+5)"]["count"] == 1


def test_a_chunk_that_is_neither_json_nor_mqtt_is_opaque_under_its_type():
    t = _gw_topics([_frame(GW, "received", _gw(0x0c, b"\x00\x01\x02")), _frame(GW, "received", _gw(0x0d, b"\x00\x00" + b"\xff" * 5))])
    assert t["0c/(opaque)"]["count"] == 1 and t["0d/(opaque)"]["count"] == 1


def test_bytes_after_the_last_whole_chunk_are_partial_and_a_non_gateway_frame_is_untouched():
    pub = _packet(3, 0, _mqtt_str("/t_ms") + b"{}")
    fr = [_frame(GW, "received", _gw(0x0f, b"{}") + b"\x0c\x01\x02\x09\x00\x00ab"),    # a cut chunk (8 bytes)
          _frame(GW, "received", pub)]
    c = d.build_channels([], fr, "x")["ws"]["gateway.facebook.com/ws/lightspeed"]
    assert c["partial_bytes"] == 8 and c["topics"]["/t_ms"]["count"] == 1 and c["topics"]["(partial)"]["count"] == 1


def test_gateway_chunks_keep_the_shape_counters_and_leak_no_value(tmp_path):
    fr = [_frame(GW, "sent", _gw(0x0d, b"\x01\x00" + json.dumps({"k": CANARY, "dm": 8}).encode())), _frame(GW, "sent", b"\x09")]
    c = d.build_channels([], fr, "x")["ws"]["gateway.facebook.com/ws/lightspeed"]
    assert c["shape"]["first_byte"] == {"0x0d": 1, "0x09": 1}
    text = json.dumps(c) + json.dumps(d.build_matches([], fr, TRUTH))
    assert CANARY not in text
    m = d.build_matches([], fr, TRUTH)
    assert any(r["endpoint"] == "gateway.facebook.com/ws/lightspeed 0d/(json)" and r["field"] == "dm" for r in m)


# --- short strings are weak -------------------------------------------------------------------------------------------
def test_a_string_of_three_characters_or_fewer_is_a_weak_match():
    truth = {"connection.effectiveType": "4g", "timezone": "Europe/Berlin"}
    assert d.match("4g", truth) == [("connection.effectiveType", "exact", True)]
    assert d.match("Europe/Berlin", truth) == [("timezone", "exact", False)]
    assert d.match("abc", {"x": "abc"}) == [("x", "exact", True)] and d.match("abcd", {"x": "abcd"}) == [("x", "exact", False)]


# --- --rederive: the outputs again from a kept capture, no browser ---------------------------------------------------------
def test_rederive_rewrites_channels_and_matches_from_a_kept_capture(tmp_path):
    reqs, frames = _fixture()
    cap = tmp_path / "capture"
    cap.mkdir()
    (cap / "requests.jsonl").write_text("\n".join(json.dumps(r) for r in reqs) + "\n", encoding="utf-8")
    (cap / "ws.jsonl").write_text("\n".join(json.dumps(f) for f in frames) + "\n", encoding="utf-8")
    (tmp_path / "truth.json").write_text(json.dumps(TRUTH), encoding="utf-8")
    (tmp_path / "channels.json").write_text("stale", encoding="utf-8")
    assert d.main(["--rederive", str(tmp_path), "--arm", "3w"]) == 0
    c = json.loads((tmp_path / "channels.json").read_text(encoding="utf-8"))
    assert c["arm"] == "3w" and c["posts_captured"] == 3
    assert json.loads((tmp_path / "matches.json").read_text(encoding="utf-8"))
    assert CANARY not in (tmp_path / "channels.json").read_text(encoding="utf-8")


def test_a_live_run_still_needs_its_arguments():
    with pytest.raises(SystemExit):
        d.parse_args(["--arm", "3w"])
