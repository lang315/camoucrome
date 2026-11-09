import measure_observe_cost as m

def test_shift_inside_a_range_passes():
    a = {"ua_200k_ms": [10.0, 12.0, 11.0, 13.0, 11.5]}
    b = {"ua_200k_ms": [11.0, 12.5, 11.8, 12.0, 11.2]}
    v = m.verdict(a, b)
    assert v["ua_200k_ms"][0] == "PASS"

def test_shift_beyond_a_range_fails():
    a = {"ua_200k_ms": [10.0, 10.5, 10.2, 10.4, 10.1]}
    b = {"ua_200k_ms": [14.0, 14.2, 13.9, 14.1, 14.3]}
    assert m.verdict(a, b)["ua_200k_ms"][0] == "FAIL"

def test_unequal_metric_sets_refuse():
    import pytest
    with pytest.raises(ValueError):
        m.verdict({"x": [1.0]}, {"y": [1.0]})

def test_fewer_than_five_runs_refuse():
    import pytest
    with pytest.raises(ValueError):
        m.verdict({"x": [1.0] * 4}, {"x": [1.0] * 4})

def test_session_state_keeps_states_only():
    q = (" USERNAME  SESSIONNAME  ID  STATE   IDLE TIME  LOGON TIME\n"
         ">someone   console       1  Active      none   1/1/2026 1:00 AM\n"
         " other     rdp-tcp#3     2  Disc        4:10   1/1/2026 1:00 AM\n")
    assert m.session_state(q) == "Active,Disc"
    assert m.session_state("") == "none"

def test_post_loops_name_three_metrics():
    import re
    names = re.findall(r"\b(\w+_ms)\s*:", m.POST_PAGE)
    assert sorted(names) == ["post_500_ms", "post_blob_200_ms", "ws_2000_ms"]
    assert sorted(set(re.findall(r"\w+_ms", m.POST_PAGE))) == sorted(names)  # quoted keys too
