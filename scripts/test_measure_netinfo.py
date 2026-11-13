"""verdicts() of measure_netinfo: V1-V4 over synthetic launch records."""
import measure_netinfo as m


def rec(rtt=100, downlink=10.0, eff="4g", **kw):
    w = {"effectiveType": eff, "rtt": rtt, "downlink": downlink, "saveData": False, "hasType": False}
    base = {"fetched": 10, "win": dict(w), "worker": dict(w), "audio": [2, 2]}
    base.update(kw)
    return base


def arm(n=10, **kw):
    return [rec(**kw) for _ in range(n)]


def ok(stock, fork, prefix):
    hits = [v for name, v, _ in m.verdicts(stock, fork) if name.startswith(prefix)]
    assert len(hits) == 1, (prefix, hits)
    return hits[0]


def test_all_pass():
    rows = m.verdicts(arm(), arm())
    assert [n[:2] for n, _, _ in rows] == ["V1", "V2", "V3", "V4"]
    assert all(v is True for _, v, _ in rows), rows


def test_v1_fails_on_worker_exact_key_mismatch():
    fork = arm()
    fork[0]["worker"]["saveData"] = True
    assert ok(arm(), fork, "V1") is False


def test_v1_fails_when_fork_worker_rtt_out_of_stock_worker_range():
    fork = arm()
    for r in fork:
        r["worker"]["rtt"] = 300
    assert ok(arm(), fork, "V1") is False


def test_v1_passes_on_salted_estimates_like_stock():
    # run 20261113-025840: stock's own worker downlink differs from its window in 10 of 10 launches
    stock, fork = arm(), arm()
    for i, r in enumerate(stock + fork):
        r["worker"]["downlink"] = r["win"]["downlink"] + (0.05 if i % 2 else -0.05)
    assert ok(stock, fork, "V1") is True


def test_v1_ignores_worker_timeout():
    fork = arm()
    fork[0]["worker"] = None
    assert ok(arm(), fork, "V1") is True


def test_v2_fails_on_other_effective_type():
    fork = arm()
    fork[0]["win"]["effectiveType"] = "3g"
    assert ok(arm(), fork, "V2") is False


def test_v2_fails_on_type_in_one_arm():
    fork = arm()
    for r in fork:
        r["win"]["hasType"] = True
    assert ok(arm(), fork, "V2") is False


def test_v3_fails_when_fork_median_rtt_out_of_stock_range():
    stock = [rec(rtt=100 + i) for i in range(10)]
    assert ok(stock, arm(rtt=300), "V3") is False


def test_v3_fails_on_rtt_zero_excess():
    fork = arm(rtt=100)
    for r in fork[:3]:
        r["win"]["rtt"] = 0
    assert ok(arm(), fork, "V3") is False


def test_v4_fails_on_six_channels():
    fork = arm()
    fork[0]["audio"] = [6, 6]
    assert ok(arm(), fork, "V4") is False


def test_v4_skips_audio_null():
    fork = arm()
    for r in fork[:6]:
        r["audio"] = None
    assert ok(arm(), fork, "V4") is None


def test_unwarmed_records_are_unmeasured():
    fork = arm(fetched=3)
    assert ok(arm(), fork, "V2") is None
    assert ok(arm(), fork, "V3") is None
