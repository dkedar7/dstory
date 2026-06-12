"""End-to-end browser checks for the runtime features that static tests can't
see: lang/dir application, hero image, aria-labels on chart mounts, the
reading progress rail, and slides-mode deep-linking.

Requires the [vet] extra AND an installed Chromium (`playwright install
chromium`); skips cleanly when either is missing (e.g. CI without browsers).
Needs network access for the CDN libs (d3, Motion) the template loads.
"""
import json
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from dstory import bundle, init, write_scene  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:
            pytest.skip(f"Chromium unavailable: {e}")
        yield b
        b.close()


SIMPLE_SCENE_JS = """\
window.STORY.register("scene-one", (mount, data, scene) => {
  const svg = d3.select(mount).append("svg").attr("viewBox", "0 0 100 100")
    .attr("width", "100%").attr("height", 300);
  svg.append("circle").attr("cx", 50).attr("cy", 50).attr("r", 40)
    .attr("fill", "var(--accent)");
});
"""


def _write_data(dest: Path, data: dict) -> None:
    (dest / "data.json").write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture(scope="module")
def scroll_story(tmp_path_factory) -> Path:
    dest = init(tmp_path_factory.mktemp("e2e") / "scroll-story", brand="editorial-noir")
    (dest / "assets").mkdir()
    # 1x1 transparent PNG
    import base64
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )
    (dest / "assets" / "hero.png").write_bytes(png)
    _write_data(dest, {
        "meta": {
            "title": "E2E Scroll", "deck": "A test story", "author": "pytest",
            "published": "2026-06-12", "lang": "es",
            "hero_image": "assets/hero.png",
            "sources": [{"name": "Synthetic"}],
        },
        "scenes": [
            {"id": "scene-one", "kind": "simple", "headline": "One big circle",
             "commentary": "It is round.", "dataset": "users",
             "alt": "A circle filled with the accent color.",
             "source_line": "Source: synthetic."},
            {"id": "scene-two", "kind": "scrolly", "dataset": "users",
             "steps": [{"headline": "Step one"}, {"headline": "Step two"}],
             "source_line": "Source: synthetic."},
        ],
        "datasets": {"users": [{"month": "Jan", "users": 10}, {"month": "Feb", "users": 30}]},
    })
    write_scene(dest, "scene-one", SIMPLE_SCENE_JS)
    return bundle(dest, validate=True).out


@pytest.fixture(scope="module")
def slides_story(tmp_path_factory) -> Path:
    dest = init(tmp_path_factory.mktemp("e2e") / "slides-story", brand="minimal-light")
    _write_data(dest, {
        "meta": {"title": "E2E Slides", "mode": "slides"},
        "scenes": [
            {"id": "s1", "kind": "simple", "headline": "First"},
            {"id": "s2", "kind": "simple", "headline": "Second"},
        ],
        "datasets": {},
    })
    return bundle(dest, validate=True).out


def test_scroll_mode_runtime(browser, scroll_story: Path):
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.goto(scroll_story.as_uri(), wait_until="load")
    # Renderer ran → the chart painted.
    page.wait_for_selector('[data-mount="scene-one"] svg', timeout=10000)

    # meta.lang applied to <html>.
    assert page.evaluate("document.documentElement.lang") == "es"

    # Hero image applied with the inlined data URI.
    bg = page.evaluate(
        "document.querySelector('.hero__bg').classList.contains('hero__bg--image')")
    assert bg is True
    img = page.evaluate("document.querySelector('.hero__bg').style.backgroundImage")
    assert img.startswith('url("data:image/png')

    # scene.alt wired to role="img" + aria-label on the mount.
    mount = page.locator('[data-mount="scene-one"]')
    assert mount.get_attribute("role") == "img"
    assert mount.get_attribute("aria-label") == "A circle filled with the accent color."

    # Skip link present and pointing at the story.
    assert page.locator('.skip-link[href="#story"]').count() == 1

    # Progress rail fills as we scroll to the bottom.
    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    page.wait_for_function(
        """() => {
          const t = document.querySelector('.progress-rail__fill').style.transform;
          const m = t.match(/scaleX\\(([\\d.]+)\\)/);
          return m && parseFloat(m[1]) > 0.9;
        }""",
        timeout=5000,
    )
    page.close()


@pytest.fixture(scope="module")
def cookbook_story(tmp_path_factory) -> Path:
    """One story containing every cookbook recipe's demo scene."""
    from dstory import build, recipe_js
    from dstory.cookbook import RECIPE_DEMOS

    scenes, datasets, scripts = [], {}, {}
    for name, demo in RECIPE_DEMOS.items():
        sid = f"scene-{name}"
        scenes.append({"id": sid, "dataset": name, **demo["scene"]})
        datasets[name] = demo["dataset"]
        scripts[sid] = recipe_js(name, sid)

    result = build(
        {"meta": {"title": "Cookbook E2E", "theme": "editorial-noir"},
         "scenes": scenes, "datasets": datasets},
        tmp_path_factory.mktemp("e2e") / "cookbook-story",
        scenes=scripts,
    )
    return result.html


def test_every_cookbook_recipe_paints(browser, cookbook_story: Path):
    from dstory.cookbook import RECIPE_DEMOS

    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(cookbook_story.as_uri(), wait_until="load")

    for name in RECIPE_DEMOS:
        sel = f'[data-mount="scene-{name}"] svg'
        page.wait_for_selector(sel, timeout=15000)
        # The svg must contain actual marks, not just an empty root.
        marks = page.locator(f"{sel} circle, {sel} rect, {sel} path, {sel} line").count()
        assert marks > 0, f"recipe {name}: svg painted no marks"

    recipe_errors = [e for e in errors if "scene-" in e]
    assert not recipe_errors, f"page errors from recipes: {recipe_errors}"
    page.close()


def test_slides_mode_deeplink_and_keyboard(browser, slides_story: Path):
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    # Deep link straight to slide 2 (hero=1, s1=2, s2=3, outro=4).
    page.goto(slides_story.as_uri() + "#slide-2", wait_until="load")
    page.wait_for_function(
        "document.querySelector('[data-slide-indicator]')?.textContent === '2 / 4'",
        timeout=10000,
    )
    assert page.evaluate("document.body.classList.contains('story-mode--slides')")

    # ArrowRight advances and the hash tracks it.
    page.keyboard.press("ArrowRight")
    page.wait_for_function(
        "document.querySelector('[data-slide-indicator]')?.textContent === '3 / 4'",
        timeout=5000,
    )
    assert page.evaluate("location.hash") == "#slide-3"
    page.close()
