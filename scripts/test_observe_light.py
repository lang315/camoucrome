"""observe_light.py on hand-made arm dirs (no browser): kinds, counts, MB and ms only."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import observe_light as L  # noqa: E402

TYPES = {"URL_REQUEST_START_JOB": 1, "HTTP_TRANSACTION_SEND_REQUEST": 2,
         "HTTP_TRANSACTION_READ_RESPONSE_HEADERS": 3, "URL_REQUEST_JOB_BYTES_READ": 4}


def _netlog(reqs):
    """reqs: (url, content_type, bytes, sent) per request."""
    ev = []
    for i, (url, ct, n, sent) in enumerate(reqs, 1):
        src = {"id": i}
        ev.append({"type": 1, "source": src, "params": {"url": url, "method": "GET",
                                                        "network_isolation_key": "https://www.facebook.invalid https://www.facebook.invalid"}})
        if sent:
            ev.append({"type": 2, "source": src, "params": {}})
        ev.append({"type": 3, "source": src, "params": {"headers": [f"content-type: {ct}", "set-cookie: CANARY_COOKIE=1"]}})
        ev.append({"type": 4, "source": src, "params": {"byte_count": n}})
    return {"constants": {"logEventTypes": TYPES}, "events": ev}


def _arm(tmp, name, video=4, js_cached=True, ram=True, loads=True):
    d = tmp / name
    d.mkdir()
    reqs = [(f"https://video.invalid/v{i}.mp4?token=CANARY_Q", "video/mp4", 1_000_000, True) for i in range(video)]
    reqs += [("https://static.invalid/a.js", "text/javascript", 500_000, True),
             ("https://static.invalid/b.js", "text/javascript", 500_000, not js_cached)]
    (d / "net.json").write_text(json.dumps(_netlog(reqs)))
    if ram:
        (d / "ram.json").write_text(json.dumps({"interval_s": 6, "samples": [
            {"t": 0, "by_type": {"renderer": 400 * 2**20, "utility": 100 * 2**20}},
            {"t": 6, "by_type": {"renderer": 600 * 2**20, "utility": 300 * 2**20}}]}))
    if loads:
        (d / "loads.json").write_text(json.dumps([{"path": "/", "ms": 1200}, {"path": "/watch/", "ms": 900}]))
    return d


def test_identical_arms_give_zero_deltas(tmp_path):
    # the RED for the compare: the same numbers on both sides must read as no change
    a, b = _arm(tmp_path, "a"), _arm(tmp_path, "b")
    cmp = L.compare(L.arm_numbers(a), L.arm_numbers(b))
    assert cmp["delta_pct"]["video_requests"] == 0
    assert cmp["delta_pct"]["total_network_mb"] == 0


def test_half_the_video_requests_reads_minus_50(tmp_path):
    cmp = L.compare(L.arm_numbers(_arm(tmp_path, "a", video=4)), L.arm_numbers(_arm(tmp_path, "b", video=2)))
    assert cmp["delta_pct"]["video_requests"] == -50
    assert cmp["delta_pct"]["video_mb"] == -50
    assert cmp["b"]["video"]["mb_per_request"] == 1.0


def test_numbers_read_back(tmp_path):
    n = L.arm_numbers(_arm(tmp_path, "a"))
    assert n["js"] == {"network_mb": 0.5, "cache_mb": 0.5}
    assert n["ram"]["renderer"] == {"peak_mb": 600.0, "mean_mb": 500.0}
    assert n["loads"] == [{"path": "/", "ms": 1200}, {"path": "/watch/", "ms": 900}]
    assert n["cpu"] == {"top_s": None, "all_s": None}  # no trace.json: CPU unknown, not zero


@pytest.mark.parametrize("missing", ["ram", "loads"])
def test_a_missing_file_is_unmeasured(tmp_path, missing):
    d = _arm(tmp_path, "a", **{missing: False})
    with pytest.raises(L.Unmeasured, match=f"{missing}.json"):
        L.arm_numbers(d)


def test_a_cold_warm_arm_is_unmeasured(tmp_path):
    a, b = _arm(tmp_path, "a"), _arm(tmp_path, "b", js_cached=False)
    with pytest.raises(L.Unmeasured, match="cache cold"):
        L.compare(L.arm_numbers(a), L.arm_numbers(b))


def test_outputs_hold_no_query_cookie_or_url(tmp_path):
    a, b = _arm(tmp_path, "a"), _arm(tmp_path, "b", video=2)
    rc = L.main([str(a), str(b), "--out", str(tmp_path / "light.json"), "--md", str(tmp_path / "light.md")])
    assert rc == 0
    for f in ("light.json", "light.md"):
        t = (tmp_path / f).read_text()
        assert "CANARY" not in t and "video.invalid" not in t and "static.invalid" not in t, f


def test_cli_unmeasured_exit_3(tmp_path, capsys):
    a, b = _arm(tmp_path, "a"), _arm(tmp_path, "b", ram=False)
    assert L.main([str(a), str(b), "--out", str(tmp_path / "l.json"), "--md", str(tmp_path / "l.md")]) == 3
    assert capsys.readouterr().out.startswith("UNMEASURED light: b ram.json")


def test_render_lists_each_process_and_the_renderer_count(tmp_path):
    a, b = _arm(tmp_path, "a"), _arm(tmp_path, "b")
    (b / "ram.json").write_text(json.dumps({"interval_s": 6, "samples": [
        {"t": 0, "n_renderer": 2, "by_type": {"renderer": 500 * 2**20, "utility:network.mojom.NetworkService": 200 * 2**20,
                                              "gpu-process": 90 * 2**20}}]}))
    md = L.render(L.compare(L.arm_numbers(a), L.arm_numbers(b)))
    assert "| utility:network.mojom.NetworkService |  |  | 200.0 | 200.0 |" in md
    assert "| gpu-process |  |  | 90.0 | 90.0 |" in md
    assert "| renderer processes, most | unknown |  | 2 |  |" in md
