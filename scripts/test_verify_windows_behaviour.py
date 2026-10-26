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
