import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lib_argv import argv_diff  # noqa: E402

EXPECTED = {"--no-first-run", "--headless=new", "--remote-debugging-pipe"}
SELF = {"--noerrdialogs", "--ozone-platform=headless"}


def test_clean_env_view_without_the_self_added_flags_passes():
    assert argv_diff(EXPECTED, EXPECTED, SELF) == ([], [])


def test_rewritten_title_view_with_the_self_added_flags_passes():
    assert argv_diff(EXPECTED | SELF, EXPECTED, SELF) == ([], [])


def test_a_bogus_extra_flag_fails():
    assert argv_diff(EXPECTED | {"--disable-features=X"}, EXPECTED, SELF) == (["--disable-features=X"], [])


def test_a_missing_driver_flag_fails():
    assert argv_diff(EXPECTED - {"--headless=new"}, EXPECTED, SELF) == ([], ["--headless=new"])


def test_a_self_added_flag_does_not_excuse_a_missing_driver_flag():
    assert argv_diff((EXPECTED - {"--no-first-run"}) | SELF, EXPECTED, SELF) == ([], ["--no-first-run"])
