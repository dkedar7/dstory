"""Sweep 2026-11-20: #39, compute_claim follows draft()'s newsroom wording.
Big multiples read "rose 12-fold", no change reads "held steady", and every
phrase it writes still passes the vetter."""
from __future__ import annotations

import pytest

from dstory.prep import compute_claim, compute_pct_change, compute_ratio, derive_claim_text
from dstory.vet import check_data_fidelity


@pytest.mark.parametrize("after,want", [
    (1200, "Sales rose 12-fold"),
    (1000, "Sales rose 10-fold"),
    (100, "Sales held steady, a 0% change"),
    (100.04, "Sales held steady, a 0% change"),
    (99.97, "Sales held steady, a 0% change"),
    (186, "Sales increased by 86.0%"),
    (37, "Sales decreased by 63.0%"),
    (200, "Sales doubled"),
])
@pytest.mark.parametrize("compute", [compute_ratio, compute_pct_change])
def test_the_issue_repro(compute, after, want):
    claim = compute_claim(id="c", text_template="Sales {phrase}",
                          value=compute(after=after, before=100))
    assert claim["text"] == want
    assert check_data_fidelity("", {"claims": [claim]}).passed, claim


def test_percent_style_keeps_the_old_wording():
    v = compute_ratio(after=1200, before=100)
    assert compute_claim(id="c", text_template="Sales {phrase}", value=v,
                         style="percent")["text"] == "Sales increased by 1100.0%"
    assert derive_claim_text(0.0, kind="pct", style="percent") == "increased by 0.0%"
    with pytest.raises(ValueError):
        derive_claim_text(2.0, kind="ratio", style="fold")


@pytest.mark.parametrize("ratio", [x / 100 for x in range(1, 3000, 7)])
def test_every_phrase_passes_vet(ratio):
    claim = compute_claim(id="c", text_template="Sales {phrase}", value=compute_ratio(
        after=ratio * 100, before=100))
    assert check_data_fidelity("", {"claims": [claim]}).passed, claim
