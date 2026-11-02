"""Browser vetter: data-bearing scenes must paint (dogfood #3).

These call vet(browser=True), which starts its own Playwright, so they live
apart from test_e2e_browser.py's module-scoped sync browser fixture.
"""
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def chromium():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            p.chromium.launch().close()
        except Exception as e:
            pytest.skip(f"Chromium unavailable: {e}")


def _paint_story(tmp_path: Path, name: str, renderer_js: str, rows: list):
    from dstory import build
    return build(
        {"meta": {"title": "T", "published": "2026-11-02", "sources": [{"name": "x"}]},
         "scenes": [{"id": "s1", "kind": "simple", "dataset": "d", "headline": "H",
                     "alt": "A chart.", "source_line": "Source: x"}],
         "datasets": {"d": rows}},
        tmp_path / name, scenes={"s1": renderer_js}, vet=True, browser=True,
    )


def test_vet_fails_scene_whose_chart_paints_nothing(chromium, tmp_path: Path):
    res = _paint_story(tmp_path, "nullr", 'window.STORY.register("s1", m => null);',
                       [{"date": "2026-01-01", "value": 1}])
    renders = next(d for d in res.report.dimensions if d.name == "Renders correctly")
    assert not renders.passed
    assert any("did not paint" in i and "s1" in i for i in renders.issues)


def test_vet_fails_recipe_with_mismatched_columns(chromium, tmp_path: Path):
    from dstory.cookbook import recipe_js
    res = _paint_story(tmp_path, "blank", recipe_js("line-reveal", "s1"),
                       [{"month": "2026-01-01", "signups": 1000},
                        {"month": "2026-04-01", "signups": 3400}])
    renders = next(d for d in res.report.dimensions if d.name == "Renders correctly")
    assert not renders.passed
    assert any("empty dataset" in i for i in renders.issues)


def test_vet_passes_scene_that_paints(chromium, tmp_path: Path):
    res = _paint_story(
        tmp_path, "good",
        'window.STORY.register("s1", m => { m.innerHTML = '
        '"<svg viewBox=\\"0 0 10 10\\"><rect width=\\"10\\" height=\\"10\\"></rect></svg>"; return null; });',
        [{"date": "2026-01-01", "value": 1}],
    )
    renders = next(d for d in res.report.dimensions if d.name == "Renders correctly")
    assert renders.passed, renders.issues
