"""#14 milestone 2: the keyboard chart explorer and its aria-live readout,
driven with real key presses in Chromium."""
import pytest

from dstory import build, recipe_js, vet
from dstory.schema import Story

from tests.test_e2e_sweep_1109 import META, _offline_page, _story


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


LIVE = "#dstory-explore-live"


def _live(page):
    return page.text_content(LIVE)


def _visible(page):
    box = page.locator(LIVE).bounding_box()
    return bool(box and box["width"] > 20 and box["height"] > 10)


def test_schema_accepts_explorer_option():
    s = Story.model_validate({"meta": dict(META, a11y={"explorer": False}),
                              "scenes": [{"id": "s1", "a11y": {"explorer": True}}]})
    assert s.meta.a11y.explorer is False and s.scenes[0].a11y.explorer is True


@pytest.fixture(scope="module")
def recipes(tmp_path_factory):
    story, js = _story()
    return story, build(story, tmp_path_factory.mktemp("ex") / "all", scenes=js, vendor=True)


def test_every_recipe_chart_is_explorable(pw, recipes):
    story, r = recipes
    page, errors, _ = _offline_page(pw, r.html)
    page.wait_for_function("Object.values(window.__DSTORY_EXPLORER__?.attached || {}).filter(Boolean).length >= 10",
                           timeout=15000)
    for s in story["scenes"]:
        m = page.locator(f'[data-explore="{s["id"]}"]')
        assert m.count() == 1, s["id"]
        assert m.get_attribute("tabindex") == "0" and m.get_attribute("role") == "application"
        assert m.get_attribute("aria-roledescription") == "chart"
        m.focus()
        summary = _live(page)
        assert summary.startswith(s["headline"]) and "Escape leaves the chart" in summary, summary
        page.keyboard.press("ArrowRight")
        assert _live(page).endswith(f"1 of {len(story['datasets'][s['dataset']])}") or \
            " of " in _live(page), (s["id"], _live(page))
    assert not errors, errors
    page.close()


def test_arrow_keys_read_the_points_and_the_readout_is_visible(pw, recipes):
    _, r = recipes
    page, errors, _ = _offline_page(pw, r.html)
    chart = page.locator('[data-explore="s-line-reveal"]')
    chart.wait_for(timeout=15000)
    # Reach it the way a keyboard user does: Tab from the element before it.
    page.locator('#s-line-reveal h2').evaluate(
        "h => { h.tabIndex = -1; h.focus(); }")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.dataset.explore") == "s-line-reveal"
    assert _visible(page)
    assert "6 points, from 1,200,000 to 3,900,000, rising, peaking at 4,100,000 in May 2024" \
        in _live(page)
    page.keyboard.press("ArrowRight")
    assert _live(page) == "Jan 2024: 1,200,000, 1 of 6"
    page.keyboard.press("ArrowRight")
    assert _live(page) == "Feb 2024: 1,350,000, 2 of 6"
    page.keyboard.press("End")
    assert _live(page) == "Jun 2024: 3,900,000, 6 of 6"
    page.keyboard.press("ArrowRight")                     # stays on the last point
    assert _live(page) == "Jun 2024: 3,900,000, 6 of 6"
    page.keyboard.press("Home")
    assert _live(page).startswith("Jan 2024")
    y = page.evaluate("scrollY")
    page.keyboard.press("ArrowLeft")
    assert page.evaluate("scrollY") == y                 # the arrows don't scroll the page
    page.keyboard.press("Escape")
    assert page.evaluate("document.activeElement.dataset.explore") is None
    assert not _visible(page)
    assert not errors, errors
    page.close()


def test_up_and_down_switch_series_at_the_same_x(pw, recipes):
    _, r = recipes
    page, errors, _ = _offline_page(pw, r.html)
    chart = page.locator('[data-explore="s-small-multiples"]')
    chart.wait_for(timeout=15000)
    chart.focus()
    assert "West, 6 points" in _live(page) and "up and down switch series" in _live(page)
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    assert _live(page) == "2020: index 108 (West), 2 of 6"
    page.keyboard.press("ArrowDown")
    assert _live(page) == "2020: index 105 (Northeast), 2 of 6"
    page.keyboard.press("ArrowUp")
    page.keyboard.press("ArrowUp")                       # wraps round to the last series
    assert _live(page).endswith("(Plains), 2 of 6")
    page.keyboard.press("Enter")
    assert _live(page).startswith("Growth was a coastal story.")
    assert not errors, errors
    page.close()


