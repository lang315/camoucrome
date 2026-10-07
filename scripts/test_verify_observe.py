"""verify_observe.off_arm on synthetic event lists (the browser run is on the box)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import verify_observe as v  # noqa: E402

CAMOU = {"name": "Navigator.userAgent.get", "cat": v.CATEGORY}
OTHER = {"name": "ParseHTML", "cat": "blink"}


def test_off_arm_needs_zero_camou_events_and_some_other_events():
    assert v.off_arm([OTHER, OTHER]) == (True, 0, 2)
    assert v.off_arm([OTHER, CAMOU]) == (False, 1, 1)
    # an empty trace measured nothing: tracing may not have run at all
    assert v.off_arm([]) == (False, 0, 0)
    assert v.off_arm([{"name": "thread_name", "cat": "__metadata"}]) == (False, 0, 0)
    assert v.off_arm(None) == (False, None, None)
