"""step2_rows and oracle_rules without a browser (roadmap step 2)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_oracle_rules_shared():
    import oracle_rules
    assert "screen.width" in oracle_rules.SHAPE_ONLY and "audioFp" in oracle_rules.SHAPE_ONLY
    assert oracle_rules.flatten({"a": {"b": 1, "c": [2]}, "d": None}) == {"a.b": 1, "a.c": [2], "d": None}
