"""Nov 10 sweep: data-panel bug fixes (#22, #23, #24)."""
import json
from pathlib import Path
from urllib.parse import unquote

import pytest

from dstory import build, recipe_js, vet
from dstory.schema import Story
from dstory.vet import check_static_a11y

META = {"title": "T", "published": "2026-11-10", "sources": [{"name": "x"}]}


def _one(rows, **scene):
    return {"meta": dict(META, **scene.pop("meta", {})), "datasets": {"r": rows},
            "scenes": [{"id": "scene-a", "kind": "simple", "dataset": "r",
                        "headline": "Things moved", **scene}]}


# ---------- #22: the vetter decides "table present" from the bundle ----------

def test_no_alt_fails_when_the_bundle_ships_no_table(tmp_path):
    story = _one([{"date": f"2024-{m:02d}-01", "value": m} for m in range(1, 7)])
    js = {"scene-a": recipe_js("line-reveal", "scene-a")}
    r = build(story, tmp_path / "off", scenes=js, a11y_extras=False)
    html = r.html.read_text(encoding="utf-8")
    assert 'name="dstory:a11y-extras" content="off"' in html and r.bundle.self_contained
    a11y = check_static_a11y(html, story)
    assert not a11y.passed and any("ships no data table" in i for i in a11y.issues), a11y.issues
    # Bundled normally, the same story keeps the old note and passes.
    on = build(story, tmp_path / "on", scenes=js).html.read_text(encoding="utf-8")
    assert check_static_a11y(on, story).passed
    # A bundle from before 0.11 (no panel, no marker) is not suddenly failed.
    old = on.replace("__DSTORY_DATA_PANEL__", "__X__")
    res = check_static_a11y(old, story)
    assert res.passed and any("predates the data panel" in n for n in res.notes)


def test_cli_vet_fails_a_no_a11y_extras_bundle(tmp_path):
    from click.testing import CliRunner
    from dstory.cli import cli
    story = _one([{"date": f"2024-{m:02d}-01", "value": m} for m in range(1, 7)])
    r = build(story, tmp_path / "s", scenes={"scene-a": recipe_js("line-reveal", "scene-a")})
    run = CliRunner().invoke(cli, ["bundle", str(r.project), "--no-a11y-extras"])
    assert run.exit_code == 0, run.output
    report = vet(r.project / "dist" / "story.html", data=r.project / "data.json", browser=False)
    assert not report.passed


# ---------- #23: CSV injection, including "-" ----------

OWASP = ["-2+3+cmd|' /C calc'!A0", "@SUM(1+1)*cmd|' /C calc'!A0", "=1+1", "+1+1",
         "\t=1", "\r=1", "＝1+1", "＋1", "－1+1", "＠SUM(1)", " =1", "-", "−1+1"]
SAFE = ["-5", "-1.2%", "+3", "1,234", "-0.5e3", "hello", "a-b"]


@pytest.fixture(scope="module")
def browser():
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


def test_csv_neutralises_every_formula_lead(browser, tmp_path):
    rows = [{"label": t, "n": i} for i, t in enumerate(OWASP + SAFE)]
    r = build(_one(rows, alt="x"), tmp_path / "c",
              scenes={"scene-a": recipe_js("bar-steps", "scene-a")})
    page = browser.new_page()
    page.goto(r.html.as_uri())
    a = page.locator('[data-scene-data="scene-a"] a[download]')
    a.wait_for(state="attached", timeout=15000)
    csv = unquote(a.get_attribute("href").split(",", 1)[1]).lstrip("﻿")
    cells = [line.rsplit(",", 1)[0] for line in csv.split("\r\n")[1:]]
    cells = [c[1:-1].replace('""', '"') if c.startswith('"') else c for c in cells]
    for raw, got in zip(OWASP, cells):
        assert got == "'" + raw, (raw, got)
    for raw, got in zip(SAFE, cells[len(OWASP):]):
        assert got == raw, (raw, got)
    page.close()


# ---------- #24: years and IDs are not quantities ----------

def test_schema_table_format():
    s = Story.model_validate(_one([{"year": 2020, "n": 5}], table_format={"year": "raw",
                                                                          "nope": "number"}))
    assert s.scenes[0].table_format == {"year": "raw", "nope": "number"}
    assert any("table_format ['nope']" in i for i in s.validate_dataset_refs())
    with pytest.raises(Exception):
        Story.model_validate(_one([{"year": 2020}], table_format={"year": "plain"}))


def test_table_shows_years_and_ids_without_grouping(browser, tmp_path):
    rows = [{"year": 2020, "fips": 10001, "rank": 1, "pop": 1234567, "sold": 4321, "label": "A", "value": 3},
            {"year": 2021, "fips": 10001, "rank": 2, "pop": 2000000, "sold": 1500, "label": "B", "value": 5}]
    for lang, want in (("en", ["2020", "10001", "1", "1,234,567", "4321", "A", "3"]),
                       ("de", ["2020", "10001", "1", "1.234.567", "4321", "A", "3"])):
        story = _one(rows, alt="x", meta={"lang": lang}, table_format={"sold": "raw"})
        r = build(story, tmp_path / lang, scenes={"scene-a": recipe_js("bar-steps", "scene-a")},
                  vet=True, browser=True)
        assert r.passed, [i for d in r.report.dimensions for i in d.issues]
        page = browser.new_page()
        page.goto(r.html.as_uri())
        panel = page.locator('[data-scene-data="scene-a"]')
        panel.locator("summary").click()
        got = [c.strip() for c in panel.locator("tbody tr").first.locator("th, td")
               .all_text_contents()]
        assert got == want, (lang, got)
        # The CSV is raw values, untouched.
        href = unquote(panel.locator("a[download]").get_attribute("href"))
        assert "2020,10001,1,1234567,4321,A,3" in href
        page.close()
