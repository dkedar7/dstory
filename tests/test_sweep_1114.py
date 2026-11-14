"""Sweep 2026-11-14: #29, scene prose that contradicts its claim in percent,
"Nx" or direction must fail data fidelity and stop the bundle."""
from __future__ import annotations

import json

import pytest

from dstory.prep import compute_claim, compute_pct_change, compute_point_change, compute_ratio
from dstory.vet import check_data_fidelity

RATIO = compute_claim(id="c1", text_template="Signups {phrase} in Q1",
                      value=compute_ratio(after=2900, before=1000), scene="a")      # 2.9
PCT = compute_claim(id="c2", text_template="Churn {phrase} in Q1",
                    value=compute_pct_change(after=260, before=200), scene="b")     # +30%
PP = compute_claim(id="c3", text_template="Share {phrase}",
                   value=compute_point_change(after=14, before=12), scene="c")      # +2 points


def _story(a: str = "Signups tripled in Q1", b: str = "Churn rose 30% in Q1",
           c: str = "Share rose 2 points") -> dict:
    return {"meta": {"title": "Q1"}, "claims": [RATIO, PCT, PP],
            "scenes": [{"id": "a", "kind": "simple", "headline": a},
                       {"id": "b", "kind": "simple", "headline": b},
                       {"id": "c", "kind": "simple", "headline": c}]}


@pytest.mark.parametrize("a,b,c", [
    ("Signups grew 5x in Q1", None, None),
    ("Signups rose 400% in Q1", None, None),
    ("Signups rose five times over", None, None),
    ("Signups fell by half", None, None),
    (None, "Churn fell 30% in Q1", None),        # the direction is reversed
    (None, "Churn was down 30%", None),
    (None, "A 30% drop in churn", None),
    (None, "Churn rose 45% in Q1", None),
    (None, None, "Share fell 2 points"),
    (None, None, "Share up 5 points"),
])
def test_drifted_scene_prose_fails(a, b, c):
    kw = {k: v for k, v in (("a", a), ("b", b), ("c", c)) if v}
    r = check_data_fidelity("", _story(**kw))
    assert not r.passed
    assert any("drifted" in i for i in r.issues)


@pytest.mark.parametrize("a,b,c", [
    ("Signups tripled in Q1", "Churn rose 30% in Q1", "Share rose 2 points"),
    ("Signups grew 2.9x in Q1", "Churn increased by 30.0% in Q1", "a 2-point gain"),
    ("Signups rose 190%, nearly 3x", "Churn rose about 31% to 13% of users", "Share up 2 points"),
    ("Signups rose almost three times over", "Uptime held at 99.9%; churn up 30%",
     "Share rose 2 percentage points"),
    ("Signups tripled; 3 times more than 2023", "A 30% increase in churn", "Share rose 2 points"),
    # A share or a level is not a change: "made up 47%" and a bare "12%" are left alone.
    ("Signups tripled; web made up 47% of them", "Churn rose 30% to 12%", "Share rose 2 points"),
])
def test_faithful_scene_prose_passes(a, b, c):
    r = check_data_fidelity("", _story(a, b, c))
    assert r.passed, r.issues


def test_scene_without_claims_is_not_checked():
    d = _story()
    d["scenes"].append({"id": "d", "kind": "simple", "headline": "Costs fell 12%"})
    assert check_data_fidelity("", d).passed


def test_legacy_unitless_claim_is_not_read_as_a_change():
    d = {"meta": {"title": "t"},
         "claims": [{"id": "s", "text": "a majority", "value": 0.6, "scene": "a"}],
         "scenes": [{"id": "a", "kind": "simple", "headline": "A majority, up 5% on 2023, 2x the rest"}]}
    assert check_data_fidelity("", d).passed


def test_bundle_stops_on_reversed_direction(tmp_path, monkeypatch):
    """The issue's repro: `dstory bundle` must raise, not write the page."""
    from dstory.bundle import ClaimDriftError, bundle
    from dstory.scaffold import init

    monkeypatch.chdir(tmp_path)
    init("q1", brand="minimal-light")
    p = tmp_path / "q1" / "data.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["meta"].update(title="Q1 signups", published="2026-11-14", sources=[{"name": "CRM export"}])
    d["claims"] = [RATIO, PCT]
    d["datasets"] = {"m": [{"date": "2024-01-01", "value": 1000}, {"date": "2024-03-01", "value": 2900}],
                     "c": [{"date": "2024-01-01", "value": 200}, {"date": "2024-03-01", "value": 260}]}
    d["scenes"] = [{"id": "a", "kind": "simple", "dataset": "m", "headline": "Signups tripled in Q1",
                    "alt": "Signups grew from 1,000 to 2,900."},
                   {"id": "b", "kind": "simple", "dataset": "c", "headline": "Churn fell 30% in Q1",
                    "alt": "Churn grew from 200 to 260."}]
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ClaimDriftError, match="fell 30%"):
        bundle("q1")
    assert not (tmp_path / "q1" / "dist" / "story.html").exists()

    d["scenes"][1]["headline"] = "Churn rose 30% in Q1"
    p.write_text(json.dumps(d), encoding="utf-8")
    assert bundle("q1").out.exists()
