"""Every scene kind x every mode x a11y extras on/off, in Chromium.

Most layout bugs so far lived where two features meet (slides x simple #8,
vizzu x the scenes after it #16, slides x vizzu #27, scrolly x headline #28).
This matrix checks the reader-visible contract for every combination:
the page has no errors, every scene shows its headline and paints its chart,
the Data panel follows a11y_extras, a slides deck can be walked end to end
with every slide inside the viewport, and a phone never scrolls sideways.
"""
import pytest

from dstory import build, recipe_js

META = {"title": "Matrix", "published": "2026-11-13", "sources": [{"name": "Test data"}]}
BARS = [{"label": "Solar", "value": 31}, {"label": "Wind", "value": 18},
        {"label": "Coal", "value": -12}]
LINE = [{"date": f"20{y}-01-01", "value": v} for y, v in zip(range(18, 24), (5, 7, 6, 9, 12, 15))]
LONG = [{"year": y, "source": s, "value": v} for y in ("2019", "2024")
        for s, v in (("Solar", 40 if y == "2019" else 120), ("Coal", 300 if y == "2019" else 150))]

PAINT = """window.STORY.register("%s", (mount, data, scene) => {
  const box = document.createElement("div");
  box.className = "matrix-mark"; box.textContent = "%s painted";
  box.style.cssText = "min-height:120px;display:grid;place-items:center;";
  mount.append(box);
  %s
});"""
JS = {
    "s-simple": recipe_js("line-reveal", "s-simple"),
    "s-scrolly": recipe_js("bar-steps", "s-scrolly"),
    "s-bleed": PAINT % ("s-bleed", "bleed", "return null;"),
    "s-pinned": PAINT % ("s-pinned", "pinned", "return { onProgress(p) { box.dataset.p = p; } };"),
    "s-custom": PAINT % ("s-custom", "custom",
                         "const h = document.createElement('h2'); h.textContent = scene.headline;"
                         " mount.prepend(h); return null;"),
}
SCENES = [
    {"id": "s-simple", "kind": "simple", "dataset": "line", "headline": "Output tripled since 2018",
     "commentary": "Most of it after 2021.", "alt": "Line rising from 5 to 15.",
     "source_line": "Test data"},
    {"id": "s-scrolly", "kind": "scrolly", "dataset": "bars", "headline": "Coal alone shrank",
     "commentary": "Everything else grew.", "alt": "Bars: Solar 31, Wind 18, Coal -12.",
     "source_line": "Test data", "config": {"label": "label", "y": "value"},
     "steps": [{"headline": "Solar grew most."}, {"headline": "Coal fell."}]},
    {"id": "s-bleed", "kind": "bleed", "headline": "A turning point",
     "commentary": "The year the curve bent."},
    {"id": "s-pinned", "kind": "pinned", "headline": "One object, pinned",
     "commentary": "It changes as you scroll."},
    {"id": "s-vizzu", "kind": "vizzu", "dataset": "long", "headline": "Solar caught up",
     "alt": "Bars by year and source.", "source_line": "Test data",
     "series": [{"name": "year", "type": "dimension"}, {"name": "source", "type": "dimension"},
                {"name": "value", "type": "measure"}],
     "frames": [{"headline": "Two sources, two years",
                 "config": {"channels": {"x": "year", "y": ["value", "source"], "color": "source"},
                            "geometry": "rectangle"}}]},
    {"id": "s-custom", "kind": "custom", "headline": "Built by hand"},
]
WITH_DATA = {"s-simple", "s-scrolly"}          # vizzu: its data panel needs Vizzu's own table
PAINTS = {"s-simple": "svg path", "s-scrolly": "svg rect", "s-bleed": ".matrix-mark",
          "s-pinned": ".matrix-mark", "s-custom": ".matrix-mark"}


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


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = {}
    for mode in ("scroll", "slides"):
        for extras in (True, False):
            story = {"meta": dict(META, mode=mode), "scenes": SCENES,
                     "datasets": {"bars": BARS, "line": LINE, "long": LONG}}
            d = tmp_path_factory.mktemp(f"m-{mode}-{extras}")
            out[mode, extras] = build(story, d / "p", scenes=JS, vendor=True,
                                      a11y_extras=extras, check_claims=False).html
    return out


