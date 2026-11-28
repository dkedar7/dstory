"""Sweep 2026-11-28.

#50: "by a factor of N" and "multiplied by N" were never read, and "N-fold",
"Nx" and "N times" accepted any ratio that rounds to N, so "rose twofold" at
1.6 passed while "doubled" was blocked.

#51: a hedge before a ratio verb was ignored, so the true "nearly doubled"
at 1.9 was blocked.

Every ratio wording now goes through one table (vet.ratio_window): 2 to 5
share the windows of "doubled".."quintupled", and hedges work as they do
for percents.
"""
from __future__ import annotations

import importlib

import pytest

from dstory import build
from dstory.bundle import ClaimDriftError
from dstory.prep import compute_claim, compute_ratio

vet_mod = importlib.import_module("dstory.vet")
ROWS = [{"label": "A", "start": 100, "end": 190}, {"label": "B", "start": 80, "end": 90}]


def _data(headline, ratio, text="Sales changed"):
    return {"meta": {"title": "Sales story", "published": "2026-11-28",
                     "sources": [{"name": "Ledger"}]},
            "claims": [{"id": "c1", "scene": "s1", "text": text, "value": ratio, "unit": "ratio"}],
            "scenes": [{"id": "s1", "kind": "simple", "dataset": "d", "headline": headline,
                        "alt": "Slope chart of sales.", "source_line": "Ledger"}],
            "datasets": {"d": ROWS}}


def _fidelity(data):
    return vet_mod.check_data_fidelity("", data)


BLOCKED = [   # (ratio, headline): false, so the build must stop
    (1.9, "Sales rose by a factor of two"),
    (1.9, "Sales rose by a factor of ten"),
    (1.9, "Sales grew by a factor of 5"),
    (1.9, "Sales were multiplied by five"),
    (4.8, "Sales were up by a factor of 20"),
    (4.8, "Sales grew by a factor of 2"),
    (1.6, "Sales rose twofold"),
    (1.6, "Sales rose 2x"),
    (1.6, "Sales rose two times"),
    (1.6, "Sales doubled"),
    (4.6, "Sales rose fivefold"),
    (4.6, "Sales rose 5x"),
    (4.6, "Sales quintupled"),
    (1.9, "Sales rose tenfold"),
    (2.3, "Sales nearly doubled"),          # a hedge on the wrong side
    (2.5, "Sales more than tripled"),
    (0.8, "Sales fell by a factor of two"),
]
PASSES = [    # true wording
    (1.9, "Sales nearly doubled"),
    (1.9, "Sales almost doubled"),
    (4.8, "Sales more than quadrupled"),
    (4.8, "Sales nearly quintupled"),
    (2.0, "Sales rose by a factor of two"),
    (5.0, "Sales were multiplied by five"),
    (2.0, "Sales rose twofold"),
    (3.0, "Sales rose 3x"),
    (12.2, "Sales rose 12-fold"),
    (10.0, "Sales rose by a factor of ten"),
    (1.9, "Sales roughly doubled"),
    (0.53, "Sales nearly halved"),
    (0.5, "Sales fell by a factor of two"),
]


@pytest.mark.parametrize("ratio,headline", BLOCKED, ids=[f"{r}-{h}" for r, h in BLOCKED])
def test_false_ratio_wording_is_blocked(ratio, headline):
    issues = _fidelity(_data(headline, ratio)).issues
    assert any("Scene 's1' says" in i for i in issues), (headline, issues)


@pytest.mark.parametrize("ratio,headline", PASSES, ids=[f"{r}-{h}" for r, h in PASSES])
def test_true_ratio_wording_passes(ratio, headline):
    assert not _fidelity(_data(headline, ratio)).issues, headline


def test_the_error_quotes_the_hedge():
    (issue,) = _fidelity(_data("Sales nearly doubled", 2.4)).issues
    assert '"nearly doubled"' in issue


def test_true_but_weak_wording_is_a_note_not_a_failure():
    dim = _fidelity(_data("Solar's share has more than doubled", 4.8))
    assert dim.passed, dim.issues
    assert any('"more than doubled"' in n and "undersells" in n for n in dim.notes), dim.notes


@pytest.mark.parametrize("text,ratio,ok", [
    ("Sales nearly doubled", 1.9, True),
    ("Sales rose by a factor of ten", 1.9, False),
    ("Sales rose twofold", 1.6, False),
    ("Sales were multiplied by five", 5.0, True),
])
def test_claim_text_reads_the_same_table(text, ratio, ok):
    issues = [i for i in _fidelity(_data("A headline", ratio, text=text)).issues
              if i.startswith("Claim 'c1'")]
    assert (not issues) == ok, (text, issues)


def test_the_issue_repros_through_build(tmp_path):
    def story(headline):
        c = compute_claim(id="c1", scene="s1", text_template="Sales {phrase} between 2014 and 2024",
                          value=compute_ratio(after=190, before=100))
        d = _data(headline, c["value"])
        d["claims"] = [c]
        d["scenes"][0]["commentary"] = c["text"] + "."
        return d
    with pytest.raises(ClaimDriftError, match="by a factor of ten"):
        build(story("Sales rose by a factor of ten"), tmp_path / "a", vet=False)
    build(story("Sales nearly doubled"), tmp_path / "b", vet=False)       # #51: no error


@pytest.mark.parametrize("ratio", [0.5, 1.2, 1.9, 2.0, 2.05, 3.1, 4.0, 5.0, 5.6, 7.4, 12.2, 40.0])
def test_compute_claim_text_always_passes_its_own_check(ratio):
    """prep and the vetter share one table, so a generated phrase never fails."""
    c = compute_claim(id="c1", scene="s1", text_template="Sales {phrase}",
                      value=compute_ratio(after=ratio * 100, before=100))
    d = _data(c["text"], c["value"], text=c["text"])
    d["claims"] = [c]
    assert not _fidelity(d).issues, c["text"]


def test_ratio_window_matches_the_verb_windows():
    from dstory.prep import RATIO_WINDOWS
    assert vet_mod.ratio_window(2) == RATIO_WINDOWS["doubled"]
    assert vet_mod.ratio_window(5) == RATIO_WINDOWS["quintupled"]
    assert vet_mod.ratio_window(12) == (11.5, 12.5)
