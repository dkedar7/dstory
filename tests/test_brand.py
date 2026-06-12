"""Brand: presets load, custom TOMLs extend correctly, CSS emits all tokens."""
import pytest
from pathlib import Path

from dstory.brand import Brand, list_presets, _deep_merge


def test_all_eight_presets_load():
    presets = list_presets()
    assert set(presets) == {
        "editorial-noir", "scientific-bright", "tech-glow", "minimal-light",
        "warm-print", "playful-pastel", "brutalist", "data-fi",
    }
    for name in presets:
        b = Brand.from_preset(name)
        assert b.colors.get("accent")
        assert b.typography.get("display")


def test_unknown_preset_raises():
    with pytest.raises(FileNotFoundError):
        Brand.from_preset("does-not-exist")


def test_css_contains_all_token_categories():
    b = Brand.from_preset("editorial-noir")
    css = b.css()
    for token in ("--bg", "--ink", "--accent", "--cat-1", "--cat-7",
                  "--ramp-low", "--ramp-pos", "--font-display", "--motion-base",
                  "--easing-out", "--grain-opacity"):
        assert token in css, f"missing token {token}"


def test_extend_overrides_color_at_top_level():
    b = Brand.from_preset("editorial-noir").extend(accent="#FF6B35")
    assert b.colors["accent"] == "#FF6B35"
    # Other tokens preserved
    assert b.colors["bg"] == "#0E0E10"


def test_extend_with_nested_dict():
    b = Brand.from_preset("editorial-noir").extend(colors={"accent": "#0066FF"})
    assert b.colors["accent"] == "#0066FF"


def test_brand_from_toml_extends_preset(tmp_path: Path):
    custom = tmp_path / "acme.toml"
    custom.write_text("""
[brand]
name = "Acme"
extends = "minimal-light"

[colors]
accent = "#FF6B35"

[typography]
display = "GT America"
""")
    b = Brand.from_toml(custom)
    assert b.name == "Acme"
    assert b.colors["accent"] == "#FF6B35"
    # Inherited from minimal-light
    assert b.colors["bg"] == "#FBFBF9"
    assert b.typography["display"] == "GT America"
    # Original preset font preserved (we only overrode display)
    assert "Manrope" in b.typography["body"]


def test_brand_from_toml_no_extends(tmp_path: Path):
    custom = tmp_path / "self-contained.toml"
    custom.write_text("""
[brand]
name = "Self"

[colors]
bg = "#000"
ink = "#FFF"
accent = "#F00"

[typography]
display = "Foo"
body = "Bar"
mono = "Baz"
""")
    b = Brand.from_toml(custom)
    assert b.colors["bg"] == "#000"


def test_deep_merge_replaces_lists_wholesale():
    base = {"a": {"list": [1, 2, 3]}, "b": "keep"}
    over = {"a": {"list": [9]}}
    merged = _deep_merge(base, over)
    assert merged == {"a": {"list": [9]}, "b": "keep"}


def test_google_fonts_url_built_from_families():
    b = Brand.from_preset("editorial-noir")
    url = b.google_fonts_url()
    assert url and url.startswith("https://fonts.googleapis.com/css2?")
    assert "Fraunces" in url
    assert "display=swap" in url
