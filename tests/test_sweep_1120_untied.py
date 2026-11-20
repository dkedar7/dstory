"""Sweep 2026-11-20: a numeric claim with no `from` (hand-written, or drafted
before 0.14.3) still builds, but bundle and vet say it is not checked against
the data (#38 follow-up)."""
from __future__ import annotations

import io
import json

import pytest

from dstory.vet import UNTIED_CLAIMS_NOTE, check_data_fidelity


def _story(**claim):
    c = {"id": "c-up", "text": "Sales doubled", "value": 2.0, "unit": "ratio",
         "scene": "scene-a", **claim}
    return {"meta": {"title": "T"}, "claims": [c],
            "scenes": [{"id": "scene-a", "dataset": "a", "headline": "Sales doubled"}],
            "datasets": {"a": [{"year": 2023, "sales": 10}, {"year": 2024, "sales": 20}]}}


def _untied(r):
    return [n for n in r.notes if n.startswith(UNTIED_CLAIMS_NOTE)]


def test_a_claim_without_from_passes_with_a_note_naming_it():
    r = check_data_fidelity("", _story())
    assert r.passed
    (note,) = _untied(r)
    assert "'c-up'" in note and "dstory draft" in note


@pytest.mark.parametrize("story", [
    _story(**{"from": {"op": "ratio", "after": {"sum": "sales", "where": {"year": 2024}},
                       "before": {"sum": "sales", "where": {"year": 2023}}}}),
    _story(value=None),                                   # no number to check
    _story(scene="scene-missing"),                        # no scene data to check against
    {k: v for k, v in _story().items() if k != "datasets"},   # a claims-only check
])
def test_no_note_when_there_is_nothing_to_tie(story):
    assert not _untied(check_data_fidelity("", story))


def test_many_untied_claims_are_summarised():
    d = _story()
    d["claims"] = [dict(d["claims"][0], id=f"c{i}") for i in range(8)]
    (note,) = _untied(check_data_fidelity("", d))
    assert "'c4'" in note and "'c5'" not in note and "and 3 more" in note


def test_bundle_warns_about_an_untied_drafted_claim(tmp_path):
    pd = pytest.importorskip("pandas")
    from dstory.bundle import bundle
    from dstory.draft import draft

    d = draft(pd.read_csv(io.StringIO("team,score\nA,10\nB,25\nC,17\nD,40\n")), title="T")
    proj = d.to_project(tmp_path / "t")
    assert not any(w.startswith(UNTIED_CLAIMS_NOTE) for w in bundle(proj).warnings)
    p = proj / "data.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    for c in data["claims"]:
        c.pop("from", None)                               # as drafted before 0.14.3
    p.write_text(json.dumps(data), encoding="utf-8")
    warned = [w for w in bundle(proj).warnings if w.startswith(UNTIED_CLAIMS_NOTE)]
    assert warned and "'c-rank'" in warned[0]
