import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import measure_audio_text as m  # noqa: E402


def dom(text):
    return f'<html><head></head><body><pre id="r">{text}</pre></body></html>'


def test_parse_reads_a_finished_probe():
    got = m.parse(dom('{"fpjs":"35.7","bufSha":"ab","text":{"Arial":[1,2,3,4,5]},"done":true}'))
    assert got["fpjs"] == "35.7" and got["text"]["Arial"] == [1, 2, 3, 4, 5]


def test_parse_unescapes_html_entities():
    got = m.parse(dom('{"fpjs":"1","bufSha":"a&amp;b","text":{},"done":true}'))
    assert got["bufSha"] == "a&b"


def test_unfinished_probe_is_unmeasured():
    assert m.parse(dom("pending")) is None
    assert m.parse(dom('{"error":"TypeError: x"}')) is None
    assert m.parse("<html><body></body></html>") is None


def test_summary_counts_distinct_values_per_probe():
    a = {"fpjs": "35.7", "bufSha": "ab", "text": {"Arial": [1, 2, 3, 4, 5]}}
    b = {"fpjs": "35.7", "bufSha": "ab", "text": {"Arial": [1, 2, 3, 4, 6]}}
    assert m.summarize([a, b]) == {"fpjs": 1, "bufSha": 1, "text.Arial": 2}


def test_summary_of_no_measured_launch_is_empty():
    assert m.summarize([]) == {}
