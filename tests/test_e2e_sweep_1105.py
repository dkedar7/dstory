"""Browser e2e for dogfood #8 (slides charts fit their card) and #16 (a Vizzu
scene no longer holds back the charts after it)."""
import time
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from dstory import build, list_recipes, recipe_demo, recipe_js  # noqa: E402
from dstory.vet import OVERFLOW_AUDIT_JS  # noqa: E402

META = {"title": "T", "published": "2026-11-05", "sources": [{"name": "demo"}]}


@pytest.fixture(scope="module")
def pw():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:
            pytest.skip(f"Chromium unavailable: {e}")
        yield b
        b.close()


@pytest.fixture(scope="module")
def all_recipes_deck(tmp_path_factory):
    scenes, ds, js = [], {}, {}
    for r in list_recipes():
        d = recipe_demo(r.name)
        sid = "s-" + r.name
        scenes.append({"id": sid, "dataset": sid, **d["scene"]})
        ds[sid] = d["dataset"]
        js[sid] = recipe_js(r.name, sid)
    return build({"meta": dict(META, title="All recipes", mode="slides"), "scenes": scenes, "datasets": ds},
                 tmp_path_factory.mktemp("deck") / "allsl", scenes=js)


@pytest.mark.parametrize("w,h", [(1280, 720), (1366, 768), (1440, 900)])
def test_slides_charts_fit_their_card(pw, all_recipes_deck, w, h):
    page = pw.new_page(viewport={"width": w, "height": h})
    page.goto(all_recipes_deck.html.as_uri(), wait_until="load")
    page.wait_for_function("document.querySelectorAll('.scene__graphic svg').length >= 8", timeout=15000)
    assert page.evaluate(OVERFLOW_AUDIT_JS) == []
    rows = page.evaluate("""() => Array.from(document.querySelectorAll('.scene--simple')).map(sc => {
        const g = sc.querySelector('.scene__graphic').getBoundingClientRect();
        const src = sc.querySelector('.scene__source');
        return {id: sc.id, cardH: g.height, srcBottom: src ? src.getBoundingClientRect().bottom : 0};
    })""")
    for r in rows:
        assert r["cardH"] >= 150, r            # the chart stays readable
        assert r["srcBottom"] <= h - 50, r     # source line clears the slide controls
    page.close()


def test_overflow_audit_catches_an_overflowing_chart(pw, tmp_path: Path):
    res = build({"meta": META, "datasets": {"d": [{"v": 1}]},
                 "scenes": [{"id": "s1", "dataset": "d", "headline": "H", "alt": "a"}]},
                tmp_path / "of", scenes={"s1": 'window.STORY.register("s1", m => { m.style.height = "100px"; '
                                               'm.style.minHeight = "0"; m.style.padding = "0"; '
                                               'm.innerHTML = \'<svg width="100" height="400"><rect width="10" height="10"></rect></svg>\'; });'})
    page = pw.new_page()
    page.goto(res.html.as_uri(), wait_until="load")
    page.wait_for_selector('[data-mount="s1"] svg')
    assert page.evaluate(OVERFLOW_AUDIT_JS) == ["s1"]
    page.close()


def test_vizzu_scene_does_not_block_later_charts_offline(pw, tmp_path: Path):
    dm = recipe_demo("line-reveal")
    story = {
        "meta": META,
        "datasets": {"trend": dm["dataset"]},
        "scenes": [
            {"id": "scene-viz", "kind": "vizzu", "dataset": "trend", "source_line": "demo",
             "alt": "Bars of monthly volume.",
             "series": [{"name": "date", "type": "dimension"}, {"name": "value", "type": "measure"}],
             "frames": [{"headline": "Volume by month",
                         "config": {"channels": {"x": "date", "y": "value"}, "geometry": "rectangle"}}]},
            dict(id="scene-trend", dataset="trend", **dm["scene"]),
        ],
    }
    res = build(story, tmp_path / "rp", scenes={"scene-trend": recipe_js("line-reveal", "scene-trend")},
                vendor=True)
    ctx = pw.new_context()
    ctx.route("**/*", lambda route: route.continue_() if route.request.url.startswith("file:") else route.abort())
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    t0 = time.monotonic()
    page.goto(res.html.as_uri(), wait_until="domcontentloaded")
    page.wait_for_selector('[data-mount="scene-trend"] svg path', timeout=3000)
    assert time.monotonic() - t0 < 2.5, "line-reveal waited on Vizzu"
    # Vizzu can't load offline: its mount degrades to the alt text, not an empty box.
    page.wait_for_selector('[data-mount="scene-viz"] .scene__fallback', timeout=8000)
    assert "Bars of monthly volume." in page.inner_text('[data-mount="scene-viz"]')
    assert not errors, errors
    ctx.close()
