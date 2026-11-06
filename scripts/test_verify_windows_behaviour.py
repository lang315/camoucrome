import verify_windows_behaviour as v


def test_claim_rate_differs_from_the_boxs_real_rate():
    """A1/A4 prove the hook only if the claim is not what the device already reports (RED: 44100 claim on a 44100 box)."""
    assert v.audio_claim({"audio:sampleRate": 44100, "audio:bufferFrames": 441}, 44100) == (48000, 480)
    assert v.audio_claim({"audio:sampleRate": 48000, "audio:bufferFrames": 480}, 48000) == (44100, 441)


def test_claim_is_kept_when_it_already_differs():
    assert v.audio_claim({"audio:sampleRate": 44100, "audio:bufferFrames": 441}, 48000) == (44100, 441)


def test_claim_keeps_a_ten_millisecond_quantum():
    for real in (44100, 48000, 96000):
        rate, frames = v.audio_claim({"audio:sampleRate": 44100, "audio:bufferFrames": 441}, real)
        assert rate != real and frames == rate // 100


def test_interfaces_follow_the_claim():
    assert v.iface_ok("linux", {"share": "undefined", "bluetooth": "undefined"})
    assert v.iface_ok("windows", {"share": "function", "bluetooth": "object"})
    assert v.iface_ok("macos", {"share": "function", "bluetooth": "object"})


def test_interface_rows_fail_on_the_wrong_shape():
    """RED fixtures: the unamended Windows build under a Linux claim, and a build that dropped the enabling branch."""
    assert not v.iface_ok("linux", {"share": "function", "bluetooth": "object"})
    assert not v.iface_ok("linux", {"share": "undefined", "bluetooth": "object"})
    assert not v.iface_ok("windows", {"share": "undefined", "bluetooth": "undefined"})
    assert not v.iface_ok("macos", {"error": "launch failed"})


def test_row_count_includes_the_interface_rows():
    assert v.EXPECTED_ROWS == 17
