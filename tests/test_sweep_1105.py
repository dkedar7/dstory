"""Regression tests for dogfood issues #7, #8, #9, #10, #12, #13, #16."""
import json
import os
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from dstory import build
from dstory.bundle import ClaimDriftError, bundle
from dstory.prep import fmt_compact
from dstory.schema import Story, vizzu_channel_series
from dstory.vet import check_vizzu_overdraw

META = {"title": "T", "published": "2026-11-05", "sources": [{"name": "x"}]}


# ---------- #10: fmt_compact promotes the suffix after rounding ----------

@pytest.mark.parametrize("value,expected", [
    (999_499, "999.5K"), (999_999, "1M"), (999_999_999, "1B"), (1_000_000, "1M"),
    (999.96, "1K"), (1_234_567, "1.2M"), (-999_999, "-1M"), (0, "0"), (12.5, "12.5"),
])
def test_fmt_compact(value, expected):
    assert fmt_compact(value) == expected


def test_fmt_compact_zero_digits_keeps_trailing_zeros():
    assert fmt_compact(10, digits=0) == "10"
    assert fmt_compact(20_000, digits=0) == "20K"


# ---------- #13: unknown theme is an error, not a silent fallback ----------

def test_build_rejects_unknown_theme(tmp_path: Path):
    with pytest.raises(ValueError, match=r"scientific-brigth.*Available:.*scientific-bright"):
        build({"meta": {"title": "t", "theme": "scientific-brigth"},
               "scenes": [{"id": "a", "headline": "h"}]}, tmp_path / "r2")


def test_build_known_theme_applies(tmp_path: Path):
    r = build({"meta": {"title": "t", "theme": "warm-print"},
               "scenes": [{"id": "a", "headline": "h"}]}, tmp_path / "ok")
    assert 'data-theme="warm-print"' in r.html.read_text(encoding="utf-8")


# ---------- #9: drifted claims block the build ----------

DRIFT = {"meta": {"title": "Drift"},
         "claims": [{"id": "c1", "text": "Signups tripled in Q1", "value": 1.2}],
         "scenes": [{"id": "s", "kind": "simple", "headline": "Signups tripled in Q1"}]}


def test_build_refuses_drifted_claim(tmp_path: Path):
    with pytest.raises(ClaimDriftError, match="tripled"):
        build(DRIFT, tmp_path / "drift")
    assert not (tmp_path / "drift" / "dist" / "story.html").exists()


def test_build_drift_escape_hatch(tmp_path: Path):
    r = build(DRIFT, tmp_path / "drift", check_claims=False)
    assert r.html.exists()


def test_cli_bundle_refuses_drifted_claim(tmp_path: Path):
    build(DRIFT, tmp_path / "drift", check_claims=False)
    (tmp_path / "drift" / "dist" / "story.html").unlink()
    cmd = [sys.executable, "-m", "dstory.cli", "bundle", str(tmp_path / "drift")]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(cmd, capture_output=True, env=env, timeout=120)
    assert proc.returncode == 1
    assert b"tripled" in proc.stdout
    assert not (tmp_path / "drift" / "dist" / "story.html").exists()
    proc = subprocess.run(cmd + ["--no-check-claims"], capture_output=True, env=env, timeout=120)
    assert proc.returncode == 0, proc.stdout


# ---------- #12: vet reports skipped checks; vizzu channel typos fail early ----------

def _vizzu_scene(channels, series=("month", "value")):
    return {"id": "v", "kind": "vizzu", "dataset": "m", "alt": "a",
            "series": [{"name": series[0], "type": "dimension"},
                       {"name": series[1], "type": "measure"}],
            "frames": [{"headline": "h", "config": {"channels": channels, "geometry": "rectangle"}}]}


def test_vizzu_channel_must_name_declared_series(tmp_path: Path):
    story = {"meta": META, "datasets": {"m": [{"month": "Jan", "value": 1}]},
             "scenes": [_vizzu_scene({"x": "Month", "y": "value"})]}
    with pytest.raises(ValueError, match=r"'Month'.*not in the scene's series"):
        build(story, tmp_path / "typo")


def test_vizzu_channel_forms():
    assert vizzu_channel_series("a") == ["a"]
    assert vizzu_channel_series(["a", "b"]) == ["a", "b"]
    assert vizzu_channel_series({"set": ["a"], "range": {"max": "110%"}}) == ["a"]
    assert vizzu_channel_series({"set": None}) == []
    assert vizzu_channel_series("count()") == []
    assert vizzu_channel_series(None) == []
    ok = Story.model_validate({"meta": META, "datasets": {"m": [{"month": "Jan", "value": 1}]},
                               "scenes": [_vizzu_scene({"x": {"set": ["month"]}, "y": ["value"]})]})
    assert ok.validate_dataset_refs() == []