def test_slides_arrows_belong_to_the_focused_chart_until_escape(pw, tmp_path):
    story, js = _story(mode="slides")
    r = build(story, tmp_path / "sl", scenes=js)
    page, errors, _ = _offline_page(pw, r.html, viewport={"width": 1280, "height": 720})
    page.wait_for_function("Object.values(window.__DSTORY_EXPLORER__?.attached || {}).filter(Boolean).length >= 10",
                           timeout=15000)
    page.wait_for_selector("[data-slide-controls]:not([hidden])", timeout=15000)
    page.keyboard.press("ArrowRight")
    page.wait_for_selector(".scene.is-current [data-explore]", timeout=5000)
    ind = lambda: page.text_content("[data-slide-indicator]")  # noqa: E731
    before = ind()
    page.locator(".scene.is-current [data-explore]").focus()
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    assert ind() == before and " of " in _live(page)
    page.keyboard.press("Escape")
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(300)
    assert ind() != before
    assert not errors, errors
    page.close()


def test_explorer_can_be_turned_off(pw, tmp_path):
    story, js = _story(a11y={"explorer": False})
    story["scenes"][0]["a11y"] = {"explorer": True}
    r = build(story, tmp_path / "off", scenes=js)
    page, errors, _ = _offline_page(pw, r.html)
    page.wait_for_selector("details.scene-data", state="attached", timeout=15000)
    page.wait_for_timeout(300)
    assert page.locator("[data-explore]").count() == 1   # only the scene that opted back in
    assert page.locator("details.scene-data").count() == 10   # the tables stay
    page.close()


def test_vet_drives_the_explorer_and_catches_a_dead_one(tmp_path):
    from dstory.vet import browser_available
    if not browser_available()[0]:
        pytest.skip("no browser")
    story, js = _story()
    r = build(story, tmp_path / "v", scenes=js, vendor=True)
    html = r.html.read_text(encoding="utf-8")
    bad = html.replace("</body>", """<script>
      setTimeout(() => { const m = document.querySelector('[data-explore="s-waffle"]');
                         if (m) m.removeAttribute('data-explore'); }, 300);
    </script></body>""")
    r.html.write_text(bad, encoding="utf-8")
    report = vet(r.html, data=r.project / "data.json", browser=True)
    a11y = next(d for d in report.dimensions if d.name.startswith("Accessibility"))
    assert any("s-waffle: the chart cannot be explored" in i for i in a11y.issues), a11y.issues
    assert not any("s-line-reveal" in i for i in a11y.issues), a11y.issues


def test_drafted_story_is_explorable(pw, tmp_path):
    """build(df) with no options: the drafted small multiples speak every metro."""
    pd = pytest.importorskip("pandas")
    rows = []
    for metro, base, peak in (("Austin", 100, 1.4), ("Boise", 60, 1.5), ("Denver", 90, 1.3)):
        for i, year in enumerate(range(2018, 2024)):
            f = 1 + (peak - 1) * (1 - abs(i - 3) / 3)
            rows.append((f"{year}-01-01", metro, round(base * f, 1)))
    df = pd.DataFrame(rows, columns=["date", "metro", "price"])
    r = build(df, tmp_path / "metros", vendor=True, vet=True, browser=True)
    assert r.passed, [i for d in r.report.dimensions for i in d.issues]
    page, errors, _ = _offline_page(pw, r.html)
    chart = page.locator("#scene-panels [data-explore]")
    chart.wait_for(timeout=15000)
    chart.focus()
    said = _live(page)
    assert all(m in said for m in ("Austin", "Boise", "Denver")), said
    page.keyboard.press("ArrowRight")
    assert _live(page).startswith("2018:") or _live(page).startswith("Jan 2018"), _live(page)
    assert not errors, errors
    page.close()
