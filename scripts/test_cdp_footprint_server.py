import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import cdp_footprint_server as s

PROBE = (pathlib.Path(__file__).parent / "cdp_footprint" / "probe.html").read_text()


def _get(port, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def test_delay_route_sleeps(tmp_path):
    srv, port = s.serve(tmp_path, delay_ms=50)
    t = time.monotonic()
    code, body = _get(port, "/delay?i=1")
    srv.shutdown()
    assert (code, body) == (200, b"ok") and time.monotonic() - t >= 0.05


def test_result_post_written_and_done_200(tmp_path):
    srv, port = s.serve(tmp_path)
    req = urllib.request.Request(f"http://127.0.0.1:{port}/result?arm=tdp&run=r1", b'{"L1": false}')
    assert urllib.request.urlopen(req).status == 200
    code, _ = _get(port, "/done?arm=tdp&run=r1")
    srv.shutdown()
    assert code == 200 and (tmp_path / "tdp-r1.json").read_text() == '{"L1": false}'


def test_done_404_before_post(tmp_path):
    srv, port = s.serve(tmp_path)
    code, _ = _get(port, "/done?arm=none&run=x")
    srv.shutdown()
    assert code == 404


def test_bad_arm_rejected_and_creepjs_traversal(tmp_path):
    srv, port = s.serve(tmp_path)
    req = urllib.request.Request(f"http://127.0.0.1:{port}/result?arm=..%2Fx&run=1", b"{}")
    try:
        urllib.request.urlopen(req)
        bad = 200
    except urllib.error.HTTPError as e:
        bad = e.code
    ok = _get(port, "/creepjs/creep.js")[0]
    trav = _get(port, "/creepjs/..%2Fcdp_footprint_server.py")[0]
    srv.shutdown()
    assert (bad, ok, trav) == (400, 200, 404)


def test_probe_html_has_contract_ids():
    for s_ in ('id="ready"', 'id="t1"', 'id="t2"', 'id="go"', "/result?arm="):
        assert s_ in PROBE
