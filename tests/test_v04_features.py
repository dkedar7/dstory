"""v0.4.0 features: lang/dir, social meta tags, hero_image inlining, scene.alt,
readability vetting, quintupled vocab, fmt helpers, starter scenes, favicon,
and the template polish (skip link, progress rail, print styles, slide hash).
"""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from dstory import Meta, Scene, Story, bundle, init, starter_scene_js
from dstory.prep import RATIO_PHRASES, derive_claim_text, fmt_compact, fmt_pct
from dstory.vet import (
    PHRASE_RULES,
    check_data_fidelity,
    check_editorial,
    check_static_a11y,
    flesch_reading_ease,
)


def _project(tmp_path: Path, meta_extra: dict = None, scenes: list = None) -> Path:
    dest = init(tmp_path / "demo", brand="editorial-noir")
    data = json.loads((dest / "data.json").read_text(encoding="utf-8"))
    data["meta"].update(meta_extra or {})
    if scenes is not None:
        data["scenes"] = scenes
    (dest / "data.json").write_text(json.dumps(data), encoding="utf-8")
    return dest


# --- Meta.lang / Meta.dir ---

def test_meta_lang_dir_validate():
    m = Meta.model_validate({"title": "T", "lang": "es", "dir": "rtl"})
    assert m.lang == "es" and m.dir == "rtl"


def test_meta_dir_rejects_unknown():
    with pytest.raises(ValidationError):
        Meta.model_validate({"title": "T", "dir": "sideways"})


def test_bundle_patches_html_lang_and_dir(tmp_path: Path):
    dest = _project(tmp_path, {"lang": "ar", "dir": "rtl"})
    html = bundle(dest, validate=False).out.read_text(encoding="utf-8")
    html_tag = html[html.index("<html"):html.index(">", html.index("<html")) + 1]
    assert 'lang="ar"' in html_tag
    assert 'dir="rtl"' in html_tag


def test_bundle_keeps_default_ltr_unset(tmp_path: Path):
    dest = _project(tmp_path)  # default lang=en (template), dir=ltr
    html = bundle(dest, validate=False).out.read_text(encoding="utf-8")
    html_tag = html[html.index("<html"):html.index(">", html.index("<html")) + 1]
    assert 'lang="en"' in html_tag
    assert "dir=" not in html_tag  # ltr is the HTML default; don't add noise


# --- social meta tags ---

def test_bundle_injects_description_and_og_tags(tmp_path: Path):
    dest = _project(tmp_path, {
        "title": "Growth & Decline",  # & must be escaped
        "deck": "How users tripled in one quarter",
        "author": "Kedar",
    })
    html = bundle(dest, validate=False).out.read_text(encoding="utf-8")
    assert '<meta name="description" content="How users tripled in one quarter">' in html
    assert '<meta name="author" content="Kedar">' in html
    assert '<meta property="og:title" content="Growth &amp; Decline">' in html
    assert '<meta property="og:description"' in html
    assert '<meta name="twitter:card" content="summary">' in html


def test_bundle_share_image_upgrades_twitter_card(tmp_path: Path):
    dest = _project(tmp_path, {"share_image": "https://example.com/card.png"})
    html = bundle(dest, validate=False).out.read_text(encoding="utf-8")
    assert '<meta property="og:image" content="https://example.com/card.png">' in html
    assert '<meta name="twitter:card" content="summary_large_image">' in html


def test_bundle_description_field_beats_deck(tmp_path: Path):
    dest = _project(tmp_path, {"description": "Custom blurb", "deck": "Deck text"})
    html = bundle(dest, validate=False).out.read_text(encoding="utf-8")
    assert '<meta name="description" content="Custom blurb">' in html


# --- hero image ---

def test_meta_hero_image_validates():
    m = Meta.model_validate({"title": "T", "hero_image": "assets/hero.png"})
    assert m.hero_image == "assets/hero.png"