def _open(pw, html, w=1280, h=800):
    page = pw.new_page(viewport={"width": w, "height": h})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    # Offline: only the file itself. Vizzu cannot load; nothing else may break.
    page.route("**/*", lambda r: r.continue_() if r.request.url.startswith("file:") else r.abort())
    page.goto(html.as_uri(), wait_until="load")
    page.wait_for_selector("#s-custom .matrix-mark", state="attached", timeout=15000)
    return page, errors


@pytest.mark.parametrize("extras", [True, False], ids=["extras", "plain"])
def test_scroll_every_kind_shows_headline_and_paints(pw, built, extras):
    page, errors = _open(pw, built["scroll", extras])
    for s in SCENES:
        sec = page.locator(f"#{s['id']}")
        sec.scroll_into_view_if_needed()
        page.wait_for_timeout(150)
        assert s["headline"] in sec.inner_text(), s["id"]
        if s.get("commentary"):
            assert s["commentary"] in sec.inner_text(), s["id"]
        if s["id"] in PAINTS:
            assert sec.locator(PAINTS[s["id"]]).count() > 0, s["id"]
        panels = sec.locator("details.scene-data").count() + page.locator(
            f'[data-scene-tools="{s["id"]}"] details.scene-data').count()
        if s["id"] in WITH_DATA:
            assert (panels > 0) == extras, (s["id"], panels)
        if not extras:
            assert panels == 0, s["id"]
    assert not errors, errors
    page.close()


@pytest.mark.parametrize("extras", [True, False], ids=["extras", "plain"])
def test_slides_walk_every_kind_end_to_end(pw, built, extras):
    page, errors = _open(pw, built["slides", extras], 1280, 720)
    page.wait_for_selector("[data-slide-controls]:not([hidden])", timeout=15000)
    ind = lambda: page.text_content("[data-slide-indicator]")  # noqa: E731
    total = int(ind().split(" / ")[1])
    seen = set()
    for i in range(total):
        cur = page.locator(".is-current").first
        sid = cur.get_attribute("id")
        if sid in {s["id"] for s in SCENES}:
            seen.add(sid)
            s = next(x for x in SCENES if x["id"] == sid)
            if s["kind"] != "vizzu":                  # offline Vizzu shows its frame headline only
                assert s["headline"] in cur.inner_text(), sid
            if sid in PAINTS:
                mark = cur.locator(PAINTS[sid]).first
                box = mark.bounding_box()
                assert box and box["width"] > 0 and box["height"] > 0, sid
            # Everything on the slide fits the viewport: no clipped headline.
            h = cur.locator("h2:visible, h3:visible").first
            if h.count():
                hb = h.bounding_box()
                assert hb and hb["y"] >= 0 and hb["y"] + hb["height"] <= 720, (sid, hb)
        assert ind() == f"{i + 1} / {total}"
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(120)
    assert seen == {s["id"] for s in SCENES}, seen
    assert ind() == f"{total} / {total}"              # stops at the end
    for _ in range(total):
        page.keyboard.press("ArrowLeft")
    page.wait_for_timeout(120)
    assert ind() == f"1 / {total}"
    assert not errors, errors
    page.close()


@pytest.mark.parametrize("mode", ["scroll", "slides"])
def test_phone_never_scrolls_sideways(pw, built, mode):
    page, errors = _open(pw, built[mode, True], 390, 844)
    for s in SCENES:
        page.locator(f"#{s['id']}").scroll_into_view_if_needed()
    page.wait_for_timeout(200)
    over = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert over <= 1, f"{mode}: page is {over}px wider than the phone"
    assert not errors, errors
    page.close()
