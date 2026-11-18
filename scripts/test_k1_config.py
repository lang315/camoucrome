import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import k1_config  # noqa: E402

LIMIT = 30000  # launcher.CONFIG_CHUNK_CHARS


def chunks(raw, limit=LIMIT):
    """launcher.config_env's rule: one string when it fits, else name_1..N."""
    return 1 if len(raw) <= limit else -(-len(raw) // limit)


def test_small_config_is_padded_past_one_chunk():
    small = {"navigator.hardwareConcurrency": 8, "fonts:list": ["Arial", "Segoe UI"] * 50}
    assert chunks(json.dumps(small)) == 1  # the old K1 premise: this FAILs `len(chunks) >= 2`
    padded = k1_config.over_one_chunk(small, LIMIT)
    assert chunks(json.dumps(padded)) >= 2
    assert set(padded["fonts:list"]) == set(small["fonts:list"]) and set(padded) == set(small)


def test_already_long_config_is_unchanged_in_content():
    big = {"fonts:list": ["Arial"] * 6000}
    assert len(json.dumps(big)) > LIMIT
    assert k1_config.over_one_chunk(big, LIMIT)["fonts:list"] == big["fonts:list"]


def test_no_fonts_list_raises():
    with pytest.raises(ValueError):
        k1_config.over_one_chunk({"a": 1}, LIMIT)
