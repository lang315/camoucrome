"""finch_switches: stock's variations command line (chrome://version/?show-variations-cmd) as a feature list."""
import pytest

import finch_switches as fs

# Fixture values are invented: no client data.
TEXT = ("--force-fieldtrials=StudyA/GroupA/*StudyB/GroupB/ "
        "--force-fieldtrial-params=StudyA.GroupA:k/v\n"
        "--enable-features=FeatOne<StudyA,*FeatTwo<StudyB,FeatThree:p/1 "
        "--disable-features=FeatFour<StudyB")


def test_parse_splits_the_four_switches():
    sw = fs.parse(TEXT)
    assert sw["features"]["enable"] == ["FeatOne<StudyA", "*FeatTwo<StudyB", "FeatThree:p/1"]
    assert sw["features"]["disable"] == ["FeatFour<StudyB"]
    assert sw["trials"] == "StudyA/GroupA/*StudyB/GroupB/"
    assert sw["params"] == "StudyA.GroupA:k/v"


def test_parse_output_has_only_known_keys():
    # Review Focus 3: nothing but features, trials and params leaves the parser (no client data keys).
    assert set(fs.parse(TEXT + " --variations-seed-version=1 --lang=xx")) == {"features", "trials", "params"}


def test_subset_unknown_name_raises():
    sw = fs.parse(TEXT)
    with pytest.raises(KeyError):
        fs.subset(sw, enable=["Nope"])
    with pytest.raises(KeyError):
        fs.subset(sw, disable=["FeatOne"])      # enabled, not disabled


def test_subset_keeps_named_tokens_in_order_and_toggles_trials_params():
    sw = fs.parse(TEXT)
    got = fs.subset(sw, enable=["FeatThree", "FeatOne"], disable=[], keep_params=False)
    assert got["features"] == {"enable": ["FeatOne<StudyA", "FeatThree:p/1"], "disable": []}
    assert got["params"] == "" and got["trials"] == sw["trials"]
    assert fs.subset(sw)["features"] == sw["features"]          # None keeps everything
    assert fs.subset(sw, keep_trials=False)["trials"] == ""


def test_argv_omits_empty():
    sw = fs.subset(fs.parse(TEXT), enable=["FeatOne"], disable=[], keep_trials=False, keep_params=False)
    assert fs.argv(sw) == ["--enable-features=FeatOne<StudyA"]
    assert fs.argv(fs.parse(TEXT)) == [
        "--force-fieldtrials=StudyA/GroupA/*StudyB/GroupB/", "--force-fieldtrial-params=StudyA.GroupA:k/v",
        "--enable-features=FeatOne<StudyA,*FeatTwo<StudyB,FeatThree:p/1", "--disable-features=FeatFour<StudyB"]


def test_parse_strips_quotes():
    quoted = ('--force-fieldtrials="StudyA/GroupA/*StudyB/GroupB/" '
              '--force-fieldtrial-params="StudyA.GroupA:k/v" '
              '--enable-features="FeatOne<StudyA,*FeatTwo<StudyB,FeatThree:p/1" '
              '--disable-features="FeatFour<StudyB"')
    assert fs.parse(quoted) == fs.parse(TEXT)
