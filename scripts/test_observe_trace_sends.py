"""observe_trace_sends.py on a synthetic startup trace (no browser, no real values)."""
import base64
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "client" / "python"))
import observe_trace_sends as t  # noqa: E402

CAT = "disabled-by-default-camou.observe.send"
TRUTH = {"navigator.hardwareConcurrency": 12, "screen.width": 1366, "screen.height": 768,
         "navigator.userAgent": "Mozilla/5.0 (Planted; Test) AppleWebKit/537.36 Chrome/1.2.3.4"}
SITE = "http://127.0.0.1:8000"


def b64(b):
    return base64.b64encode(b).decode()


def ev(name, **args):
    return {"name": name, "cat": CAT, "ph": "I", "ts": 1, "pid": 1, "tid": 1, "args": args}


def http(loader, endpoint="127.0.0.1:8000/collect", ctype="application/json", elements=1, top_site=SITE):
    return ev("camou.send.http", loader=loader, endpoint=endpoint, method="POST", content_type=ctype,
              top_site=top_site, top_frame="", elements=elements)


def body(loader, element, offset, data, cut=""):
    return ev("camou.send.body", loader=loader, element=element, offset=offset, b64=b64(data), cut=cut)


def ws(text, site=SITE, endpoint="127.0.0.1:8000/sock", opcode=1, cut=""):
    raw = text.encode()
    return ev("camou.send.ws", endpoint=endpoint, site=site, origin=SITE, script="", opcode=opcode,
              size=len(raw), b64=b64(raw), cut=cut)


PLANTED = json.dumps({"hc": 12, "scr": "1366x768", "ua": TRUTH["navigator.userAgent"]}).encode()


def run(tmp_path, events, *extra, wrap=True):
    trace = tmp_path / "trace.json"
    trace.write_text(json.dumps({"traceEvents": events} if wrap else events))
    truth = tmp_path / "truth.json"
    truth.write_text(json.dumps(TRUTH))
    out = tmp_path / "out"
    rc = t.main([str(trace), "--truth", str(truth), "--out", str(out), *extra])
    return rc, out


def matches(out):
    return json.loads((out / "matches.json").read_text())


def summary(out):
    return json.loads((out / "trace_sends.json").read_text())


def test_json_post_matches_truth(tmp_path):
    rc, out = run(tmp_path, [http(1), body(1, 0, 0, PLANTED)])
    assert rc == 0
    got = {(m["endpoint"], m["field"], m["surface"], m["encoding"]) for m in matches(out)}
    assert ("127.0.0.1:8000/collect", "hc", "navigator.hardwareConcurrency", "exact") in got
    assert ("127.0.0.1:8000/collect", "scr", "screen", "WxH") in got
    assert ("127.0.0.1:8000/collect", "ua", "navigator.userAgent", "exact") in got
    ch = json.loads((out / "channels.json").read_text())
    assert ch["endpoints"]["127.0.0.1:8000/collect"]["kinds"] == {"json": 1}
    assert ch["endpoints"]["127.0.0.1:8000/collect"]["via"] == {"trace": 1}


def test_fragments_out_of_order_and_307_repeat_kept_once(tmp_path):
    a, b = PLANTED[:10], PLANTED[10:]
    evs = [http(1), body(1, 0, 10, b), body(1, 0, 0, a), body(1, 0, 0, a), body(1, 0, 10, b)]
    rc, out = run(tmp_path, evs)
    assert rc == 0
    assert any(m["surface"] == "screen" for m in matches(out))
    assert summary(out)["partial"] == 0
    assert json.loads((out / "channels.json").read_text())["endpoints"]["127.0.0.1:8000/collect"]["bytes"] == len(PLANTED)


def test_cut_element_is_counted_and_still_decoded(tmp_path):
    rc, out = run(tmp_path, [http(1), body(1, 0, 0, PLANTED, cut=1)])
    assert rc == 0
    assert summary(out)["cut"] == 1
    assert any(m["surface"] == "screen" for m in matches(out))


def test_file_element_length_only(tmp_path):
    evs = [http(1, ctype="multipart/form-data", elements=1), ev("camou.send.file", loader=1, element=0, size=5000)]
    rc, out = run(tmp_path, evs)
    assert rc == 0
    s = summary(out)
    assert s["file"] == 1 and s["missing"] == 0


