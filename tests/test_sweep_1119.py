"""Sweep 2026-11-19: #38, a claim must not go stale when its data changes.
Drafted claims record where their number comes from (`from`), and bundle and
vet recompute it."""
from __future__ import annotations

import json

import pytest

from dstory.prep import (claim_from, compute_claim, compute_point_change, operand,
                         recompute_claim)
from dstory.schema import Story
from dstory.vet import check_data_fidelity

SHIFT = [{"source": "Coal", "start": 40, "end": 16}, {"source": "Gas", "start": 30, "end": 46},
         {"source": "Wind", "start": 30, "end": 38}]
MIX_CSV = ("year,source,share_pct\n2014,Coal,40\n2014,Gas,30\n2014,Wind,30\n"
           "2024,Coal,16\n2024,Gas,46\n2024,Wind,38\n")


def _coal(rank=1):
    return claim_from("pp", after=operand("end", source="Coal"),
                      before=operand("start", source="Coal"), rank={"by": "source", "is": rank})


def test_recompute_point_change_and_rank():
    assert recompute_claim(_coal(), SHIFT) == (-24.0, None)
    rows = [dict(r, end=38) if r["source"] == "Coal" else r for r in SHIFT]
    v, problem = recompute_claim(_coal(), rows)
    assert v == -2.0 and "Gas now does" in problem


@pytest.mark.parametrize("spec,want", [
    (claim_from("pct", after=operand("end", source="Gas"), before=operand("start", source="Gas")),
     pytest.approx(53.333, abs=1e-3)),
    (claim_from("ratio", after=operand("end", source="Gas"), before=operand("start", source="Gas")),
     pytest.approx(46 / 30)),
    (claim_from("share", part=operand("end", source="Gas"), whole=operand("end")), 0.46),
    (claim_from("value", of=operand("end")), 100.0),
])
def test_each_op(spec, want):
    assert recompute_claim(spec, SHIFT)[0] == want


def test_least_rank_and_missing_rows():
    assert recompute_claim(_coal(rank=-1), SHIFT)[1] is not None     # Coal moved most
    wind_least = claim_from("pp", after=operand("end", source="Wind"),
                            before=operand("start", source="Wind"),
                            rank={"by": "source", "is": -1})
    assert recompute_claim(wind_least, SHIFT) == (8.0, None)
    v, problem = recompute_claim(_coal(), [r for r in SHIFT if r["source"] != "Coal"])
    assert v is None and "gone" in problem


def test_bad_op_is_rejected():
    with pytest.raises(ValueError):
        claim_from("median", of=operand("x"))
    with pytest.raises(ValueError):
        claim_from("pct", after=operand("x"))


def _story(rows, value=-24.0, text="Coal share fell 24 points, the biggest shift of any source"):
    claim = {"id": "c-shift", "text": text, "value": value, "unit": "pp",
             "scene": "scene-shift", "from": _coal()}
    return {"meta": {"title": "Mix"}, "claims": [claim],
            "scenes": [{"id": "scene-shift", "kind": "simple", "dataset": "shift",
                        "headline": text}],
            "datasets": {"shift": rows}}


def test_fidelity_passes_while_the_data_agrees():
    r = check_data_fidelity("", _story(SHIFT))
    assert r.passed, r.issues


def test_fidelity_fails_a_stale_value_naming_old_and_new():
    rows = [dict(r, end=38) if r["source"] == "Coal" else r for r in SHIFT]
    r = check_data_fidelity("", _story(rows))
    assert not r.passed
    msg = next(i for i in r.issues if "c-shift" in i)
    assert "-24.0 points" in msg and "-2.0 points" in msg and "scene 'scene-shift'" in msg


def test_fidelity_fails_a_superlative_that_moved():
    # Coal still fell 24 points, but Gas now rose 30: Coal is no longer the biggest.
    rows = [dict(r, end=60) if r["source"] == "Gas" else r for r in SHIFT]
    r = check_data_fidelity("", _story(rows))
    assert any("ranks first" in i and "Gas now does" in i for i in r.issues), r.issues


