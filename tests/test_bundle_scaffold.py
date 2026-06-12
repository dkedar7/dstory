"""End-to-end: scaffold + bundle round-trips a working HTML."""
import json
from pathlib import Path

import pytest

from dstory import Brand, init, bundle


def test_scaffold_creates_full_project(tmp_path: Path):
    dest = init(tmp_path / "demo", brand="editorial-noir", audience="general-public")
    assert (dest / "index.html").exists()
    assert (dest / "theme.css").exists()
    assert (dest / "story.css").exists()
    assert (dest / "story.js").exists()
    assert (dest / "data.json").exists()
    assert (dest / "scenes").is_dir()
    # data.json has the right meta defaults
    data = json.loads((dest / "data.json").read_text())
    assert data["meta"]["theme"] == "editorial-noir"
    assert data["meta"]["audience"] == "general-public"
    assert data["meta"]["mode"] == "scroll"
    # theme.css emitted from brand
    css = (dest / "theme.css").read_text()
    assert "--accent:" in css and "#E25822" in css


def test_scaffold_refuses_non_empty_dir_without_overwrite(tmp_path: Path):
    target = tmp_path / "occupied"
    target.mkdir()
    (target / "preexisting.txt").write_text("hi")
    with pytest.raises(FileExistsError):
        init(target, brand="minimal-light")


def test_scaffold_with_slides_mode(tmp_path: Path):
    dest = init(tmp_path / "deck", brand="data-fi", mode="slides", title="My Deck")
    data = json.loads((dest / "data.json").read_text())
    assert data["meta"]["mode"] == "slides"
    assert data["meta"]["title"] == "My Deck"


def test_bundle_inlines_styles_scripts_data(tmp_path: Path):
    dest = init(tmp_path / "demo", brand="editorial-noir")
    # Add a sample scene + dataset so the bundle has something to inline
    data = json.loads((dest / "data.json").read_text())
    data["scenes"].append({
        "id": "scene-hello",
        "kind": "simple",
        "headline": "Hello world",
        "commentary": "Tiny test scene.",
        "source_line": "Source: test fixture",
    })
    (dest / "data.json").write_text(json.dumps(data, indent=2))

    result = bundle(dest)
    assert result.out.exists()
    html = result.out.read_text()
    assert "<style" in html  # theme.css + story.css inlined
    assert "<script>" in html
    assert "__STORY_DATA__" in html
    assert "Hello world" in html  # data injected
    assert result.inlined_styles >= 2
    assert result.inlined_scripts >= 1


def test_bundle_validates_data_json_by_default(tmp_path: Path):
    dest = init(tmp_path / "demo", brand="editorial-noir")
    # Inject an invalid data.json (unknown meta field)
    bad = json.loads((dest / "data.json").read_text())
    bad["meta"]["totally_invalid_field"] = True
    (dest / "data.json").write_text(json.dumps(bad))
    with pytest.raises(Exception):  # pydantic ValidationError
        bundle(dest)


def test_bundle_rejects_dataset_ref_to_missing_dataset(tmp_path: Path):
    dest = init(tmp_path / "demo", brand="editorial-noir")
    data = json.loads((dest / "data.json").read_text())
    data["scenes"].append({"id": "s1", "kind": "simple", "dataset": "nope"})
    (dest / "data.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="nope"):
        bundle(dest)


def test_bundle_patches_title_from_meta(tmp_path: Path):
    """The bundled <title> should reflect meta.title, not the template default."""
    dest = init(tmp_path / "demo", brand="editorial-noir")
    data = json.loads((dest / "data.json").read_text())
    data["meta"]["title"] = "The Fifty Years"
    (dest / "data.json").write_text(json.dumps(data))
    html = bundle(dest, validate=False).out.read_text()
    assert "<title>The Fifty Years</title>" in html
    assert "Untitled Story" not in html
    assert html.count("<title>") == 1  # exactly one title tag


def test_bundle_escapes_title(tmp_path: Path):
    """meta.title is HTML-escaped before being injected into <title>."""
    dest = init(tmp_path / "demo", brand="editorial-noir")
    data = json.loads((dest / "data.json").read_text())
    data["meta"]["title"] = 'A <b> & "C" story'
    (dest / "data.json").write_text(json.dumps(data))
    html = bundle(dest, validate=False).out.read_text()
    assert "&lt;b&gt;" in html and "&amp;" in html
    assert "<title>A <b>" not in html  # raw tag must not leak through


def test_template_index_has_single_title():
    """Guard against the duplicate-line corruption that once bloated the
    template index.html with ~1,100 repeated <title> tags."""
    from importlib.resources import files
    index_html = files("dstory.templates").joinpath("index.html").read_text()
    assert index_html.count("<title>") == 1
    assert index_html.count("\n") < 300  # skeleton, not a corrupted blob


def test_brand_from_toml_used_in_scaffold(tmp_path: Path):
    custom = tmp_path / "acme.toml"
    custom.write_text("""
[brand]
name = "Acme"
extends = "minimal-light"

[colors]
accent = "#FF6B35"
""")
    brand = Brand.from_toml(custom)
    dest = init(tmp_path / "acme-story", brand=brand)
    css = (dest / "theme.css").read_text()
    assert "#FF6B35" in css
    assert "minimal" not in (dest / "data.json").read_text().lower()  # theme slug from brand name
