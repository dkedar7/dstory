"""Nov 12 sweep: #25 (claim drift in the headline), #26 (CLI honours
meta.theme), #27 (slides deck navigable while Vizzu loads)."""
import json
import re
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from dstory import build, recipe_js, vet
from dstory.cli import cli
from dstory.prep import compute_claim, compute_ratio
from dstory.vet import check_data_fidelity

META = {"title": "Q1 signups", "published": "2026-11-12", "sources": [{"name": "CRM export"}]}


# ---------- #25 ----------

def _q1(headline="Signups tripled in Q1", claim_scene="scene-trend"):
    claim = compute_claim(id="c1", text_template="Signups {phrase} in Q1",
                          value=compute_ratio(after=2900, before=1000), scene=claim_scene)
    return {"meta": dict(META), "claims": [claim],
            "scenes": [{"id": "scene-trend", "kind": "simple", "dataset": "m",
                        "headline": headline, "source_line": "CRM export",
                        "alt": "Line: signups grew from 1,000 in January to 2,900 in March."}],
            "datasets": {"m": [{"date": "2024-01-01", "value": 1000},
                               {"date": "2024-02-01", "value": 1500},
                               {"date": "2024-03-01", "value": 2900}]}}


def test_headline_that_contradicts_its_claim_fails():
    data = _q1("Signups quintupled in Q1")
    assert data["claims"][0]["text"] == "Signups tripled in Q1"
    r = check_data_fidelity("", data)
    assert not r.passed
    assert any("scene-trend" in i and "quintupled" in i for i in r.issues), r.issues
    # The claims array is not "reader-facing prose" any more.
    assert any("not in any reader-facing text" in n for n in r.notes), r.notes


def test_matching_headline_passes_and_other_claims_can_cover_a_word():
    assert check_data_fidelity("", _q1()).passed
    data = _q1("Signups tripled while churn halved")
    data["claims"].append(compute_claim(id="c2", text_template="Churn {phrase}",
                                        value=compute_ratio(after=50, before=100),
                                        scene="scene-trend"))
    assert check_data_fidelity("", data).passed, check_data_fidelity("", data).issues
    data["scenes"][0]["commentary"] = "That is a 9-fold jump."
    r = check_data_fidelity("", data)
    assert not r.passed and any("9-fold" in i for i in r.issues)


def test_drift_is_caught_at_bundle_time_and_by_vet(tmp_path):
    from dstory.bundle import ClaimDriftError
    js = {"scene-trend": recipe_js("line-reveal", "scene-trend")}
    with pytest.raises(ClaimDriftError, match="quintupled"):
        build(_q1("Signups quintupled in Q1"), tmp_path / "b", scenes=js)
    r = build(_q1("Signups quintupled in Q1"), tmp_path / "v", scenes=js, check_claims=False)
    report = vet(r.html, data=r.project / "data.json", browser=False)
    fid = next(d for d in report.dimensions if d.name == "Data fidelity")
    assert not fid.passed


def test_drafted_stories_still_pass_fidelity(tmp_path):
    pd = pytest.importorskip("pandas")
    from dstory import draft
    rows = [(y, c, v) for y, vals in ((2019, (10, 100, 50)), (2023, (80, 110, 40)))
            for c, v in zip(("Smallville", "Bigtown", "Midburg"), vals)]
    d = draft(pd.DataFrame(rows, columns=["year", "city", "pop"]), title="Cities")
    data = d.story.model_dump(exclude_none=True) if hasattr(d.story, "model_dump") else d.story
    assert data["claims"]
    r = check_data_fidelity("", data)
    assert r.passed, r.issues


# ---------- #26 ----------

def _project(tmp_path, theme="editorial-noir"):
    runner = CliRunner()
    slug = str(tmp_path / "tt")
    assert runner.invoke(cli, ["init", slug, "--theme", theme]).exit_code == 0
    assert runner.invoke(cli, ["scene", slug, "scene-trend", "--from", "line-reveal"]).exit_code == 0
    d = json.loads((Path(slug) / "data.json").read_text(encoding="utf-8"))
    d["meta"]["sources"] = [{"name": "x"}]
    d["scenes"] = [{"id": "scene-trend", "kind": "simple", "dataset": "m", "headline": "Up",
                    "alt": "Line rising.", "source_line": "x"}]
    d["datasets"] = {"m": [{"date": "2024-01-01", "value": 1}, {"date": "2024-02-01", "value": 3}]}
    return runner, Path(slug), d


def _accent(html):
    return re.search(r"--accent:\s*(#[0-9A-Fa-f]+)", html).group(1).upper()


