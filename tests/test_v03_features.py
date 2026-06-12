"""v0.3.0 features: kind:"custom", Scene.width, Scene.chrome, Story.extra_css,
and the source_line vetter fix."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from dstory import Story, Scene, init, bundle
from dstory.vet import check_editorial


# --- kind: "custom" ---

def test_custom_kind_validates():
    s = Scene.model_validate({"id": "scene-c", "kind": "custom"})
    assert s.kind == "custom"


def test_custom_scene_css_class_in_bundle(tmp_path: Path):
    """Scenes are built at runtime from data.json; the bundle should at least
    include the `.scene--custom` CSS rule so the chrome-free layout works."""
    dest = init(tmp_path / "demo", brand="editorial-noir")
    data = json.loads((dest / "data.json").read_text())
    data["scenes"] = [{"id": "scene-c", "kind": "custom"}]
    (dest / "data.json").write_text(json.dumps(data))
    result = bundle(dest, validate=False)
    html = result.out.read_text()
    # CSS rule is in the inlined story.css
    assert ".scene--custom" in html
    # JS dispatch handles "custom" kind
    assert "buildCustomScene" in html
    assert "activateCustomScene" in html
    # The data.json with the custom scene is embedded
    assert '"kind": "custom"' in html or '"kind":"custom"' in html


# --- Scene.width ---

@pytest.mark.parametrize("width", ["narrow", "default", "wide", "full"])
def test_scene_width_validates(width):
    s = Scene.model_validate({"id": "s", "kind": "simple", "width": width})
    assert s.width == width


def test_scene_width_rejects_unknown():
    with pytest.raises(ValidationError):
        Scene.model_validate({"id": "s", "kind": "simple", "width": "wider-than-wide"})


def test_scene_width_default_is_default():
    s = Scene.model_validate({"id": "s", "kind": "simple"})
    assert s.width == "default"


def test_scene_width_emits_class_in_bundle(tmp_path: Path):
    dest = init(tmp_path / "demo", brand="editorial-noir")
    data = json.loads((dest / "data.json").read_text())
    data["scenes"] = [
        {"id": "narrow-s", "kind": "simple", "width": "narrow"},
        {"id": "wide-s",   "kind": "simple", "width": "wide"},
        {"id": "full-s",   "kind": "simple", "width": "full"},
        {"id": "default-s","kind": "simple"},
    ]
    (dest / "data.json").write_text(json.dumps(data))
    result = bundle(dest, validate=False)
    html = result.out.read_text()
    # Width-modifier classes are added in the JS at build time, but they ARE
    # CSS-defined in story.css (which IS in the bundle).
    css = html  # bundled story.html includes story.css inlined
    assert ".scene--w-narrow" in css
    assert ".scene--w-wide" in css
    assert ".scene--w-full" in css


# --- Scene.chrome ---

def test_scene_chrome_default_is_true():
    s = Scene.model_validate({"id": "s", "kind": "simple"})
    assert s.chrome is True


def test_scene_chrome_validates():
    s = Scene.model_validate({"id": "s", "kind": "simple", "chrome": False})
    assert s.chrome is False


# --- Story.extra_css ---

def test_story_extra_css_field_exists():
    story = Story.model_validate({
        "meta": {"title": "T"},
        "extra_css": ".scene--magazine { display: grid; }",
    })
    assert story.extra_css == ".scene--magazine { display: grid; }"


def test_story_extra_css_appended_at_bundle_time(tmp_path: Path):
    dest = init(tmp_path / "demo", brand="editorial-noir")
    data = json.loads((dest / "data.json").read_text())
    sentinel = ".SENTINEL_EXTRA_CSS_b9f3 { color: hotpink; }"
    data["extra_css"] = sentinel
    (dest / "data.json").write_text(json.dumps(data))
    result = bundle(dest, validate=False)
    html = result.out.read_text()
    assert sentinel in html
    assert 'data-src="story.extra_css"' in html


def test_story_extra_css_optional(tmp_path: Path):
    dest = init(tmp_path / "demo", brand="editorial-noir")
    # data.json has no extra_css set
    result = bundle(dest, validate=False)
    html = result.out.read_text()
    assert 'data-src="story.extra_css"' not in html


# --- vet source_line gate ---

def test_vetter_skips_source_line_on_chrome_free_simple_scenes():
    """A simple scene that doesn't reference a dataset (kinetic typography,
    program note, etc.) should NOT trigger a source_line note."""
    data = {
        "meta": {"title": "T"},
        "scenes": [
            {"id": "scene-typo",  "kind": "simple"},                     # no dataset → skip
            {"id": "scene-chart", "kind": "simple", "dataset": "users"}, # has dataset → demand source
            {"id": "scene-bleed", "kind": "bleed",  "headline": "Big!"}, # bleed → skip
            {"id": "scene-cust",  "kind": "custom"},                     # custom → skip
        ],
        "datasets": {"users": [{"u": 1}]},
    }
    dim = check_editorial("<html></html>", data)
    notes = " ".join(dim.notes)
    assert "scene-typo" not in notes      # chrome-free simple → no warning
    assert "scene-bleed" not in notes     # bleed → no warning
    assert "scene-cust" not in notes      # custom → no warning
    assert "scene-chart" in notes         # has dataset → warning fires


def test_vetter_demands_source_line_on_vizzu_with_frames():
    """A vizzu scene with frames is a chart-bearing scene; missing source_line
    should still trigger the note."""
    data = {
        "meta": {"title": "T"},
        "scenes": [
            {"id": "scene-vz", "kind": "vizzu",
             "frames": [{"headline": "h", "config": {"channels": {"x": "X"}, "geometry": "rectangle"}}]},
        ],
    }
    dim = check_editorial("<html></html>", data)
    assert any("scene-vz" in n for n in dim.notes)