def test_bundle_inlines_local_hero_image(tmp_path: Path):
    dest = _project(tmp_path, {"hero_image": "assets/hero.png"})
    (dest / "assets").mkdir()
    # Tiny valid PNG header bytes are enough for base64 inlining
    (dest / "assets" / "hero.png").write_bytes(b"\x89PNG\r\n\x1a\n0000")
    result = bundle(dest, validate=False)
    html = result.out.read_text(encoding="utf-8")
    assert '"hero_image": "data:image/png;base64,' in html
    assert result.inlined_images >= 1


def test_bundle_leaves_remote_hero_image(tmp_path: Path):
    dest = _project(tmp_path, {"hero_image": "https://example.com/hero.jpg"})
    html = bundle(dest, validate=False).out.read_text(encoding="utf-8")
    assert '"hero_image": "https://example.com/hero.jpg"' in html


def test_bundle_warns_on_missing_hero_image(tmp_path: Path):
    dest = _project(tmp_path, {"hero_image": "assets/nope.png"})
    result = bundle(dest, validate=False)
    assert any("Hero image not found" in w for w in result.warnings)


# --- Scene.alt ---

def test_scene_alt_validates():
    s = Scene.model_validate({"id": "s", "alt": "Line chart: users tripled in Q1."})
    assert s.alt == "Line chart: users tripled in Q1."


def test_vet_notes_chart_scene_without_alt():
    data = {
        "meta": {"title": "T"},
        "scenes": [
            {"id": "with-alt", "kind": "simple", "dataset": "u", "alt": "Bar chart."},
            {"id": "no-alt", "kind": "simple", "dataset": "u"},
            {"id": "no-data", "kind": "simple"},
        ],
        "datasets": {"u": [{"x": 1}]},
    }
    dim = check_static_a11y("<html lang='en'></html>", data)
    notes = " ".join(dim.notes)
    assert "no-alt" in notes
    assert "with-alt" not in notes
    assert "no-data" not in notes
    assert dim.passed  # notes, not failures


def test_vet_notes_missing_html_lang():
    dim = check_static_a11y("<html><body></body></html>", {"meta": {"title": "T"}})
    assert any("lang" in n for n in dim.notes)


# --- readability ---

def test_flesch_easy_text_scores_high():
    text = ("The cat sat on the mat. " * 12)
    score = flesch_reading_ease(text)
    assert score is not None and score > 80


def test_flesch_too_short_returns_none():
    assert flesch_reading_ease("Short text only.") is None


HARD_PROSE = (
    "Notwithstanding considerable organizational heterogeneity, comprehensive "
    "institutionalization of multidimensional accountability infrastructures "
    "necessitates simultaneous reconceptualization of intergovernmental "
    "responsibilities alongside unprecedented technological interoperability "
    "considerations, particularly regarding internationalization initiatives "
    "characterized by extraordinary administrative complexity and persistent "
    "epistemological disagreements concerning methodological standardization."
)


def test_readability_note_for_general_public():
    data = {
        "meta": {"title": "T", "audience": "general-public"},
        "scenes": [{"id": "s1", "kind": "simple", "commentary": HARD_PROSE + " " + HARD_PROSE}],
    }
    dim = check_editorial("<html></html>", data)
    assert any("Readability" in n for n in dim.notes)
    assert dim.passed  # advisory note, not a failure


def test_no_readability_note_for_technical_peer():
    data = {
        "meta": {"title": "T", "audience": "technical-peer"},
        "scenes": [{"id": "s1", "kind": "simple", "commentary": HARD_PROSE + " " + HARD_PROSE}],
    }
    dim = check_editorial("<html></html>", data)
    assert not any("Readability" in n for n in dim.notes)


def test_no_readability_note_for_non_english():
    data = {
        "meta": {"title": "T", "audience": "general-public", "lang": "de"},
        "scenes": [{"id": "s1", "kind": "simple", "commentary": HARD_PROSE + " " + HARD_PROSE}],
    }
    dim = check_editorial("<html></html>", data)
    assert not any("Readability" in n for n in dim.notes)