def test_bundle_honours_meta_theme(tmp_path):
    from dstory.brand import Brand
    runner, p, d = _project(tmp_path)
    d["meta"]["theme"] = "scientific-bright"
    (p / "data.json").write_text(json.dumps(d), encoding="utf-8")
    res = runner.invoke(cli, ["bundle", str(p)])
    assert res.exit_code == 0, res.output
    assert "Re-themed" in res.output
    html = (p / "dist" / "story.html").read_text(encoding="utf-8")
    want = Brand.from_preset("scientific-bright").colors["accent"].upper()
    assert _accent(html) == want and 'data-theme="scientific-bright"' in html


def test_unknown_theme_warns_and_edited_css_is_kept(tmp_path):
    runner, p, d = _project(tmp_path)
    d["meta"]["theme"] = "scientfic-brite"
    (p / "data.json").write_text(json.dumps(d), encoding="utf-8")
    res = runner.invoke(cli, ["bundle", str(p)])
    assert res.exit_code == 0 and "Unknown theme 'scientfic-brite'" in res.output
    assert "warm-print" in res.output                     # lists the presets
    # A hand-edited theme.css is never overwritten silently.
    (p / "theme.css").write_text((p / "theme.css").read_text(encoding="utf-8")
                                 + "\n/* mine */\n", encoding="utf-8")
    d["meta"]["theme"] = "warm-print"
    (p / "data.json").write_text(json.dumps(d), encoding="utf-8")
    res = runner.invoke(cli, ["bundle", str(p)])
    assert "theme.css has been edited" in res.output
    assert "/* mine */" in (p / "theme.css").read_text(encoding="utf-8")


def test_theme_command(tmp_path):
    runner, p, d = _project(tmp_path)
    (p / "data.json").write_text(json.dumps(d), encoding="utf-8")
    res = runner.invoke(cli, ["theme", str(p), "warm-print"])
    assert res.exit_code == 0, res.output
    assert json.loads((p / "data.json").read_text(encoding="utf-8"))["meta"]["theme"] == "warm-print"
    assert 'data-theme="warm-print"' in (p / "index.html").read_text(encoding="utf-8")
    res = runner.invoke(cli, ["bundle", str(p)])
    assert res.exit_code == 0 and "Re-themed" not in res.output
    assert runner.invoke(cli, ["theme", str(p), "nope"]).exit_code == 1


def test_build_with_custom_brand_is_left_alone(tmp_path):
    from dstory.brand import Brand
    b = Brand.from_preset("tech-glow")
    b.name = "Acme Corp"
    r = build({"meta": dict(META), "scenes": [], "datasets": {}}, tmp_path / "c", brand=b)
    assert not any("theme" in w.lower() for w in r.bundle.warnings), r.bundle.warnings


# ---------- #27 ----------

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


def test_slides_deck_with_vizzu_is_navigable_at_once_offline(pw, tmp_path):
    story = {"meta": dict(META, title="Deck", mode="slides"),
             "datasets": {
                 "long": [{"year": "2015", "variable": "Solar", "value": 40},
                          {"year": "2024", "variable": "Solar", "value": 120}],
                 "slope": [{"label": "Solar", "start": 40, "end": 120},
                           {"label": "Coal", "start": 300, "end": 150}]},
             "scenes": [
                 {"id": "scene-vz", "kind": "vizzu", "dataset": "long", "alt": "Bars.",
                  "source_line": "x",
                  "series": [{"name": "year", "type": "dimension"},
                             {"name": "variable", "type": "dimension"},
                             {"name": "value", "type": "measure"}],
                  "frames": [{"headline": "Solar", "config": {"channels": {"x": "year", "y": "value"},
                                                              "geometry": "rectangle"}}]},
                 {"id": "scene-slope", "kind": "simple", "headline": "Solar tripled",
                  "dataset": "slope", "alt": "Slope chart.", "source_line": "x"}]}
    r = build(story, tmp_path / "deck", scenes={"scene-slope": recipe_js("slope-chart", "scene-slope")},
              vendor=True, check_claims=False)
    page = pw.new_page(viewport={"width": 1280, "height": 720})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route("**/*", lambda rt: rt.continue_() if rt.request.url.startswith("file:") else rt.abort())
    t0 = time.time()
    page.goto(r.html.as_uri(), wait_until="domcontentloaded")
    ind = lambda: page.text_content("[data-slide-indicator]")  # noqa: E731
    page.wait_for_function("document.querySelector('[data-slide-indicator]').textContent !== '0 / 0'",
                           timeout=3000)
    assert time.time() - t0 < 2.5                      # not the 4 s Vizzu timeout
    total = ind().split(" / ")[1]
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(100)
    assert ind() == f"3 / {total}"                     # neither press was dropped
    assert page.locator("#scene-slope.is-current").count() == 1
    page.keyboard.press("ArrowLeft")                   # back onto the (offline, inert) Vizzu slide
    assert ind() == f"2 / {total}"
    page.wait_for_timeout(4500)                        # Vizzu gives up; nothing breaks
    page.keyboard.press("ArrowRight")
    assert ind() == f"3 / {total}"
    page.close()
