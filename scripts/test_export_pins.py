"""export.sh and check_checkout_sync.sh must write patch bytes that do not depend on the box's git state.

2026-10-23: the shared object store grew (the 157 fetch), git's auto-abbrev went from 10 to 11 hex,
every `index` line changed, and the sync gate failed on all 37 patches."""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent


def test_every_pinned_patch_diff_pins_the_index_abbrev():
    calls = [l for name in ("export.sh", "check_checkout_sync.sh")
             for l in (HERE / name).read_text().splitlines() if "diff --no-ext-diff" in l]
    assert len(calls) == 2
    assert all("--abbrev=10" in l for l in calls), calls
