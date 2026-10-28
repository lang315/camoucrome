"""The verdict logic of verify_geoip_pixelscan on constructed page texts. The browser run is the host's."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import verify_geoip_pixelscan as v  # noqa: E402

CLEAN, SPOOFED = "Your fingerprint\nNo masking detected", "Your fingerprint\nTimezone spoofed\nMasking detected"


def test_pass_needs_stock_clean_red_flagged_green_clean():
    assert v.verdict(CLEAN, SPOOFED, CLEAN)[0] == 0


def test_a_red_that_does_not_trip_fails_because_the_check_would_measure_nothing():
    code, line = v.verdict(CLEAN, CLEAN, CLEAN)
    assert code == 1 and "measures nothing" in line


def test_a_green_that_is_still_flagged_fails():
    assert v.verdict(CLEAN, SPOOFED, SPOOFED)[0] == 1


def test_a_flagged_stock_fails_because_the_page_flags_something_else():
    code, line = v.verdict(SPOOFED, SPOOFED, CLEAN)
    assert code == 1 and "stock" in line


def test_an_unsettled_load_is_unmeasured_not_a_pass_or_a_fail():
    assert v.verdict(CLEAN, None, CLEAN)[0] == 3