def test_missing_body(tmp_path):
    rc, out = run(tmp_path, [http(1, elements=1), body(2, 0, 0, b"x"), http(3, endpoint="127.0.0.1:8000/other")] )
    assert rc == 0
    s = summary(out)
    assert s["missing"] == 2  # loaders 1 and 3 have elements>0 and nothing; the orphan body of 2 is dropped
    ch = json.loads((out / "channels.json").read_text())
    assert ch["posts_missing"] == 2


def test_partial_request_not_decoded_but_counted(tmp_path):
    evs = [http(1), body(1, 0, 5, PLANTED[5:])]  # does not start at offset 0
    rc, out = run(tmp_path, evs)
    assert rc == 0
    assert summary(out)["partial"] == 1
    assert matches(out) == []


def test_partial_when_element_missing(tmp_path):
    evs = [http(1, elements=2), body(1, 0, 0, PLANTED)]  # element 1 never arrived
    rc, out = run(tmp_path, evs)
    assert summary(out)["partial"] == 1
    assert matches(out) == []


def test_ws_text_frame(tmp_path):
    msg = json.dumps({"w": "1366x768", "hc": 12})
    rc, out = run(tmp_path, [ws(msg)])
    assert rc == 0
    got = {(m["endpoint"], m["field"], m["surface"]) for m in matches(out)}
    assert any(e.startswith("127.0.0.1:8000/sock") and f == "w" and s == "screen" for e, f, s in got)
    ch = json.loads((out / "channels.json").read_text())
    assert ch["ws"]["127.0.0.1:8000/sock"]["frames_sent"] == 1


def test_zero_send_events_is_unmeasured(tmp_path, capsys):
    read_only = {"name": "Navigator.hardwareConcurrency.get", "cat": "disabled-by-default-camou.observe",
                 "ph": "I", "args": {"origin": SITE, "site": SITE, "script": ""}}
    rc, out = run(tmp_path, [read_only])
    assert rc == 2
    assert "UNMEASURED: no send events (was disabled-by-default-camou.observe.send in --trace-startup?)" in capsys.readouterr().out
    assert not (out / "matches.json").exists()


def test_top_site_filter_and_worker_count(tmp_path):
    other = "http://other.test"
    evs = [http(1), body(1, 0, 0, PLANTED),
           http(2, endpoint="other.test/x", top_site=other), body(2, 0, 0, PLANTED),
           ws("hc 12", site=other, endpoint="other.test/s"),
           ws(json.dumps({"hc": 12}), site=""),  # a worker: no top site
           ]
    rc, out = run(tmp_path, evs, "--top-site", SITE)
    assert rc == 0
    ch = json.loads((out / "channels.json").read_text())
    assert list(ch["endpoints"]) == ["127.0.0.1:8000/collect"]
    assert "other.test/s" not in ch["ws"]
    assert len(ch["ws"]) == 1  # the worker message is kept
    assert summary(out)["no_site"] == 1


def test_uint_args_as_strings_and_bare_list_trace(tmp_path):
    h = http(1)
    h["args"]["loader"] = "1"
    h["args"]["elements"] = "1"
    b = body(1, 0, 0, PLANTED)
    b["args"].update(loader="1", element="0", offset="0")
    rc, out = run(tmp_path, [h, b], wrap=False)
    assert rc == 0 and any(m["surface"] == "screen" for m in matches(out))


def test_truncated_trace_file_is_read(tmp_path):
    # a startup trace killed before its closing brackets
    trace = tmp_path / "trace.json"
    trace.write_text('{"traceEvents":[' + ",".join(json.dumps(e) for e in [http(1), body(1, 0, 0, PLANTED)]) + ",")
    truth = tmp_path / "truth.json"
    truth.write_text(json.dumps(TRUTH))
    assert t.main([str(trace), "--truth", str(truth), "--out", str(tmp_path / "o")]) == 0


def test_print_truth_js(capsys):
    assert t.main(["--print-truth-js"]) == 0
    assert capsys.readouterr().out.lstrip().startswith("async () =>")


def test_top_site_matching_nothing_is_unmeasured(tmp_path, capsys):
    rc, out = run(tmp_path, [http(1), body(1, 0, 0, PLANTED)], "--top-site", "http://nomatch.test")
    assert rc == 2
    assert "UNMEASURED: --top-site matched none of the 1 send(s)" in capsys.readouterr().out
    assert not (out / "matches.json").exists()
