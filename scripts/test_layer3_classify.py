"""The marker rules on saved page dicts: every vendor's challenge and block, a clean pass, and the negatives."""
import json
import pathlib

import pytest

import layer3_classify as lc

HERE = pathlib.Path(__file__).resolve().parent
PAGES = json.loads((HERE / "testdata" / "layer3" / "pages.json").read_text())


@pytest.mark.parametrize("name", sorted(PAGES))
def test_fixture_pages_classify_as_labelled(name):
    case = PAGES[name]
    got = lc.classify(case["vendor"], case["page"])
    assert got["outcome"] == case["outcome"], got
    for marker in case.get("markers", []):
        assert marker in got["markers"], got


def test_every_vendor_has_a_challenge_and_a_pass_fixture():
    for vendor in lc.RULES:
        outcomes = {c["outcome"] for c in PAGES.values() if c["vendor"] == vendor}
        assert {"challenge", "pass"} <= outcomes, (vendor, outcomes)


def test_a_blank_page_is_unknown_not_pass():
    assert lc.classify("cloudflare", {"status": 200, "title": "", "text": "", "html": "<html></html>", "ok": False})["outcome"] == "unknown"


def test_block_outranks_challenge_and_a_foreign_vendors_marker_still_counts():
    page = {"title": "Attention Required! | Cloudflare", "html": 'id="challenge-form"', "ok": True}
    assert lc.classify("cloudflare", page)["outcome"] == "block"
    page = {"title": "x", "frames": ["https://geo.captcha-delivery.com/c"], "ok": False}
    got = lc.classify("cloudflare", page)  # the site is listed as Cloudflare but DataDome challenged
    assert got["outcome"] == "challenge" and "datadome:captcha-delivery-frame" in got["markers"]


def test_cookie_names_are_filtered_to_the_vendor_allowlist_and_values_never_enter():
    got = lc.classify("akamai", {"ok": True, "cookies": ["_abck", "sessionid", "bm_sz"]})
    assert got["cookies"] == ["_abck", "bm_sz"]


def test_combine_counts_either_stage_and_needs_both_for_a_pass():
    P, C, B, U = ({"outcome": o} for o in ("pass", "challenge", "block", "unknown"))
    assert lc.combine(P, P) == "pass" and lc.combine(P, C) == "challenge" and lc.combine(C, P) == "challenge"
    assert lc.combine(P, B) == "block" and lc.combine(C, B) == "block" and lc.combine(P, U) == "unknown"
    assert lc.challenged("challenge") and lc.challenged("block") and not lc.challenged("pass") and not lc.challenged("unknown")
