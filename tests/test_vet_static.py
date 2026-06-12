"""Vet static checks (no browser): claims, editorial slop, PII."""
import json
from pathlib import Path

from dstory import init, bundle, vet
from dstory.vet import check_data_fidelity, check_editorial, check_static_a11y


def _scaffold_with_data(tmp_path: Path, scenes: list, claims: list, datasets: dict | None = None) -> Path:
    dest = init(tmp_path / "demo", brand="editorial-noir")
    data = json.loads((dest / "data.json").read_text())
    data["scenes"]   = scenes
    data["claims"]   = claims
    data["meta"]["sources"] = [{"name": "Source X", "url": "https://example.com"}]
    data["meta"]["published"] = "2026-05-02"
    if datasets:
        data["datasets"] = datasets
    (dest / "data.json").write_text(json.dumps(data))
    return dest


def test_data_fidelity_passes_when_claim_matches(tmp_path: Path):
    dest = _scaffold_with_data(
        tmp_path,
        scenes=[{"id": "s1", "kind": "simple", "headline": "h", "commentary": "x doubled today"}],
        claims=[{"id": "c1", "text": "x doubled today", "value": 2.0}],
    )
    result = bundle(dest)
    html = result.out.read_text()
    data = json.loads((dest / "data.json").read_text())
    dim = check_data_fidelity(html, data)
    assert dim.passed


def test_data_fidelity_blocks_mismatched_ratio(tmp_path: Path):
    dest = _scaffold_with_data(
        tmp_path,
        scenes=[{"id": "s1", "kind": "simple", "headline": "h", "commentary": "x tripled overnight"}],
        claims=[{"id": "c1", "text": "x tripled overnight", "value": 2.4}],   # NOT triple
    )
    result = bundle(dest)
    html = result.out.read_text()
    data = json.loads((dest / "data.json").read_text())
    dim = check_data_fidelity(html, data)
    assert not dim.passed
    assert any("tripled" in i for i in dim.issues)


def test_data_fidelity_blocks_off_pct(tmp_path: Path):
    dest = _scaffold_with_data(
        tmp_path,
        scenes=[{"id": "s1", "kind": "simple", "headline": "h",
                 "commentary": "labor share fell to 47%"}],
        claims=[{"id": "c1", "text": "labor share fell to 47%", "value": 50.0}],
    )
    result = bundle(dest)
    html = result.out.read_text()
    data = json.loads((dest / "data.json").read_text())
    dim = check_data_fidelity(html, data)
    assert not dim.passed


def test_editorial_blocks_slop(tmp_path: Path):
    dest = _scaffold_with_data(
        tmp_path,
        scenes=[{"id": "s1", "kind": "simple", "headline": "h",
                 "commentary": "TODO: write this up properly"}],
        claims=[],
    )
    result = bundle(dest)
    html = result.out.read_text()
    data = json.loads((dest / "data.json").read_text())
    dim = check_editorial(html, data)
    assert not dim.passed
    assert any("TODO" in i for i in dim.issues)


def test_a11y_flags_pii(tmp_path: Path):
    dest = _scaffold_with_data(
        tmp_path,
        scenes=[],
        claims=[],
        datasets={"users": [{"email": "leaked@example.com", "x": 1}]},
    )
    data = json.loads((dest / "data.json").read_text())
    dim = check_static_a11y("", data)
    assert not dim.passed
    assert any("email" in i for i in dim.issues)


def test_full_vet_no_browser_returns_report(tmp_path: Path):
    dest = _scaffold_with_data(
        tmp_path,
        scenes=[{"id": "s1", "kind": "simple", "headline": "Real insight", "commentary": "It went up."}],
        claims=[],
    )
    result = bundle(dest)
    report = vet(result.out, data=dest / "data.json", browser=False)
    assert report.passed
    names = [d.name for d in report.dimensions]
    assert "Renders correctly" in names
    assert "Data fidelity" in names
    assert "Editorial integrity" in names
