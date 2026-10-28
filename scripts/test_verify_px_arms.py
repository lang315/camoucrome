"""The row logic of verify_px_arms.py on made-up page readings (the browser part runs on the box)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import verify_px_arms as v  # noqa: E402

GOOD = {
    "stock": {"canvas": "a", "audio": "x", "geom": "800"},
    "F": {"canvas": "b", "audio": "y", "geom": "1366"},
    "N": {"canvas": "a", "audio": "x", "geom": "1366"},
    "S2": {"canvas": "b", "audio": "y", "geom": "800"},
}


def test_every_row_passes_on_the_expected_readings():
    assert all(ok for ok, _ in v.rows(GOOD))


def test_a_noise_that_did_not_go_away_fails_n1():
    bad = {**GOOD, "N": {**GOOD["N"], "canvas": "b"}}
    assert [ok for ok, t in v.rows(bad) if t.startswith("N1")] == [False]


def test_a_fork_that_equals_stock_fails_the_red_rows():
    bad = {**GOOD, "F": GOOD["stock"]}
    failed = {t[:2] for ok, t in v.rows(bad) if not ok}
    assert {"R1", "R2", "R3"} <= failed


def test_s2_still_claiming_a_screen_fails_s1():
    bad = {**GOOD, "S2": {**GOOD["S2"], "geom": "1366"}}
    assert [ok for ok, t in v.rows(bad) if t.startswith("S1")] == [False]


def test_configs_drop_only_the_arms_own_keys():
    cfg = {"canvas:seed": 1, "audio:seed": 2, "screen.width": 3, "window.outerWidth": 4, "navigator.hardwareConcurrency": 5}
    c = v.configs(cfg)
    assert set(c["N"]) == {"screen.width", "window.outerWidth", "navigator.hardwareConcurrency"}
    assert set(c["S2"]) == {"canvas:seed", "audio:seed", "navigator.hardwareConcurrency"}
    assert c["F"] == cfg and c["stock"] == {}
