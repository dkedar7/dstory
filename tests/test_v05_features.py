"""v0.5.0 features: build() one-call API, cookbook recipes, bundle --vendor,
and the leftover-local-reference safety net.
"""
import json
import re
from pathlib import Path

import pytest

from dstory import (
    Story,
    build,
    bundle,
    init,
    list_recipes,
    recipe_demo,
    recipe_js,
    write_scene,
)
from dstory.bundle import _leftover_local_refs
from dstory.cookbook import RECIPE_DEMOS, recipe_kind

VALID_KINDS = {"simple", "scrolly", "bleed", "pinned", "vizzu", "custom"}


# --- build() one-call API ---

def _demo_story(**meta_extra) -> dict:
    return {
        "meta": {"title": "One Call", "theme": "scientific-bright", **meta_extra},
        "scenes": [{"id": "scene-a", "kind": "simple", "headline": "It works",
                    "commentary": "One cell, one file."}],
        "datasets": {},
    }


def test_build_from_dict(tmp_path: Path):
    result = build(_demo_story(), tmp_path / "story")
    assert result.html.exists()
    assert result.html.name == "story.html"
    assert result.passed is None  # vet not run
    assert "not vetted" in repr(result)
    html = result.html.read_text(encoding="utf-8")
    assert '"title": "One Call"' in html
    assert "<title>One Call</title>" in html


def test_build_from_story_object(tmp_path: Path):
    story = Story.model_validate(_demo_story())
    result = build(story, tmp_path / "story")
    assert result.html.exists()


def test_build_uses_meta_theme_preset(tmp_path: Path):
    result = build(_demo_story(), tmp_path / "story")
    theme_css = (result.project / "theme.css").read_text(encoding="utf-8")
    assert "Scientific Bright" in theme_css  # Brand name in the generated header


def test_build_writes_and_wires_scenes(tmp_path: Path):
    js = 'window.STORY.register("scene-a", () => {});'
    result = build(_demo_story(), tmp_path / "story", scenes={"scene-a": js})
    assert (result.project / "scenes" / "scene-a.js").read_text(encoding="utf-8") == js
    bundled = result.html.read_text(encoding="utf-8")
    assert 'window.STORY.register("scene-a"' in bundled


def test_build_with_vet_static(tmp_path: Path):
    result = build(_demo_story(), tmp_path / "story", vet=True, browser=False)
    assert result.report is not None
    assert result.passed is True


def test_build_reruns_in_place(tmp_path: Path):
    build(_demo_story(), tmp_path / "story")
    result = build(_demo_story(title="Second Run"), tmp_path / "story")
    assert "<title>Second Run</title>" in result.html.read_text(encoding="utf-8")


# --- cookbook registry ---

def test_recipes_discovered():
    names = {r.name for r in list_recipes()}
    assert len(names) >= 10
    assert "line-reveal" in names and "bar-steps" in names


def test_every_recipe_has_valid_metadata():
    for r in list_recipes():
        assert r.kind in VALID_KINDS, f"{r.name}: bad kind {r.kind!r}"
        assert r.summary, f"{r.name}: missing summary"


def test_every_recipe_has_a_demo_and_vice_versa():
    names = {r.name for r in list_recipes()}
    assert names == set(RECIPE_DEMOS)


def test_recipe_js_fills_scene_id():
    js = recipe_js("waffle", "scene-mix")
    assert 'STORY.register("scene-mix"' in js
    assert "__SCENE_ID__" not in js


def test_recipe_kind_matches_demo_kind():
    for name, demo in RECIPE_DEMOS.items():
        assert recipe_kind(name) == demo["scene"]["kind"], name


def test_unknown_recipe_raises():
    with pytest.raises(FileNotFoundError):
        recipe_js("hologram", "s")
    with pytest.raises(KeyError):
        recipe_demo("hologram")


def test_all_demos_validate_against_schema():
    """Each demo must be a legal Story — they're the documentation."""
    for name, demo in RECIPE_DEMOS.items():
        scene = {"id": f"scene-{name}", "dataset": name, **demo["scene"]}
        Story.model_validate({
            "meta": {"title": f"Demo {name}"},
            "scenes": [scene],
            "datasets": {name: demo["dataset"]},
        })


