"""Sweep 2026-11-24.

#45: `dstory vet story.html --data data.json` compares the data inlined in
story.html with data.json, so a stale bundle, or --data from another story,
no longer gets "safe to deliver".

#46: to_records() writes None for pd.NA from nullable dtypes, so build()
no longer crashes with PydanticSerializationError.
"""
from __future__ import annotations

import io
import json

import pytest
from click.testing import CliRunner

from dstory import build
from dstory.vet import embedded_data, vet

REV = [{"date": f"2024-{m:02d}-01", "value": v}
       for m, v in zip(range(1, 7), [100, 120, 150, 170, 210, 260])]


def _story(rows=REV, sid="scene-trend"):
    return {"meta": {"title": "Revenue climbed all year", "published": "2026-11-24",
                     "sources": [{"name": "Internal ledger"}]},
            "scenes": [{"id": sid, "kind": "simple", "dataset": "rev",
                        "source_line": "Internal ledger",
                        "headline": "Revenue climbed every month",
                        "alt": "Line chart of monthly revenue rising from 100 to 260."}],
            "datasets": {"rev": rows}}


def _fidelity(res, data_path=None):
    rep = vet(res.html, data=data_path or res.project / "data.json", browser=False)
    return next(d for d in rep.dimensions if d.name == "Data fidelity")


def _edit(res, fn):
    p = res.project / "data.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    fn(d)
    p.write_text(json.dumps(d, indent=2), encoding="utf-8")


def test_a_fresh_bundle_matches(tmp_path):
    res = build(_story(), tmp_path / "s", vet=False)
    assert embedded_data(res.html.read_text(encoding="utf-8"))["datasets"]["rev"] == REV
    dim = _fidelity(res)
    assert dim.passed, dim.issues


def test_the_issue_repro_a_stale_bundle_fails(tmp_path):
    res = build(_story(), tmp_path / "s", vet=False)

    def fix(d):
        d["datasets"]["rev"][0]["value"] = 900
        d["datasets"]["rev"][3]["value"] = 5
    _edit(res, fix)
    dim = _fidelity(res)
    assert not dim.passed
    (issue,) = [i for i in dim.issues if "Dataset 'rev'" in i]
    assert "row 1, value: 100 in story.html vs 900 in data.json" in issue
    assert "dstory bundle" in issue


def test_the_cli_says_not_safe(tmp_path):
    from dstory.cli import cli
    res = build(_story(), tmp_path / "s", vet=False)
    _edit(res, lambda d: d["datasets"]["rev"].pop())
    out = CliRunner().invoke(cli, ["vet", str(res.html), "--data", str(res.project / "data.json"),
                                   "--no-browser"])
    assert out.exit_code != 0, out.output
    flat = "".join(c for c in out.output if c.isalnum() or c in ".")   # the table wraps text
    assert "6rowsinstory.htmlvs5indata.json" in flat, out.output


def test_another_storys_data_fails(tmp_path):
    a = build(_story(), tmp_path / "a", vet=False)
    other = _story(rows=[{"date": "2024-01-01", "value": 1}], sid="scene-other")
    other["datasets"] = {"energy": other["datasets"].pop("rev")}
    other["scenes"][0]["dataset"] = "energy"
    b = build(other, tmp_path / "b", vet=False)
    issues = _fidelity(a, b.project / "data.json").issues
    assert any("only in story.html: 'rev'" in i and "only in data.json: 'energy'" in i
               for i in issues), issues
    assert any("Scenes in story.html (scene-trend)" in i for i in issues), issues


def test_edited_headline_and_claims_are_caught(tmp_path):
    res = build(_story(), tmp_path / "s", vet=False)
    _edit(res, lambda d: d["scenes"][0].update(headline="Revenue fell"))
    assert any("Scene text or settings" in i and "'scene-trend'" in i
               for i in _fidelity(res).issues)


def test_html_without_inlined_data_gets_a_note(tmp_path):
    p = tmp_path / "x.html"
    p.write_text("<!doctype html><html lang='en'><head><title>X</title></head><body></body></html>",
                 encoding="utf-8")
    d = tmp_path / "data.json"
    d.write_text(json.dumps(_story()), encoding="utf-8")
    dim = next(x for x in vet(p, data=d, browser=False).dimensions if x.name == "Data fidelity")
    assert any("No inlined story data" in n for n in dim.notes)


def test_to_records_writes_none_for_pd_na(tmp_path):
    pd = pytest.importorskip("pandas")
    from dstory.prep import to_records
    df = pd.read_csv(io.StringIO("label,start,end\nCoal,40,16\nGas,28,\nSolar,2,24\n"),
                     dtype_backend="numpy_nullable")
    recs = to_records(df)
    assert recs[1] == {"label": "Gas", "start": 28, "end": None}
    res = build({"meta": {"title": "Mix"},
                 "scenes": [{"id": "s", "kind": "simple", "dataset": "m",
                             "headline": "Solar rose", "alt": "Slope chart."}],
                 "datasets": {"m": recs}}, tmp_path / "na", vet=False)
    assert json.loads((res.project / "data.json").read_text())["datasets"]["m"][1]["end"] is None


def test_to_records_handles_every_nullable_dtype():
    pd = pytest.importorskip("pandas")
    np = pytest.importorskip("numpy")
    from dstory.prep import to_records
    df = pd.DataFrame({"s": pd.array(["a", None], dtype="string"),
                       "f": pd.array([1.5, None], dtype="Float64"),
                       "i": pd.array([1, None], dtype="Int64"),
                       "b": pd.array([True, None], dtype="boolean"),
                       "n": np.array([np.float32("nan"), np.float32(2)])})
    assert to_records(df) == [{"s": "a", "f": 1.5, "i": 1, "b": True, "n": None},
                              {"s": None, "f": None, "i": None, "b": None, "n": 2.0}]
    conv = pd.DataFrame({"x": [1.0, None], "y": ["a", None]}).convert_dtypes()
    assert to_records(conv) == [{"x": 1, "y": "a"}, {"x": None, "y": None}]
    json.dumps(to_records(df), allow_nan=False)