def test_fidelity_fails_a_missing_dataset_or_bad_spec():
    d = _story(SHIFT)
    d["claims"][0]["from"] = dict(_coal(), dataset="nope")
    assert any("dataset 'nope'" in i for i in check_data_fidelity("", d).issues)
    d["claims"][0]["from"] = {"op": "pct", "after": "x", "before": "y"}
    assert any("malformed" in i for i in check_data_fidelity("", d).issues)


def test_claims_without_from_are_unchanged():
    d = _story([{"source": "Coal", "start": 1, "end": 1}])
    del d["claims"][0]["from"]
    assert check_data_fidelity("", d).passed


def test_schema_round_trips_from():
    st = Story.model_validate(_story(SHIFT))
    dumped = json.loads(st.model_dump_json(exclude_none=True, by_alias=True))
    assert dumped["claims"][0]["from"] == _coal()


def test_readme_snippet():
    claim = compute_claim(
        id="c-coal", scene="scene-shift", kind="pp",
        text_template="Coal's share {phrase}, the biggest shift of any source",
        value=compute_point_change(after=16, before=40),
        from_=claim_from("pp", after=operand("end", source="Coal"),
                         before=operand("start", source="Coal"),
                         rank={"by": "source", "is": 1}),
    )
    assert claim["text"] == "Coal's share fell 24 percentage points, the biggest shift of any source"
    assert recompute_claim(claim["from"], SHIFT) == (claim["value"], None)


def test_the_issue_repro_blocks_bundle_and_fails_vet(tmp_path, monkeypatch):
    pytest.importorskip("pandas")
    from dstory.bundle import ClaimDriftError, bundle
    from dstory.draft import draft
    from dstory.vet import vet
    import pandas as pd
    import io

    monkeypatch.chdir(tmp_path)
    d = draft(pd.read_csv(io.StringIO(MIX_CSV)), title="Mix")
    froms = {c["id"]: c.get("from") for c in d.story["claims"]}
    assert froms and all(froms.values()), froms          # every drafted claim has a `from`
    proj = d.to_project(tmp_path / "mix")
    bundle(proj)                                          # the fresh draft bundles
    p = proj / "data.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    for r in data["datasets"]["shift"]:
        if r["source"] == "Coal":
            r["end"] = 38
    for r in data["datasets"]["mix"]:
        r["share_pct"] = {"Coal": 38, "Gas": 24}.get(r["source"], r["share_pct"])
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ClaimDriftError) as e:
        bundle(proj)
    assert "c-shift" in str(e.value) and "c-mix-lead" in str(e.value)
    res = bundle(proj, check_claims=False)
    rep = vet(res.out, data=p, browser=False)
    fid = next(x for x in rep.dimensions if x.name == "Data fidelity")
    assert not fid.passed
    failures = rep.to_json()["failures"]
    assert {f["claim"] for f in failures if f["dimension"] == "data_fidelity"} >= {"c-shift", "c-mix-lead"}


@pytest.mark.parametrize("csv", [
    # A trend with a peak, an opener, panels and a ranking: every drafted
    # claim must recompute from its own scene's rows.
    "month,region,sales\n" + "\n".join(
        f"2024-{m:02d}-01,{r},{v}" for m in range(1, 7)
        for r, v in (("North", 100 + 10 * m), ("South", 80 + (5 * m if m < 4 else 30 - 3 * m)),
                     ("East", 60 + 2 * m))),
    "team,score\nA,10\nB,25\nC,17\nD,40\n",
    MIX_CSV,
])
def test_every_drafted_claim_recomputes(csv):
    pytest.importorskip("pandas")
    import io
    import pandas as pd
    from dstory.draft import draft

    st = draft(pd.read_csv(io.StringIO(csv)), title="T").story
    assert st["claims"]
    for c in st["claims"]:
        assert c.get("from"), c
    assert check_data_fidelity("", st).passed, check_data_fidelity("", st).issues