def test_static_only_vet_is_marked_skipped(tmp_path: Path):
    r = build({"meta": META, "scenes": [{"id": "a", "headline": "h"}]},
              tmp_path / "s", vet=True, browser=False)
    assert r.report.skipped == ["Renders correctly", "Visual quality"]
    assert not r.report.complete
    assert r.report.to_json()["complete"] is False


def test_skipped_vet_warns_when_browser_was_not_disabled(tmp_path: Path, monkeypatch):
    import importlib; vetmod = importlib.import_module("dstory.vet")
    monkeypatch.setattr(vetmod, "_BROWSER_STATUS", (False, "test: no browser"))
    with pytest.warns(UserWarning, match="Vetting was partial"):
        r = build({"meta": META, "scenes": [{"id": "a", "headline": "h"}]},
                  tmp_path / "w", vet=True)
    assert r.report.skipped
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        build({"meta": META, "scenes": [{"id": "a", "headline": "h"}]},
              tmp_path / "w2", vet=True, browser=False)


def test_vet_runs_inside_a_running_event_loop(tmp_path: Path):
    """Jupyter cells run inside an asyncio loop; vet must still reach the browser."""
    import asyncio
    pytest.importorskip("playwright.sync_api")
    import importlib; vetmod = importlib.import_module("dstory.vet")
    vetmod._BROWSER_STATUS = None
    if not vetmod.browser_available()[0]:
        pytest.skip("no Chromium")
    vetmod._BROWSER_STATUS = None

    async def cell():
        return build({"meta": META, "scenes": [{"id": "a", "headline": "h"}]},
                     tmp_path / "nb", vet=True)
    r = asyncio.run(cell())
    assert r.report.complete, r.report.skipped


# ---------- #7: vizzu colour without stacking hides data ----------

QUICKSTART_ROWS = [{"month": m, "variable": v, "value": n}
                   for m, s, c in [("Jan", 1000, 200), ("Feb", 1500, 240)]
                   for v, n in [("Signups", s), ("Churn", c)]]
QS_SERIES = [{"name": "month", "type": "dimension"}, {"name": "variable", "type": "dimension"},
             {"name": "value", "type": "measure"}]


def _qs(channels, geometry="rectangle"):
    return {"datasets": {"m": QUICKSTART_ROWS},
            "scenes": [{"id": "g", "kind": "vizzu", "dataset": "m", "series": QS_SERIES,
                        "frames": [{"headline": "h", "config": {"channels": channels, "geometry": geometry}}]}]}


def test_overdraw_flagged_for_unstacked_colour():
    issues = check_vizzu_overdraw(_qs({"x": "month", "y": "value", "color": "variable"}))
    assert len(issues) == 1 and "overdraw" in issues[0]


@pytest.mark.parametrize("channels,geometry", [
    ({"x": ["month", "variable"], "y": "value", "color": "variable"}, "rectangle"),  # grouped
    ({"x": "month", "y": ["variable", "value"], "color": "variable"}, "rectangle"),  # stacked
    ({"x": "month", "y": "value", "color": "variable"}, "line"),                    # lines don't overdraw
])
def test_overdraw_not_flagged_when_stacked_grouped_or_lines(channels, geometry):
    assert check_vizzu_overdraw(_qs(channels, geometry)) == []


def test_colour_by_category_is_not_overdraw():
    data = {"datasets": {"m": [{"region": "N", "group": "A", "v": 1}, {"region": "S", "group": "B", "v": 2}]},
            "scenes": [{"id": "g", "kind": "vizzu", "dataset": "m",
                        "series": [{"name": "region"}, {"name": "group"}, {"name": "v", "type": "measure"}],
                        "frames": [{"headline": "h", "config": {"channels": {"x": "region", "y": "v", "color": "group"}}}]}]}
    assert check_vizzu_overdraw(data) == []


def test_readme_quickstart_frame_is_not_overdrawn():
    import re
    readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    m = re.search(r'"config": \{"channels": (\{[^}]*\}),\s*"geometry": "rectangle"', readme)
    assert m, "quickstart rectangle frame not found"
    channels = json.loads(m.group(1))
    assert check_vizzu_overdraw(_qs(channels)) == []
