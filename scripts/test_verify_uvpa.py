"""verify_uvpa: the comparison and the row verdicts (the browsers run on the host)."""
import verify_uvpa as v


def test_equal_readings_compare_true():
    assert v.compare({"uvpa": False, "caps": None}, {"uvpa": False, "caps": None}) is True


def test_a_different_uvpa_compares_false():
    assert v.compare({"uvpa": False, "caps": None}, {"uvpa": True, "caps": None}) is False


def test_a_capabilities_dict_differing_on_one_key_compares_false():
    assert v.compare({"uvpa": True, "caps": {"a": True, "b": False}}, {"uvpa": True, "caps": {"a": True, "b": True}}) is False


R = {"pkc": "function", "uvpa": False, "caps": None, "errors": []}


def test_rows_pass_when_both_fork_arms_equal_stock():
    assert [ok for _, ok, _ in v.rows({"stock": R, "F0": dict(R), "F": dict(R)})] == [True, True]


def test_plant_turns_both_rows_red():
    assert [ok for _, ok, _ in v.rows({"stock": R, "F0": dict(R), "F": dict(R)}, plant=True)] == [False, False]


def test_an_arm_without_publickeycredential_is_unmeasured_not_pass():
    gone = {"pkc": "undefined", "uvpa": None, "caps": None, "errors": []}
    got = v.rows({"stock": R, "F0": gone, "F": dict(R)})
    assert [ok for _, ok, _ in got] == [None, True] and "F0" in got[0][2]
    assert [ok for _, ok, _ in v.rows({"stock": None, "F0": dict(R), "F": dict(R)})] == [None, None]


def test_a_note_names_the_host_without_a_platform_authenticator():
    assert "no platform authenticator" in v.stock_note({"stock": dict(R, uvpa=False)})
    assert v.stock_note({"stock": dict(R, uvpa=True)}) is None
    assert v.stock_note({"stock": None}) is None
