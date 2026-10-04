"""parse_hosts on whole and truncated netlogs (no browser)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_sp7_phonehome as v

HEAD = '{"constants":' + json.dumps({"logEventTypes": {"REQUEST_ALIVE": 1}}) + ',\n"events": [\n'


def ev(url):
    return json.dumps({"type": 1, "params": {"url": url}})


def write(tmp_path, body):
    p = tmp_path / "netlog.json"
    p.write_text(HEAD + body)
    return str(p)


EVENTS = [ev("http://127.0.0.1:8000/"), ev("http://sb.test:8000/"),
          ev("https://safebrowsing.googleapis.com/v5/hashLists:batchGet")]


def test_whole_log(tmp_path):
    path = write(tmp_path, ",\n".join(EVENTS) + "\n]}\n")
    assert v.parse_hosts(path) == ({"safebrowsing.googleapis.com": 1}, 1, 1)


def test_cut_after_an_event(tmp_path):
    path = write(tmp_path, ",\n".join(EVENTS) + ",\n")
    assert v.parse_hosts(path) == ({"safebrowsing.googleapis.com": 1}, 1, 1)


def test_cut_mid_event_drops_only_the_partial_line(tmp_path):
    path = write(tmp_path, ",\n".join(EVENTS) + ",\n" + ev("https://x.example/")[:20])
    assert v.parse_hosts(path) == ({"safebrowsing.googleapis.com": 1}, 1, 1)


def test_cut_inside_polled_data(tmp_path):
    # Chrome's real shape: the last event closes the array on its own line.
    path = write(tmp_path, ",\n".join(EVENTS) + "],\n" + '"polledData": [{"a":')
    assert v.parse_hosts(path) == ({"safebrowsing.googleapis.com": 1}, 1, 1)


def test_a_bad_line_before_the_last_raises(tmp_path):
    import pytest
    path = write(tmp_path, ",\n".join([EVENTS[0], '{"type": 1, "par', *EVENTS[1:]]) + "\n]}\n")
    with pytest.raises(ValueError):
        v.parse_hosts(path)
