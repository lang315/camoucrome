"""verify_host_oracle's O1 comparison, without a browser.

The property worth a test is the one that is cheap to lose: a prefix exclusion
must stop applying the moment its condition no longer holds. `gpu` is excluded
because *this* machine has no GPU and the probe forces SwiftShader, so the fork
reports no adapter. On a machine with a GPU the same keys carry the host's real
hardware under a spoofed identity -- the thing O1 exists to catch -- and an
exclusion that keyed off the name alone would print "0 DIFF ... PASS" there.

Imported, not executed: the browser work is inside main(). The import does read
the committed baseline, so CAMOU_CLIENT is pointed at this repository first --
deliberately, rather than skipping when it is unset. A skipped test is a test
that measures nothing, and these cases need no build box.
"""
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
os.environ["CAMOU_CLIENT"] = str(ROOT)

import verify_host_oracle as vho  # noqa: E402 - must follow the CAMOU_CLIENT line

# A host with a WebGPU adapter, shaped like the committed baseline's subtree:
# two identity strings (shape-only), one feature list (shape-only) and three
# capability integers (compared exactly).
HOST = {
    "ua": "Mozilla/5.0 stock",
    "gpu": {
        "info": {"vendor": "intel", "architecture": "gen-9"},
        "features": ["depth-clip-control", "float32-filterable"],
        "limits": {"maxTextureDimension2D": 16384, "maxBindGroups": 4,
                   "maxComputeWorkgroupSizeX": 1024},
    },
}


def test_no_adapter_excludes_the_subtree_and_nothing_else():
    """Today's box: requestAdapter() -> null, so gpu.* has no fork value at all."""
    diffs, same, active = vho.compare(HOST, {"ua": "Mozilla/5.0 stock", "gpu": None})
    assert list(active) == ["gpu"], active
    assert diffs == [], diffs
    assert same == len(vho.flatten(HOST)) + 1  # + the fork's own bare "gpu" leaf


def test_a_real_adapter_is_compared_again():
    """RED: a different adapter must be reported, not swallowed by the prefix."""
    fork = {
        "ua": "Mozilla/5.0 stock",
        "gpu": {
            "info": {"vendor": "nvidia", "architecture": "turing"},
            "features": ["depth-clip-control"],
            "limits": {"maxTextureDimension2D": 32768, "maxBindGroups": 4,
                       "maxComputeWorkgroupSizeX": 1024},
        },
    }
    diffs, _, active = vho.compare(HOST, fork)
    assert active == {}, "the exclusion must lift once the fork reports an adapter"
    keys = [k for k, *_ in diffs]
    # The capability integer differs and is compared exactly. vendor/architecture
    # and features are shape-only by policy, so a same-typed difference there is
    # not O1's business -- that is what the WebGPU backlog item is for.
    assert "gpu.limits.maxTextureDimension2D" in keys, keys


def test_an_identity_difference_outside_gpu_is_still_a_diff():
    """The exclusion is scoped: it must not quiet a neighbouring key."""
    diffs, _, _ = vho.compare(HOST, {"ua": "Mozilla/5.0 FORK", "gpu": None})
    assert [k for k, *_ in diffs] == ["ua"], diffs


def test_every_prefix_exclusion_carries_a_reason_and_a_predicate():
    """A bare string entry would silently become unconditional again."""
    for prefix, value in vho.KNOWN_PREFIX.items():
        assert isinstance(value, tuple) and len(value) == 2, (prefix, value)
        reason, when = value
        assert isinstance(reason, str) and reason, prefix
        assert callable(when), prefix
        assert "backlog" in reason, f"{prefix}: an exclusion needs a named follow-up"
