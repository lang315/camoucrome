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
