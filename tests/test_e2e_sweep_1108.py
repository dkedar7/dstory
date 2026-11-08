"""Browser e2e for #11's final milestone (small multiples with independent
scales, range-dots past 7 categories) and #19 (no false "Total" decline),
checked as the reader sees them: offline, vendored, with the full vet."""
import pytest

pd = pytest.importorskip("pandas")

from dstory import build  # noqa: E402


def _browser_or_skip():
    pytest.importorskip("playwright.sync_api")
    from dstory.vet import browser_available
    ok, why = browser_available()
    if not ok:
        pytest.skip(why)


YEARS = list(range(2018, 2024))
CITIES = {"Austin": [12000, 12800, 14000, 15600, 16800, 18400],
          "Boise": [200, 215, 230, 260, 280, 300],
          "Tulsa": [150, 152, 151, 149, 148, 146],
          "Reno": [250, 262, 280, 300, 330, 350]}
COUNTRIES = ["Chile", "Peru", "Japan", "Kenya", "Spain", "Italy", "Ghana", "Nepal", "Oman",
             "Laos"]


def _open(page, html):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    # Offline: a vendored bundle must not need the network.
    page.route("**/*", lambda r: r.abort() if r.request.url.startswith("http") else r.continue_())
    page.goto(html.as_uri(), wait_until="load")
    return errors


def test_reader_sees_independent_panels_and_range_dots(tmp_path):
    _browser_or_skip()
    panels = pd.DataFrame([{"year": y, "city": c, "price": v} for c, vs in CITIES.items()
                           for y, v in zip(YEARS, vs)])
    r = build(panels, tmp_path / "panels", vendor=True, vet=True, browser=True)
    assert r.passed, [i for d in r.report.dimensions for i in d.issues]

    dots = pd.DataFrame([{"year": y, "country": c, "life_expectancy": 60 + i + k * (i % 4 + 1)}
                         for i, c in enumerate(COUNTRIES) for k, y in enumerate((1990, 2020))])
    r2 = build(dots, tmp_path / "dots", vendor=True, vet=True, browser=True)
    assert r2.passed, [i for d in r2.report.dimensions for i in d.issues]

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1280, "height": 900})
        errors = _open(page, r.html)
        page.locator("#scene-panels").scroll_into_view_if_needed()
        assert "Each panel has its own scale" in page.inner_text("#scene-panels")
        page.wait_for_function(
            "document.querySelectorAll('#scene-panels svg path').length >= 4", timeout=10000)
        # Every panel labels its own range: 2 ticks x 4 panels.
        ticks = page.locator("#scene-panels svg text.scale-tick").all_text_contents()
        assert len(ticks) == 8, ticks
        assert len(set(ticks)) > 2, "panels did not get their own scales"
        # The small panels are not flattened against Austin: each line spans
        # a visible share of its panel's height.
        heights = page.evaluate("""[...document.querySelectorAll('#scene-panels svg path')]
            .map(p => p.getBBox().height)""")
        assert min(heights) > 10, heights
        assert not errors, errors

        page2 = b.new_page(viewport={"width": 1280, "height": 900})
        errors = _open(page2, r2.html)
        page2.locator("#scene-shift").scroll_into_view_if_needed()
        page2.wait_for_function(
            "document.querySelectorAll('#scene-shift svg circle').length >= 20", timeout=10000)
        text = page2.inner_text("#scene-shift")
        assert "1990" in text and "2020" in text
        labels = page2.locator("#scene-shift svg text").all_text_contents()
        assert all(c in labels for c in COUNTRIES), labels
        assert not errors, errors
        b.close()


def test_reader_never_sees_a_false_total_decline(tmp_path):
    _browser_or_skip()
    df = pd.DataFrame({"year": [2022, 2022, 2023, 2023, 2024, 2024],
                       "region": ["North", "South"] * 3,
                       "sales": [100, 100, 110, 105, 120, None]})
    r = build(df, tmp_path / "gap", vendor=True, vet=True, browser=True)
    assert r.passed, [i for d in r.report.dimensions for i in d.issues]
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1280, "height": 900})
        errors = _open(page, r.html)
        body = page.inner_text("body")
        assert "North sales rose 20% between 2022 and 2024" in body
        assert "fell 40%" not in body and "Total sales" not in body
        assert not errors, errors
        b.close()
