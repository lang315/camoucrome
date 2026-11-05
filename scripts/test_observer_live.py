import json

import observer_live as ol

TABLES = {
    "status": {"events": 9, "lost": 0, "truth_ok": True},
    "truth": {"screen.width": 1920, "navigator.userAgent": "TRUTH-UA-Mozilla"},
    "reads": [{"site": "https://www.facebook.com", "member": "Screen.width", "origin": "o", "script": "SCRIPT-URL-xyz",
               "count": 7, "by": "frame"}],
    "sends": [{"via": "http", "endpoint": "https://www.facebook.com/ajax/bz?__a=1&fb_dtsg=SECRET-TOKEN", "topic": "bz",
               "by": "frame", "count": 2, "bytes": 99, "kinds": {"json": 2},
               "fields": [{"path": "w", "count": 2, "classes": {"int": 2}, "samples": ["SAMPLE-1920", "SAMPLE-1080"],
                           "strong": [{"surface": "screen.width", "encoding": "plain", "count": 2}],
                           "weak": [{"surface": "screen.height", "encoding": "plain", "count": 1}], "bool": []}]}],
}
PLANTED = ["SAMPLE-1920", "SAMPLE-1080", "TRUTH-UA-Mozilla", "1920", "SECRET-TOKEN", "SCRIPT-URL-xyz", "fb_dtsg"]


def test_names_only_drops_values():
    out = json.dumps(ol.names_only(TABLES))
    for v in PLANTED:
        assert v not in out, v
    for keep in ("/ajax/bz", "screen.width", "screen.height", "Screen.width", '"int"'):
        assert keep in out, keep
    assert "samples" not in out and "truth" not in out


def test_names_only_shape():
    o = ol.names_only(TABLES)
    assert o["sends"] == [{"endpoint": "https://www.facebook.com/ajax/bz", "topic": "bz",
                           "fields": [{"path": "w", "classes": {"int": 2}, "strong": ["screen.width"],
                                       "weak": ["screen.height"]}]}]
    assert o["reads"] == [{"member": "Screen.width", "count": 7}]
    assert o["lost"] == 0
