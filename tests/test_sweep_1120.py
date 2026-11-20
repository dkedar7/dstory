"""Sweep 2026-11-20: #40, a bar chart past 12 rows must not call the 12th row
"lowest". The text ranks over every row, the chart keeps the true lowest and
says it is a subset, and the "lowest" claim is recomputed by bundle and vet."""
from __future__ import annotations

import io
import json

import pytest

from dstory.vet import check_data_fidelity

pd = pytest.importorskip("pandas")

STATES = ("state,population\nCA,39.0\nTX,30.5\nFL,22.6\nNY,19.6\nPA,13.0\nIL,12.5\n"
          "OH,11.8\nGA,11.0\nNC,10.8\nMI,10.0\nNJ,9.3\nVA,8.7\nWA,7.8\nAZ,7.4\nWY,0.58\n")


def _draft(csv=STATES):
    from dstory.draft import draft
    return draft(pd.read_csv(io.StringIO(csv)), title="States")


def _rank_scene(d):
    return next(s for s in d.story["scenes"] if s["id"] == "scene-rank")


def test_the_issue_repro_names_the_true_lowest_and_keeps_it_in_the_chart():
    d = _draft()
    s = _rank_scene(d)
    rows = d.story["datasets"][s["dataset"]]
    assert len(rows) == 12
    assert [r["state"] for r in rows][-1] == "WY"            # the true lowest is charted
    assert "VA" not in s["alt"] and "WY lowest at 0.58" in s["alt"]
    last = s["steps"][-1]
    assert last["headline"] == "WY ranks last"
    assert "WY has the lowest population, at 0.58." in last["commentary"]
    note = "The chart shows the 11 largest of 15 state values, plus WY; the text compares all 15."
    assert note in last["commentary"] and note in s["alt"]
    texts = {c["id"]: c["text"] for c in d.story["claims"]}
    assert texts["c-rank"] == "CA's population is 67-fold that of WY."
    assert check_data_fidelity("", d.story).passed


def test_twelve_rows_or_fewer_are_unchanged_and_carry_no_note():
    csv = "team,score\nA,10\nB,25\nC,17\nD,40\n"
    s = _rank_scene(_draft(csv))
    assert "The chart shows" not in s["alt"] + json.dumps(s["steps"])
    assert s["steps"][0]["commentary"] == "D is 300% higher than A."
    assert s["steps"][-1]["commentary"] == "A has the lowest score, at 10."


def test_a_data_edit_that_moves_the_bottom_fails_vet():
    d = _draft()
    rows = d.story["datasets"]["rank"]
    for r in rows:
        if r["state"] == "NJ":
            r["population"] = 0.1                            # NJ is now the lowest
    issues = check_data_fidelity("", d.story).issues
    assert any("c-rank-low" in i and "NJ now does" in i for i in issues), issues


def test_a_wrong_fold_in_the_text_fails_vet():
    d = _draft()
    c = next(c for c in d.story["claims"] if c["id"] == "c-rank")
    c["text"] = "CA's population is 12-fold that of WY."
    assert not check_data_fidelity("", d.story).passed
