"""stock_seed.py: the stock control's seeded profiles. No browser runs here: the priming launch is a fake that
writes what a primed template holds."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import stock_seed  # noqa: E402


def write_template(profile, clean=True, streak=0, fetched=True, seed=b"seed-bytes", extra=("Preferences",)):
    p = pathlib.Path(profile)
    p.mkdir(parents=True, exist_ok=True)
    state = {"variations_crash_streak": streak,
             "user_experience_metrics": {"stability": {"exited_cleanly": clean}}}
    if fetched:
        state["variations_last_fetch_time"] = "13438582540561681"
    (p / "Local State").write_text(json.dumps(state), encoding="utf-8")
    (p / "Variations").write_bytes(b"v" * 86)
    (p / "VariationsSeedV2").write_bytes(seed)
    for name in extra:  # profile-level state a copy must NOT carry
        (p / name).write_text("profile-identity", encoding="utf-8")


def test_unseeded_modes_flags_the_modes_whose_navigator_has_protected_audience():
    docs = {"headed": {"navProto": ["vendor", "joinAdInterestGroup"]}, "headless": {"navProto": ["vendor"]}, "x": {}}
    assert stock_seed.unseeded_modes(docs) == ["headed"]
    assert stock_seed.unseeded_modes({"headed": {"navProto": ["vendor"]}}) == []


def test_guard_is_red_on_an_unseeded_page_and_silent_on_a_seeded_one():
    stock_seed.guard(False, "control/headed")
    with pytest.raises(stock_seed.Unseeded, match="UNSEEDED.*control/headed"):
        stock_seed.guard(True, "control/headed")


def test_template_is_primed_once_and_each_launch_gets_its_own_copy(tmp_path):
    primes = []

    def prime_fn(profile):
        primes.append(profile)
        write_template(profile)

    with stock_seed.SeededStock(prime_fn, tmp_path) as s:
        copies = [pathlib.Path(s.fresh_copy()) for _ in range(6)]  # more than the 4 killed launches a seed survives
        assert len(primes) == 1 and s.primed == 1
        assert len(set(copies)) == 6 and all(c != s.template for c in copies)
        for c in copies:
            assert sorted(x.name for x in c.iterdir()) == sorted(stock_seed.SEED_FILES)  # only the seed, no profile state
            assert (c / "VariationsSeedV2").read_bytes() == b"seed-bytes"
            assert json.loads((c / "Local State").read_text())["variations_crash_streak"] == 0
        # a launch that dirties its copy does not touch the template or a sibling
        (copies[0] / "Local State").write_text("{}")
        assert json.loads((s.template / "Local State").read_text())["variations_crash_streak"] == 0
        assert json.loads((copies[1] / "Local State").read_text())["variations_last_fetch_time"]


def test_seed_fills_a_callers_own_directory(tmp_path):
    with stock_seed.SeededStock(write_template, tmp_path) as s:
        dest = tmp_path / "caller"
        dest.mkdir()
        s.seed(dest)
        assert (dest / "VariationsSeedV2").exists() and not (dest / "Preferences").exists()


def test_everything_is_removed_on_exit_and_on_an_error(tmp_path):
    with stock_seed.SeededStock(write_template, tmp_path) as s:
        root = s._root
        first = s.fresh_copy()
        s.drop(first)
        assert not pathlib.Path(first).exists()
        s.fresh_copy()
        assert root.exists()
    assert not root.exists() and list(tmp_path.iterdir()) == []
    with pytest.raises(RuntimeError, match="boom"):
        with stock_seed.SeededStock(write_template, tmp_path) as s:
            root = s._root
            raise RuntimeError("boom")
    assert not root.exists()


@pytest.mark.parametrize("kw, why", [
    ({"fetched": False}, "never fetched"),
    ({"seed": b""}, "empty"),
    ({"clean": False}, "clean exit"),
    ({"streak": 2}, "crash_streak is 2"),
])
def test_a_template_that_is_not_usable_is_unmeasured_and_cleaned_up(tmp_path, kw, why):
    roots = []

    def bad(profile):
        roots.append(profile)
        write_template(profile, **kw)

    with pytest.raises(stock_seed.Unseeded, match=why):
        with stock_seed.SeededStock(bad, tmp_path):
            pytest.fail("a bad template must not be handed out")
    assert list(tmp_path.iterdir()) == []


def test_a_priming_launch_that_wrote_nothing_is_unseeded(tmp_path):
    with pytest.raises(stock_seed.Unseeded, match="no Local State"):
        with stock_seed.SeededStock(lambda p: None, tmp_path):
            pass
    assert list(tmp_path.iterdir()) == []


def test_prime_closes_gracefully_through_winhost_and_names_the_stock_exe():
    calls = []

    class W:
        def cdp_eval(self, page, **kw):
            calls.append(kw)

    stock_seed.prime(W(), r"D:\stock\156.0.8078.80\chrome.exe", r"D:\p", True, ("--x",), wait_ms=1234)
    kw = calls[0]
    assert kw["graceful_close"] is True and kw["exe"].endswith("chrome.exe") and kw["profile"] == r"D:\p"
    assert kw["wait_ms"] == 1234 and kw["args"] == ("--x",) and kw["headed"] is True
