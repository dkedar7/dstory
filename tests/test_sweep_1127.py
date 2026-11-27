"""Sweep 2026-11-27.

#49: the claim drift check missed common ways of stating a change ("cut in
half", "by a third", "tenfold", "per cent", "twice as many"), and a claim's
own text was held to a narrower vocabulary than scene prose. One phrase
parser now reads both.
"""
from __future__ import annotations

import importlib

import pytest

from dstory import build
from dstory.bundle import ClaimDriftError

vet_mod = importlib.import_module("dstory.vet")
ROWS = [{"label": "Bus", "start": 100, "end": 80}, {"label": "Rail", "start": 90, "end": 99}]


def _data(headline, value, *, text="Sales changed", unit="pct", commentary=None):
    return {"meta": {"title": "Transit", "published": "2026-11-27",
                     "sources": [{"name": "Transit authority"}]},
            "claims": [{"id": "c1", "scene": "s1", "text": text, "value": value, "unit": unit}],
            "scenes": [{"id": "s1", "kind": "simple", "dataset": "rides", "headline": headline,
                        "commentary": commentary, "alt": "Slope chart of rides.",
                        "source_line": "Source: Transit authority"}],
            "datasets": {"rides": ROWS}}


def _issues(data):
    return vet_mod.check_data_fidelity("", data).issues


# (headline, a value it fits, a value it contradicts)
PHRASES = [
    ("Sales were cut in half", -50, -20),
    ("Sales fell by a quarter", -25, -60),
    ("Sales fell by a third", -33, -60),
    ("Sales fell by two-thirds", -67, -10),
    ("Sales fell by three-quarters", -75, -10),
    ("Sales rose by a third", 33, 80),
    ("Sales rose by about a third", 30, 10),
    ("Sales up 30 per cent", 30, 50),
    ("Sales grew 50 pct", 50, 10),
    ("Twice as many sales", 100, 200),
    ("Sales rose tenfold", 900, 100),
    ("Sales rose threefold", 200, 100),
]


@pytest.mark.parametrize("headline,ok,bad", PHRASES, ids=[p[0] for p in PHRASES])
def test_scene_prose_phrasings(headline, ok, bad):
    assert not _issues(_data(headline, ok)), headline
    issues = _issues(_data(headline, bad))
    assert any("Scene 's1' says" in i for i in issues), (headline, issues)


@pytest.mark.parametrize("text,ok,bad", [
    ("Sales fell by half", -50, -20),
    ("Sales were cut in half", -50, -20),
    ("Sales three times higher", 200, 100),
    ("Sales rose ten-fold", 900, 100),
    ("Sales rose tenfold", 900, 100),
    ("Sales rose by a third", 33, 80),
    ("Sales up 30 per cent", 30, 50),
    ("Twice as many riders", 100, 200),
])
def test_claim_text_is_held_to_the_same_phrases(text, ok, bad):
    assert not _issues(_data("A headline", ok, text=text)), text
    issues = _issues(_data("A headline", bad, text=text))
    assert any(i.startswith("Claim 'c1'") for i in issues), (text, issues)


def test_the_issue_repro_stops_the_bundle(tmp_path):
    data = _data("Bus ridership was cut in half", -20, text="Bus ridership fell 20%",
                 commentary="Bus ridership fell 20% between 2019 and 2024, while rail rose by "
                            "a third and bike trips rose tenfold.")
    with pytest.raises(ClaimDriftError) as e:
        build(data, tmp_path / "drift", vet=False)
    msg = str(e.value)
    for said in ("cut in half", "rose by a third", "tenfold"):
        assert said in msg, msg


def test_ratio_claims_and_unitless_claims_stay_quiet():
    """A ratio claim reads the same phrases; a legacy unit-less claim (maybe a
    share) is not held to them, as before."""
    assert not _issues(_data("Sales rose tenfold", 10.0, text="Sales rose tenfold", unit="ratio"))
    legacy = _data("A headline", 0.4, text="Sales rose by a third")
    legacy["claims"][0].pop("unit")
    assert not [i for i in _issues(legacy) if "a third" in i]


def test_words_that_only_look_like_changes_pass():
    for headline in ("A third of riders take the bus", "Fell to a third of its peak",
                     "Half the stations closed", "Twice a week"):
        assert not _issues(_data(headline, -20)), headline
