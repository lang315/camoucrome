"""Pure-check tests for verify_webauthn_coherence.coherence_problems -- no browser.

Guards the relation `passkeyPlatformAuthenticator == isUVPAA || hybridTransport` and the two-API agreement
`isUVPAA == caps.userVerifyingPlatformAuthenticator`. These make the RED mutant in the verify meaningful: a no-op
check would pass the ShardX-shaped report, which these assert it must not.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from verify_webauthn_coherence import coherence_problems  # noqa: E402


def rep(isUVPAA, uvpa, ppaa, hybrid):
    return {"isUVPAA": isUVPAA, "uvpa": uvpa, "ppaa": ppaa, "hybrid": hybrid}


def test_coherent_all_false():
    # a Linux desktop with no platform authenticator: everything false, ppaa = false||false
    assert coherence_problems(rep(False, False, False, False)) == []


def test_coherent_uvpa_true():
    # a Mac with Touch ID: uvpa true forces ppaa true
    assert coherence_problems(rep(True, True, True, True)) == []


def test_coherent_hybrid_only():
    # no platform authenticator but hybrid (phone) transport: ppaa follows hybrid
    assert coherence_problems(rep(False, False, True, True)) == []


def test_shardx_shape_is_flagged():
    # ShardBrowser's observed report: uvpa true, ppaa false -- ppaa must be uvpa||hybrid
    probs = coherence_problems(rep(True, True, False, False))
    assert any("ppaa" in p for p in probs), probs


def test_two_api_disagreement_is_flagged():
    # isUVPAA and caps.uvpa must agree
    probs = coherence_problems(rep(False, True, True, False))
    assert any("isUVPAA" in p for p in probs), probs


def test_error_report_is_a_failure():
    assert coherence_problems({"error": "boom"})


def test_missing_key_is_a_failure():
    assert coherence_problems({"isUVPAA": True, "uvpa": True})  # ppaa, hybrid absent
