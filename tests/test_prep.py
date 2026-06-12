"""prep helpers: claim derivation must produce phrases the vetter accepts."""
import re
import pytest

from dstory.prep import (
    compute_ratio,
    compute_pct_change,
    derive_claim_text,
    compute_claim,
    RATIO_PHRASES,
)
from dstory.vet import PHRASE_RULES


def test_compute_ratio_basic():
    assert compute_ratio(after=300, before=100) == 3.0
    assert compute_ratio(after=50, before=100) == 0.5


def test_compute_ratio_raises_on_zero():
    with pytest.raises(ValueError):
        compute_ratio(after=10, before=0)


def test_compute_pct_change():
    assert compute_pct_change(after=150, before=100) == 50.0
    assert compute_pct_change(after=50, before=100) == -50.0


def test_derive_claim_text_picks_word_for_clean_ratios():
    assert derive_claim_text(2.0) == "doubled"
    assert derive_claim_text(3.04) == "tripled"  # within tolerance
    assert derive_claim_text(0.5) == "halved"


def test_derive_claim_text_falls_back_to_pct_for_messy_values():
    text = derive_claim_text(127.4, kind="pct")
    assert "increased by 127.4%" in text


@pytest.mark.parametrize("word,ratio", list(RATIO_PHRASES.items()))
def test_derived_claim_passes_vetter_phrase_rules(word: str, ratio: float):
    """Critical: the prep helpers must produce text that the vetter will accept.
    If this test fails, prep and vet have drifted out of sync."""
    text = derive_claim_text(ratio)
    assert word in text.lower()
    # Now find the matching vetter phrase rule and confirm the value satisfies it.
    for pattern, predicate in PHRASE_RULES:
        if pattern.search(text):
            assert predicate(ratio), (
                f"Vetter rule for '{pattern.pattern}' rejects value {ratio}; "
                "prep would generate prose that vet would block."
            )
            break
    else:
        pytest.fail(f"No vetter rule matched derived text {text!r} for ratio {ratio}.")


def test_compute_claim_full_payload():
    ratio = compute_ratio(after=4_200_000, before=1_380_000)  # ~3.04
    claim = compute_claim(
        id="c1",
        text_template="Monthly volume {phrase} between Jan and Mar 2024",
        value=ratio,
        scene="scene-trend",
    )
    assert claim["id"] == "c1"
    assert claim["scene"] == "scene-trend"
    assert claim["value"] == pytest.approx(3.043478, rel=1e-3)
    assert "tripled" in claim["text"]


def test_compute_claim_no_scene_omitted():
    claim = compute_claim(id="c2", text_template="x {phrase}", value=2.0)
    assert "scene" not in claim