def test_recipe_writes_and_wires(tmp_path: Path):
    dest = init(tmp_path / "demo", brand="editorial-noir")
    write_scene(dest, "scene-swarm", recipe_js("beeswarm", "scene-swarm"))
    index = (dest / "index.html").read_text(encoding="utf-8")
    assert '<script src="scenes/scene-swarm.js" defer></script>' in index


def test_recipes_respect_reduced_motion_and_theme():
    for r in list_recipes():
        src = recipe_js(r.name, "s")
        assert "prefers-reduced-motion" in src, f"{r.name}: no reduced-motion handling"
        assert "var(--" in src, f"{r.name}: not theme-token driven"


# --- leftover local-reference safety net ---

def test_leftover_refs_detected_for_both_quote_styles():
    html = (
        "<script src='sneaky.js'></script>"
        '<script src="missed.js"></script>'
        '<img src="photo.png">'
        '<link rel="stylesheet" href="extra.css">'
        '<script src="https://cdn.example.com/lib.js"></script>'
        '<img src="data:image/png;base64,AAAA">'
    )
    refs = _leftover_local_refs(html)
    assert refs == ["extra.css", "missed.js", "photo.png", "sneaky.js"]


def test_bundle_warns_on_unbundled_local_script(tmp_path: Path):
    dest = init(tmp_path / "demo", brand="editorial-noir")
    index = dest / "index.html"
    html = index.read_text(encoding="utf-8")
    # Single-quoted attribute dodges the inlining regexes — the safety net
    # must flag it.
    index.write_text(html.replace("</body>", "<script src='odd.js'></script>\n</body>"),
                     encoding="utf-8")
    result = bundle(dest, validate=False)
    assert any("odd.js" in w and "NOT" in w for w in result.warnings)


def test_clean_bundle_has_no_leftover_warnings(tmp_path: Path):
    dest = init(tmp_path / "demo", brand="editorial-noir")
    result = bundle(dest, validate=False)
    assert not any("self-contained" in w for w in result.warnings)


# --- vendor (needs network; skips offline) ---

def _network_available() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen("https://cdn.jsdelivr.net", timeout=5).close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _network_available(), reason="no network for CDN fetch")
def test_vendor_inlines_cdn_libs(tmp_path: Path):
    dest = init(tmp_path / "demo", brand="editorial-noir")
    result = bundle(dest, validate=False, vendor=True)
    html = result.html_text if hasattr(result, "html_text") else result.out.read_text(encoding="utf-8")
    # d3 + scrollama + motion vendored
    assert 'data-vendored="https://cdn.jsdelivr.net/npm/d3@7"' in html
    assert 'data-vendored="https://unpkg.com/scrollama"' in html
    assert 'data-vendored="https://cdn.jsdelivr.net/npm/motion@10/dist/motion.min.js"' in html
    assert "window.MOTION = { animate: Motion.animate" in html
    # no remote <script src> left
    assert not re.search(r'<script\b[^>]*\bsrc="https?://', html)
    # no vizzu scenes → the vizzu CDN loader module is dropped
    assert "import Vizzu" not in html
    assert not any("Vendor:" in w for w in result.warnings)


@pytest.mark.skipif(not _network_available(), reason="no network for CDN fetch")
def test_vendor_keeps_vizzu_with_warning_when_used(tmp_path: Path):
    dest = init(tmp_path / "demo", brand="editorial-noir")
    data = json.loads((dest / "data.json").read_text(encoding="utf-8"))
    data["scenes"] = [{
        "id": "scene-vz", "kind": "vizzu", "dataset": "d",
        "series": [{"name": "x"}],
        "frames": [{"headline": "h", "config": {"channels": {"x": "x"}}}],
    }]
    data["datasets"] = {"d": [{"x": "a"}]}
    (dest / "data.json").write_text(json.dumps(data), encoding="utf-8")
    result = bundle(dest, validate=False, vendor=True)
    html = result.out.read_text(encoding="utf-8")
    assert "import Vizzu" in html  # loader kept
    assert any("Vizzu" in w and "network" in w for w in result.warnings)
