"""Sweep 2026-11-22.

#42: a percent change or ratio from a negative base flips the direction
("Net income tripled" under a loss that tripled). compute_pct_change and
compute_ratio refuse it, compute_claim refuses a change across zero, and the
vetter fails a `from` claim whose base is negative.

#43: to_records()/to_long() write a date column as "2024-01-01", and the date
recipes still draw "2024-01-01T00:00:00", or say why they drew nothing.
"""
from __future__ import annotations

import pytest

from dstory.prep import (claim_from, compute_claim, compute_pct_change, compute_ratio,
                         operand, recompute_claim)
from dstory.vet import check_data_fidelity

ROWS = [{"year": "2022", "net_income": -100}, {"year": "2023", "net_income": -180},
        {"year": "2024", "net_income": -300}]


@pytest.mark.parametrize("compute", [compute_pct_change, compute_ratio])
@pytest.mark.parametrize("after,before", [(-300, -100), (-80, -100), (100, -50)])
def test_a_negative_base_is_refused(compute, after, before):
    with pytest.raises(ValueError, match="negative base"):
        compute(after=after, before=before)


def test_positive_bases_are_unchanged():
    assert compute_pct_change(after=150, before=100) == 50.0
    assert compute_ratio(after=300, before=100) == 3.0
    assert compute_pct_change(after=-50, before=100) == -150.0   # the number itself is fine


def test_compute_claim_refuses_a_change_across_zero():
    """100 -> -50 is -150%: no percent phrase is honest and vet blocks one,
    so compute_claim must not build a claim that fails vetting."""
    with pytest.raises(ValueError, match="changed sign"):
        compute_claim(id="c", text_template="Profit {phrase}",
                      value=compute_pct_change(after=-50, before=100))
    with pytest.raises(ValueError, match="changed sign"):
        compute_claim(id="c", text_template="Profit {phrase}",
                      value=compute_ratio(after=-50, before=100))


def _story(value, after_year="2024"):
    claim = {"id": "c1", "scene": "s1", "unit": "pct", "value": value,
             "text": "Net income tripled since 2022",
             "from": claim_from("pct", after=operand("net_income", year=after_year),
                                before=operand("net_income", year="2022"))}
    return {"meta": {"title": "T"}, "claims": [claim],
            "scenes": [{"id": "s1", "dataset": "income", "headline": claim["text"]}],
            "datasets": {"income": ROWS}}


def test_the_issue_repro_no_longer_passes_vet():
    # The issue's claim: value 200.0 (the sign-flipped pct), text "tripled".
    r = check_data_fidelity("", _story(200.0))
    assert not r.passed
    assert any("base (before) is negative" in i and "-100 -> -300" in i for i in r.issues), r.issues


def test_recompute_claim_names_the_negative_base():
    spec = claim_from("ratio", after=operand("net_income", year="2024"),
                      before=operand("net_income", year="2022"))
    value, problem = recompute_claim(spec, ROWS)
    assert value == 3.0 and "negative" in problem and "ratio" in problem
    ok = claim_from("pp", after=operand("net_income", year="2024"),
                    before=operand("net_income", year="2022"))
    assert recompute_claim(ok, ROWS) == (-200.0, None)


def test_the_sign_change_message_covers_turning_positive():
    claim = {"id": "c", "text": "Net income decreased by 300.0%", "value": -300.0, "unit": "pct"}
    r = check_data_fidelity("", {"claims": [claim]})
    assert any("turned positive" in i for i in r.issues), r.issues


def test_to_records_writes_dates_as_dates():
    pd = pytest.importorskip("pandas")
    from dstory.prep import to_long, to_records
    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=3, freq="MS"),
                       "signups": [10, 12, 15]})
    assert to_records(df)[0] == {"date": "2024-01-01", "signups": 10}
    assert to_long(df, id_vars="date")[0]["date"] == "2024-01-01"
    df.loc[1, "date"] = pd.NaT
    assert to_records(df)[1]["date"] is None


def test_to_records_keeps_times_and_timezones():
    pd = pytest.importorskip("pandas")
    from dstory.prep import to_records
    t = pd.DataFrame({"t": pd.to_datetime(["2024-01-01 10:30", "2024-01-02 00:00"])})
    assert [r["t"] for r in to_records(t)] == ["2024-01-01T10:30:00", "2024-01-02T00:00:00"]
    z = pd.DataFrame({"t": pd.to_datetime(["2024-01-01"]).tz_localize("UTC")})
    assert to_records(z)[0]["t"] == "2024-01-01T00:00:00+00:00"


def test_a_recipe_that_parses_no_row_says_so(tmp_path):
    """#43: rows whose x does not parse get a message naming the format and a
    sample row, and vet still blocks the story."""
    pytest.importorskip("playwright.sync_api")
    from dstory import build
    from dstory.cookbook import recipe_js
    from dstory.vet import browser_available
    ok, why = browser_available()
    if not ok:
        pytest.skip(why)
    res = build({"meta": {"title": "T", "published": "2026-11-22", "sources": [{"name": "x"}]},
                 "scenes": [{"id": "s1", "kind": "simple", "dataset": "m", "headline": "H",
                             "alt": "A chart.", "source_line": "x"}],
                 "datasets": {"m": [{"date": "Jan 2024", "value": 1},
                                    {"date": "Feb 2024", "value": 2}]}},
                tmp_path / "p", scenes={"s1": recipe_js("line-reveal", "s1")},
                vet=True, browser=True)
    renders = next(d for d in res.report.dimensions if d.name == "Renders correctly")
    assert not renders.passed
    assert any("2 rows in dataset m" in i and "%Y-%m-%d" in i and "Jan 2024" in i
               for i in renders.issues), renders.issues
