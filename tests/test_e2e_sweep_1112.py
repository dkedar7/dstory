"""#14 milestone 3: "Listen" — every chart can be heard. Driven in Chromium,
counting the AudioContext and oscillators the page actually creates."""
import pytest

from dstory import build, vet
from dstory.schema import Story

from tests.test_e2e_sweep_1109 import META, _story

# Count what the page asks Web Audio for, without silencing it.
COUNT_AUDIO = """
window.__audio = { contexts: 0, oscillators: 0, freqs: [] };
const _AC = window.AudioContext;
window.AudioContext = class extends _AC {
  constructor(...a) { super(...a); window.__audio.contexts++; }
  createOscillator() {
    const o = super.createOscillator(); window.__audio.oscillators++;
    const f = o.frequency; const set = Object.getOwnPropertyDescriptor(AudioParam.prototype, 'value').set;
    Object.defineProperty(f, 'value', { set(v) { window.__audio.freqs.push(v); set.call(f, v); },
                                        get() { return f.defaultValue; } });
    return o;
  }
};
"""


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
def recipes(tmp_path_factory):
    story, js = _story()
    return story, build(story, tmp_path_factory.mktemp("li") / "all", scenes=js, vendor=True)


def _open(pw, html, viewport=None):
    page = pw.new_page(viewport=viewport or {"width": 1280, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script(COUNT_AUDIO)
    page.route("**/*", lambda r: r.abort() if r.request.url.startswith("http") else r.continue_())
    page.goto(html.as_uri(), wait_until="load")
    page.wait_for_function("window.__DSTORY_LISTEN__ && "
                           "Object.keys(window.__DSTORY_LISTEN__.attached).length >= 10",
                           timeout=15000)
    return page, errors


def test_schema_accepts_sonify():
    s = Story.model_validate({"meta": dict(META, a11y={"sonify": False}),
                              "scenes": [{"id": "s1", "a11y": {"sonify": True}}]})
    assert s.meta.a11y.sonify is False and s.scenes[0].a11y.sonify is True


def test_every_numeric_chart_has_a_listen_button_and_nothing_autoplays(pw, recipes):
    story, r = recipes
    page, errors = _open(pw, r.html)
    page.wait_for_timeout(500)
    assert page.evaluate("window.__audio") == {"contexts": 0, "oscillators": 0, "freqs": []}
    for s in story["scenes"]:
        b = page.locator(f'[data-listen="{s["id"]}"]')
        if s["id"] == "s-dot-timeline":          # dates and labels only: nothing to hear
            assert b.count() == 0
            continue
        assert b.count() == 1, s["id"]
        assert b.text_content() == "▶ Listen" and b.get_attribute("aria-pressed") == "false"
        assert b.get_attribute("aria-label") == f"Listen to the chart: {s['headline']}"
        # It sits in the same row as the Data panel.
        assert b.evaluate("b => b.parentElement.matches('.scene-tools') && "
                          "!!b.parentElement.querySelector('details.scene-data')")
    assert not errors, errors
    page.close()


def test_listen_schedules_one_oscillator_per_point_with_pitch_following_value(pw, recipes):
    story, r = recipes
    page, errors = _open(pw, r.html)
    b = page.locator('[data-listen="s-line-reveal"]')
    b.scroll_into_view_if_needed()
    b.click()
    audio = page.evaluate("window.__audio")
    rows = story["datasets"]["s-line-reveal"]
    assert audio["contexts"] == 1 and audio["oscillators"] == len(rows)
    vals = [row["value"] for row in rows]
    order = sorted(range(len(vals)), key=vals.__getitem__)
    assert sorted(range(len(vals)), key=audio["freqs"].__getitem__) == order
    assert min(audio["freqs"]) == pytest.approx(220) and max(audio["freqs"]) == pytest.approx(880)
    assert b.text_content() == "■ Stop" and b.get_attribute("aria-pressed") == "true"
    # The series is announced, and shown, while it plays.
    live = page.locator("#dstory-explore-live")
    page.wait_for_function("document.getElementById('dstory-explore-live').textContent.length > 0")
    assert "6 points, from 1,200,000 to 3,900,000, rising" in live.text_content()
    assert live.evaluate("e => e.classList.contains('is-visible')")
    b.click()                                              # stop
    assert b.text_content() == "▶ Listen"
    assert page.evaluate("window.__DSTORY_LISTEN__.playing") is None
    assert not live.evaluate("e => e.classList.contains('is-visible')")
    assert not errors, errors
    page.close()


def test_series_play_in_turn_and_l_plays_the_focused_series(pw, recipes):
    _, r = recipes
    page, errors = _open(pw, r.html)
    plan = page.evaluate("window.__DSTORY_LISTEN__.plan('s-small-multiples')")
    assert [s["key"] for s in plan["series"]] == ["West", "Northeast", "Midwest", "South",
                                                  "Mountain", "Plains"]
    starts = [s["start"] for s in plan["series"]]
    ends = [s["end"] for s in plan["series"]]
    assert all(e < s2 for e, s2 in zip(ends, starts[1:]))       # one after another
    assert all(n["pan"] < m["pan"] for s in plan["series"]
               for n, m in zip(s["notes"], s["notes"][1:]))     # left to right
    chart = page.locator('[data-explore="s-small-multiples"]')
    chart.focus()
    assert "L plays this series as sound" in page.text_content("#dstory-explore-live")
    page.keyboard.press("ArrowDown")                            # Northeast
    page.keyboard.press("l")
    assert page.evaluate("window.__audio.oscillators") == 6     # just that series
    page.wait_for_function("document.getElementById('dstory-explore-live')"
                           ".textContent.startsWith('Northeast')")
    page.keyboard.press("Escape")                               # stops, and leaves the chart
    assert page.evaluate("window.__DSTORY_LISTEN__.playing") is None
    assert not errors, errors
    page.close()


def test_scatter_plays_along_x(pw, recipes):
    story, r = recipes
    page, _ = _open(pw, r.html)
    plan = page.evaluate("window.__DSTORY_LISTEN__.plan('s-annotated-scatter')")
    scene = next(s for s in story["scenes"] if s["id"] == "s-annotated-scatter")
    x, y = scene["config"]["x"], scene["config"]["y"]
    rows = story["datasets"]["s-annotated-scatter"]
    xs = [rows[n["row"]][x] for n in plan["series"][0]["notes"]]
    assert xs == sorted(xs) and plan["measure"] == y
    assert [n["row"] for n in plan["series"][0]["notes"]] != list(range(len(rows)))
    page.close()


def test_slides_listen_click_does_not_advance(pw, tmp_path):
    story, js = _story(mode="slides")
    r = build(story, tmp_path / "sl", scenes=js)
    page, errors = _open(pw, r.html, viewport={"width": 1280, "height": 720})
    page.wait_for_selector("[data-slide-controls]:not([hidden])", timeout=15000)
    page.keyboard.press("ArrowRight")
    page.wait_for_selector(".scene.is-current [data-listen]", timeout=5000)
    before = page.text_content("[data-slide-indicator]")
    page.locator(".scene.is-current [data-listen]").click()
    assert page.text_content("[data-slide-indicator]") == before
    assert page.evaluate("window.__audio.contexts") == 1
    assert not errors, errors
    page.close()


def test_sonify_off_and_vet_catches_a_missing_button(pw, tmp_path):
    story, js = _story(a11y={"sonify": False})
    r = build(story, tmp_path / "off", scenes=js)
    page, _ = _open(pw, r.html)
    page.wait_for_function("document.querySelectorAll('details.scene-data').length >= 10",
                           timeout=15000)
    assert page.locator("[data-listen]").count() == 0
    assert page.locator("details.scene-data").count() == 10      # tables stay
    page.close()
    story, js = _story()
    r = build(story, tmp_path / "v", scenes=js, vendor=True, vet=True, browser=True)
    assert r.passed, [i for d in r.report.dimensions for i in d.issues]
    html = r.html.read_text(encoding="utf-8")
    r.html.write_text(html.replace("</body>", """<script>
      setTimeout(() => document.querySelector('[data-listen="s-waffle"]')?.remove(), 300);
    </script></body>"""), encoding="utf-8")
    report = vet(r.html, data=r.project / "data.json", browser=True)
    a11y = next(d for d in report.dimensions if d.name.startswith("Accessibility"))
    assert any("s-waffle: no Listen button" in i for i in a11y.issues), a11y.issues