# --- quintupled (prep + vet stay in sync) ---

def test_quintupled_in_both_vocabularies():
    assert RATIO_PHRASES["quintupled"] == 5.0
    assert any(p.pattern == r"\bquintupled\b" for p, _ in PHRASE_RULES)


def test_derive_claim_text_quintupled():
    assert derive_claim_text(5.05) == "quintupled"


def test_vet_quintupled_pass_and_fail():
    ok = {"meta": {"title": "T"},
          "claims": [{"id": "c1", "text": "Revenue quintupled", "value": 5.02}]}
    bad = {"meta": {"title": "T"},
           "claims": [{"id": "c1", "text": "Revenue quintupled", "value": 4.2}]}
    assert check_data_fidelity("<html></html>", ok).passed
    assert not check_data_fidelity("<html></html>", bad).passed


# --- fmt helpers ---

@pytest.mark.parametrize("n,expected", [
    (1_234_567, "1.2M"),
    (2_000, "2K"),
    (999, "999"),
    (-1_500_000_000, "-1.5B"),
    (3_400_000_000_000, "3.4T"),
    (0, "0"),
])
def test_fmt_compact(n, expected):
    assert fmt_compact(n) == expected


def test_fmt_pct():
    assert fmt_pct(42.0) == "42%"
    assert fmt_pct(7.26) == "7.3%"
    assert fmt_pct(12.0, signed=True) == "+12%"
    assert fmt_pct(-3.5, signed=True) == "-3.5%"


# --- starter scenes ---

@pytest.mark.parametrize("kind", ["simple", "scrolly", "pinned", "bleed", "custom", "vizzu"])
def test_starter_scene_registers_renderer(kind):
    js = starter_scene_js("scene-x", kind)
    assert 'window.STORY.register("scene-x"' in js


def test_starter_scene_contracts():
    assert "onStep" in starter_scene_js("s", "scrolly")
    assert "onProgress" in starter_scene_js("s", "pinned")


def test_starter_scene_unknown_kind_raises():
    with pytest.raises(ValueError):
        starter_scene_js("s", "hologram")


def test_starter_scene_writes_and_wires(tmp_path: Path):
    from dstory import write_scene
    dest = init(tmp_path / "demo", brand="editorial-noir")
    write_scene(dest, "scene-growth", starter_scene_js("scene-growth", "scrolly"))
    assert (dest / "scenes" / "scene-growth.js").exists()
    index = (dest / "index.html").read_text(encoding="utf-8")
    assert '<script src="scenes/scene-growth.js" defer></script>' in index


# --- favicon (Brand.favicon was previously dead code) ---

def test_scaffold_inlines_brand_favicon(tmp_path: Path):
    from dstory import Brand
    fav = tmp_path / "fav.png"
    fav.write_bytes(b"\x89PNG\r\n\x1a\n0000")
    toml = tmp_path / "acme.toml"
    toml.write_text(
        '[brand]\nname = "Acme"\nextends = "minimal-light"\n\n'
        '[brand_marks]\nfavicon = "fav.png"\n',
        encoding="utf-8",
    )
    dest = init(tmp_path / "demo", brand=Brand.from_toml(toml))
    index = (dest / "index.html").read_text(encoding="utf-8")
    assert '<link rel="icon" href="data:image/png;base64,' in index


# --- template polish lands in the bundle ---

def test_bundle_contains_a11y_and_polish_features(tmp_path: Path):
    dest = _project(tmp_path)
    html = bundle(dest, validate=False).out.read_text(encoding="utf-8")
    assert "skip-link" in html               # skip-to-content
    assert "progress-rail" in html           # reading progress bar
    assert "@media print" in html            # print stylesheet
    assert "#slide-" in html                 # slides deep-linking
    assert "aria-live" in html               # slide indicator announces
    assert "hero__bg--image" in html         # hero image support
    assert "revealOnEnter" in html           # simple-scene reveal
    assert 'aria-label", scene.alt' in html  # alt wiring in runtime JS
