"""dstory.draft(): zero-config DataFrame -> vetted story (issue #11, milestone 1).

Needs pandas (the [prep] extra): run with `uv run --extra prep pytest`.
Browser tests also need the [vet] extra + Chromium, and network for the CDN
libs (or, for the vendored e2e, at build time only).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

import dstory  # noqa: E402
from dstory import Story, build, draft, vet  # noqa: E402
from dstory.vet import check_data_fidelity  # noqa: E402

YEARS = list(range(2015, 2025))
SERIES = {
    "Coal": [410, 400, 380, 350, 330, 300, 280, 250, 230, 210],
    "Gas": [300, 310, 330, 340, 360, 370, 380, 390, 395, 400],
    "Solar": [20, 28, 40, 55, 75, 100, 130, 165, 200, 240],
}


def _timeseries_long():
    return pd.DataFrame([{"year": y, "source": s, "twh": v}
                         for s, vals in SERIES.items() for y, v in zip(YEARS, vals)])


def _timeseries_wide():
    return pd.DataFrame({"year": YEARS, **{k.lower(): v for k, v in SERIES.items()}})


def _before_after():
    return pd.DataFrame({
        "department": ["Product", "Design", "Engineering", "Sales", "Support"],
        "2020": [120, 45, 300, 80, 60],
        "2024": [74, 35, 288, 90, 66],
    })


def _shares():
    return pd.DataFrame({"source": ["Gas", "Renewables", "Coal", "Nuclear"],
                         "share_pct": [38.2, 33.9, 17.6, 10.3]})


def _fallback():
    return pd.DataFrame({"team": ["North", "South", "East", "West"],
                         "score": [3.2, 7.5, 5.1, 6.0]})


FIXTURES = {
    "timeseries-long": _timeseries_long,
    "timeseries-wide": _timeseries_wide,
    "before-after": _before_after,
    "shares": _shares,
    "fallback": _fallback,
}

EXPECTED_RECIPES = {
    "timeseries-long": ["scene-trend", "scene-shift"],
    "timeseries-wide": ["scene-trend", "scene-shift"],
    "before-after": ["scene-shift"],
    "shares": ["scene-mix"],
    "fallback": ["scene-rank"],
}

_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def _prose(story: dict) -> list[str]:
    out = []
    for s in story["scenes"]:
        for k in ("headline", "commentary"):
            if s.get(k):
                out.append(s[k])
        for step in s.get("steps") or []:
            for k in ("headline", "commentary"):
                if step.get(k):
                    out.append(step[k])
    for k in ("deck", "subtitle", "description"):
        if story["meta"].get(k):
            out.append(story["meta"][k])
    return out


# ---------- static ----------

@pytest.mark.parametrize("name", FIXTURES)
def test_draft_story_validates_and_picks_expected_scenes(name):
    d = draft(FIXTURES[name](), title="A drafted story", source="Synthetic data")
    Story.model_validate(d.story)
    ids = [s["id"] for s in d.story["scenes"]]
    assert ids == EXPECTED_RECIPES[name]
    assert set(d.scenes) == set(ids)
    for s in d.story["scenes"]:
        assert s["alt"] and s["dataset"] in d.story["datasets"]
        assert d.story["datasets"][s["dataset"]], "drafted dataset is empty"


@pytest.mark.parametrize("name", FIXTURES)
def test_every_number_in_prose_is_a_claim(name):
    d = draft(FIXTURES[name](), title="A drafted story")
    claim_nums = {n for c in d.story["claims"] for n in _NUM.findall(c["text"])}
    for text in _prose(d.story):
        for n in _NUM.findall(text):
            assert n in claim_nums, f"{n!r} in {text!r} is not covered by a claim"
    # And each claim is actually used verbatim in the prose.
    prose = " ".join(_prose(d.story))
    for c in d.story["claims"]:
        assert c["text"].rstrip(".") in prose


@pytest.mark.parametrize("name", FIXTURES)
def test_claims_pass_static_fidelity(name):
    d = draft(FIXTURES[name](), title="A drafted story")
    assert check_data_fidelity("", d.story).passed


def test_mutating_a_claim_value_fails_static_vet(tmp_path):
    result = build(_timeseries_long(), tmp_path / "grid", vet=True, browser=False)
    assert result.passed is True
    data_path = result.project / "data.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    assert data["claims"], "draft produced no claims"
    data["claims"][0]["value"] = data["claims"][0]["value"] * 3 + 50
    data_path.write_text(json.dumps(data), encoding="utf-8")
    report = vet(result.html, data=data_path, browser=False)
    assert report.passed is False
    fidelity = next(d for d in report.dimensions if d.name == "Data fidelity")
    assert not fidelity.passed


def test_long_and_wide_time_series_agree():
    a = draft(_timeseries_long(), title="t")
    b = draft(_timeseries_wide(), title="t")
    # Same facts: Solar is the biggest mover in both shapes.
    assert "Solar" in a.story["scenes"][1]["headline"]
    assert "solar" in b.story["scenes"][1]["headline"].lower()
    assert a.story["claims"][0]["value"] == b.story["claims"][0]["value"]


def test_explain_mentions_rules_and_profile():
    text = draft(_timeseries_long(), title="t").explain()
    assert "year: temporal" in text and "source: categorical" in text
    assert "line-reveal over year x twh" in text
    assert "slope-chart of source, 2015 vs 2024" in text
    assert "(skipped) waffle" in text


def test_max_scenes_caps_output():
    d = draft(_timeseries_long(), title="t", max_scenes=1)
    assert [s["id"] for s in d.story["scenes"]] == ["scene-trend"]
    assert all(c["scene"] == "scene-trend" for c in d.story["claims"])


def test_meta_fields_and_theme_validation():
    d = draft(_shares(), title="Mix", theme="warm-print", mode="slides",
              audience="executive", source="Grid operator")
    m = d.story["meta"]
    assert (m["theme"], m["mode"], m["audience"]) == ("warm-print", "slides", "executive")
    assert m["sources"] == [{"name": "Grid operator"}]
    assert d.story["scenes"][0]["source_line"] == "Source: Grid operator."
    with pytest.raises(ValueError, match="Unknown theme"):
        draft(_shares(), title="Mix", theme="no-such-theme")


def test_rejects_non_dataframe_and_no_measures():
    with pytest.raises(TypeError):
        draft({"a": [1]}, title="t")
    with pytest.raises(ValueError, match="no numeric measure"):
        draft(pd.DataFrame({"a": ["x", "y"], "b": ["p", "q"]}), title="t")


def test_build_dict_input_unchanged(tmp_path):
    story = {"meta": {"title": "Plain"}, "scenes": [], "datasets": {}}
    result = build(story, tmp_path / "plain")
    assert json.loads((result.project / "data.json").read_text())["meta"]["title"] == "Plain"


def test_to_project_writes_a_normal_project(tmp_path):
    d = draft(_timeseries_long(), title="Grid", theme="warm-print")
    project = d.to_project(tmp_path / "grid")
    assert json.loads((project / "data.json").read_text(encoding="utf-8")) == d.story
    for sid in d.scenes:
        assert (project / "scenes" / f"{sid}.js").exists()
        assert f'scenes/{sid}.js' in (project / "index.html").read_text(encoding="utf-8")
    out = dstory.bundle(project, validate=True).out
    assert vet(out, data=project / "data.json", browser=False).passed


def test_import_dstory_does_not_import_pandas():
    code = "import sys, dstory; assert 'pandas' not in sys.modules, 'pandas imported'"
    subprocess.run([sys.executable, "-c", code], check=True)


def test_missing_pandas_raises_helpful_import_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "pandas", None)
    with pytest.raises(ImportError, match=r"dstory\[prep\]"):
        draft(object(), title="t")


# ---------- browser ----------

def _need_browser():
    pytest.importorskip("playwright.sync_api")


@pytest.mark.parametrize("name", FIXTURES)
def test_build_dataframe_passes_browser_vet(name, tmp_path):
    _need_browser()
    result = build(FIXTURES[name](), tmp_path / name, vet=True, browser=True)
    failures = [i for d in result.report.dimensions for i in d.issues]
    assert result.passed is True, failures


def test_slides_mode_draft_passes_vet(tmp_path):
    _need_browser()
    d = draft(_timeseries_long(), title="Grid in slides", mode="slides", theme="minimal-light")
    result = build(d.story, tmp_path / "slides", scenes=d.scenes, vet=True, browser=True)
    failures = [i for d in result.report.dimensions for i in d.issues]
    assert result.passed is True, failures


@pytest.mark.parametrize("name", FIXTURES)
def test_vendored_offline_bundle_paints_every_scene(name, tmp_path):
    _need_browser()
    from playwright.sync_api import sync_playwright

    d = draft(FIXTURES[name](), title="Offline", source="Synthetic")
    try:
        result = build(d.story, tmp_path / name, scenes=d.scenes, vendor=True)
    except Exception as e:  # vendoring downloads the libs at build time
        pytest.skip(f"vendoring needs network at build time: {e}")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:
            pytest.skip(f"Chromium unavailable: {e}")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors: list[str] = []
        blocked: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        def block(route):
            if not route.request.url.startswith("file:"):
                blocked.append(route.request.url)
                return route.abort()
            return route.continue_()

        page.route("**/*", block)
        page.goto(result.html.as_uri(), wait_until="load")
        for s in d.story["scenes"]:
            mount = f'[data-mount="{s["id"]}"]'
            page.locator(mount).scroll_into_view_if_needed()
            page.wait_for_function(
                "sel => { const m = document.querySelector(sel);"
                " return !!m && !!m.querySelector('svg') &&"
                " m.querySelector('svg').querySelectorAll('path, rect, circle, line, text').length > 0; }",
                arg=mount, timeout=5000)
        browser.close()
    assert errors == [], errors
    # Only fonts may be requested from the network; scripts are all inlined.
    assert not [u for u in blocked if not ("fonts.googleapis" in u or "fonts.gstatic" in u)], blocked
