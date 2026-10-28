"""The nm predicate of check_observe_flag_off.py, on text shaped like nm -C output."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import check_observe_flag_off as c  # noqa: E402


def test_references_observer_sees_emit_and_emitlistener_and_ignores_other_symbols():
    assert c.references_observer("U blink::camou_observe::Emit(char const*, v8::Isolate*)")
    assert c.references_observer("U blink::camou_observe::EmitListener(char const*, blink::ExecutionContext*)")
    assert not c.references_observer("T blink::EventTarget::AddEventListenerInternal(...)")
    assert not c.references_observer("")
