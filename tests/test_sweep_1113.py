"""Nov 13 sweep: #28. Scrolly and pinned scenes render their own headline and
commentary, and the vetter grades only text a reader can see."""
import pytest

from dstory import build, recipe_js
from dstory.vet import check_editorial

META = {"title": "Energy", "published": "2026-11-13", "sources": [{"name": "EIA"}]}
BARS = [{"src": "Solar", "chg": 31}, {"src": "Coal", "chg": -12}]
PIN_JS = ('STORY.register("scene-pin", (mount) => '
          '{ mount.textContent = "pinned graphic"; return null; });')


def _story(mode="scroll", **scene_extra):
    scrolly = {"id": "scene-bars", "kind": "scrolly", "dataset": "d", "alt": "Bars.",
               "headline": "Coal was the only source to shrink",
               "commentary": "Everything else grew.", "source_line": "EIA",
               "config": {"label": "src", "y": "chg"},
               "steps": [{"headline": "Solar added the most."}, {"headline": "Coal shrank."}]}
    scrolly.update(scene_extra)
    pinned = {"id": "scene-pin", "kind": "pinned", "headline": "One object, pinned",
              "commentary": "Scroll to reveal it."}
    return ({"meta": dict(META, mode=mode), "scenes": [scrolly, pinned], "datasets": {"d": BARS}},
            {"scene-bars": recipe_js("bar-steps", "scene-bars"), "scene-pin": PIN_JS})


# ---------- the vetter reads what the page shows ----------

def _editorial(data):
    return check_editorial("", data)


def test_placeholder_in_a_visible_scrolly_headline_still_blocks():
    data, _ = _story(headline="TODO lorem ipsum")
    r = _editorial(data)
    assert not r.passed and any("lorem ipsum" in i for i in r.issues), r.issues


def test_placeholder_no_reader_sees_does_not_block():
    data, _ = _story(headline="TODO lorem ipsum", chrome=False)     # hidden by chrome: false
    data["claims"] = [{"id": "c1", "text": "lorem ipsum claim note", "value": 1}]
    r = _editorial(data)
    assert not any("lorem ipsum" in i for i in r.issues), r.issues


def test_placeholder_in_a_data_table_cell_blocks():
    data, _ = _story()
    data["datasets"]["d"][0]["src"] = "Lorem ipsum"                 # readers see it in the table
    assert any("lorem ipsum" in i for i in _editorial(data).issues)


def test_hidden_topic_headline_is_not_graded():
    data, _ = _story(headline="Energy overview", chrome=False)
    assert not any("reads as a topic" in n for n in _editorial(data).notes)
    data, _ = _story(headline="Energy overview")
    assert any("reads as a topic" in n for n in _editorial(data).notes)


# ---------- what the reader sees (Chromium) ----------

@pytest.fixture(scope="module")
def pw():
    pytest.importorskip("playwright.sync_api")
    from dstory.vet import browser_available
    ok, why = browser_available()
    if not ok:
        pytest.skip(why)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _page(pw, html, **vp):
    page = pw.new_page(viewport=vp or {"width": 1280, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(html.as_uri(), wait_until="load")
    page.wait_for_selector("#scene-bars .step", state="attached")
    return page, errors


def test_scrolly_and_pinned_scenes_show_headline_and_commentary(pw, tmp_path):
    story, js = _story()
    r = build(story, tmp_path / "s", scenes=js, vendor=True, check_claims=False)
    page, errors = _page(pw, r.html)
    bars = page.locator("#scene-bars")
    lede = bars.locator(".scene__text > .scene__lede")
    assert lede.locator("h2").inner_text() == "Coal was the only source to shrink"
    assert lede.locator("p").inner_text() == "Everything else grew."
    # The lede comes before the steps, and the steps are untouched.
    assert bars.locator(".scene__text > :first-child").evaluate("e => e.matches('.scene__lede')")
    assert bars.locator(".step h3").all_inner_texts() == ["Solar added the most.", "Coal shrank."]
    lede.scroll_into_view_if_needed()
    assert lede.is_visible()
    pin = page.locator("#scene-pin")
    assert pin.locator("> .scene__lede h2").inner_text() == "One object, pinned"
    assert pin.locator("> .scene__lede p").inner_text() == "Scroll to reveal it."
    assert "Scroll to reveal it." in page.inner_text("body")
    # The graphic still renders, below the lede.
    assert pin.locator("> .scene__pin").inner_text() == "pinned graphic"
    assert pin.locator("> :first-child").evaluate("e => e.matches('.scene__lede')")
    assert not errors, errors
    page.close()


def test_chrome_false_still_hides_it(pw, tmp_path):
    story, js = _story(chrome=False)
    r = build(story, tmp_path / "c", scenes=js, vendor=True, check_claims=False)
    page, errors = _page(pw, r.html)
    assert page.locator("#scene-bars .scene__lede").count() == 0
    assert "only source to shrink" not in page.inner_text("#scene-bars")
    assert not errors, errors
    page.close()


def test_slides_show_the_lede_above_the_active_step(pw, tmp_path):
    story, js = _story(mode="slides")
    r = build(story, tmp_path / "sl", scenes=js, vendor=True, check_claims=False)
    page, errors = _page(pw, r.html, width=1280, height=720)
    page.wait_for_selector("[data-slide-controls]:not([hidden])", timeout=15000)
    page.keyboard.press("ArrowRight")
    page.wait_for_selector("#scene-bars.is-current", timeout=5000)
    lede = page.locator("#scene-bars .scene__lede")
    assert lede.is_visible()
    box, step = lede.bounding_box(), page.locator("#scene-bars .step.is-active").bounding_box()
    assert box["y"] + box["height"] <= step["y"] + 1                 # above, not on top of it
    assert box["y"] >= 0
    assert not errors, errors
    page.close()


def test_drafted_fallback_scene_ships_its_headline(pw, tmp_path):
    pd = pytest.importorskip("pandas")
    from dstory import draft
    d = draft(pd.DataFrame({"team": ["Red", "Blue", "Green", "Gold"], "wins": [42, 35, 28, 19]}),
              title="Teams")
    scene = d.story["scenes"][0]
    assert scene["kind"] == "scrolly" and scene["headline"] == "Red leads on wins"
    r = build(d.story, tmp_path / "t", scenes=d.scenes, vendor=True)
    page = pw.new_page(viewport={"width": 1280, "height": 900})
    page.goto(r.html.as_uri(), wait_until="load")
    page.wait_for_selector(".scene__lede h2", state="attached")
    assert "Red leads on wins" in page.inner_text("body")
    page.close()
