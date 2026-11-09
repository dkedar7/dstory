"""#14 milestone 1: every chart ships its own data. A collapsed "Data" panel
(accessible table + offline CSV download) under each data scene, zero config,
checked by the vetter. Also #20 in the browser."""
import json
from pathlib import Path
from urllib.parse import unquote

import pytest

from dstory import build, list_recipes, recipe_demo, recipe_js, vet
from dstory.bundle import bundle
from dstory.schema import Story
from dstory.vet import check_static_a11y

META = {"title": "T", "published": "2026-11-09", "sources": [{"name": "demo"}]}


def _story(mode="scroll", **meta):
    scenes, ds, js = [], {}, {}
    for r in list_recipes():
        d = recipe_demo(r.name)
        sid = "s-" + r.name
        scenes.append({"id": sid, "dataset": sid, **d["scene"]})
        ds[sid] = d["dataset"]
        js[sid] = recipe_js(r.name, sid)
    return {"meta": dict(META, mode=mode, **meta), "scenes": scenes, "datasets": ds}, js


# ---------- static ----------

def test_bundle_injects_the_panel_and_can_leave_it_out(tmp_path):
    story, js = _story()
    r = build(story, tmp_path / "on", scenes=js)
    html = r.html.read_text(encoding="utf-8")
    assert '<script data-dstory="data-panel">' in html and "__DSTORY_DATA_PANEL__" in html
    assert r.bundle.self_contained
    r2 = build(story, tmp_path / "off", scenes=js, a11y_extras=False)
    assert "__DSTORY_DATA_PANEL__" not in r2.html.read_text(encoding="utf-8")
    from click.testing import CliRunner
    from dstory.cli import cli
    res = CliRunner().invoke(cli, ["bundle", str(tmp_path / "on"), "--no-a11y-extras"])
    assert res.exit_code == 0, res.output
    assert "__DSTORY_DATA_PANEL__" not in (tmp_path / "on" / "dist" / "story.html").read_text(
        encoding="utf-8")


def test_schema_accepts_a11y_options_and_checks_table_columns():
    s = Story.model_validate({
        "meta": dict(META, a11y={"table": True, "download": False}),
        "datasets": {"d": [{"month": "Jan", "value": 1}]},
        "scenes": [{"id": "s1", "dataset": "d", "a11y": {"table": False},
                    "table_columns": ["month", "nope"]}]})
    assert s.meta.a11y.download is False and s.scenes[0].a11y.table is False
    assert any("table_columns ['nope']" in i for i in s.validate_dataset_refs())
    with pytest.raises(Exception):
        Story.model_validate({"meta": dict(META, a11y={"tabel": True})})


def test_no_alt_and_no_table_fails_the_vet():
    data = {"meta": META, "datasets": {"d": [{"x": 1}]},
            "scenes": [{"id": "s1", "dataset": "d", "a11y": {"table": False}}]}
    r = check_static_a11y("<html lang='en'></html>", data)
    assert not r.passed and any("table is turned off" in i for i in r.issues)
    data["scenes"][0].pop("a11y")
    assert check_static_a11y("<html lang='en'></html>", data).passed   # a note, as before


# ---------- browser ----------

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


def _offline_page(browser, html: Path, **kw):
    page = browser.new_page(viewport=kw.pop("viewport", {"width": 1280, "height": 900}))
    errors, requests = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))

    def route(r):
        if r.request.url.startswith("http"):
            requests.append(r.request.url)
            return r.abort()
        return r.continue_()
    page.route("**/*", route)
    page.goto(html.as_uri(), wait_until="load")
    return page, errors, requests


def test_every_recipe_gets_a_table_and_csv_that_match_its_data(pw, tmp_path):
    story, js = _story()
    r = build(story, tmp_path / "all", scenes=js, vendor=True)
    page, errors, requests = _offline_page(pw, r.html)
    page.wait_for_function("document.querySelectorAll('details.scene-data').length >= 10",
                           timeout=15000)
    fmt = "(v) => window.__DSTORY_DATA_PANEL__.fmt(v)"
    for s in story["scenes"]:
        rows = story["datasets"][s["dataset"]]
        cols = list(dict.fromkeys(k for row in rows for k in row))
        panel = page.locator(f'[data-scene-data="{s["id"]}"]')
        assert panel.count() == 1, s["id"]
        assert panel.evaluate("d => d.open") is False          # collapsed by default
        # Earlier panels opening shift the page under a scrolly chart, so open
        # this one directly; real clicks are covered by the tests below.
        panel.evaluate("d => { d.open = true; }")
        table = panel.locator("table")
        assert table.is_visible()
        assert table.get_attribute("data-rows") == str(len(rows))
        head = panel.locator("thead th").all_text_contents()
        assert head == cols, s["id"]
        body = panel.locator("tbody tr")
        assert body.count() == min(len(rows), 50)
        for i in (0, min(len(rows), 50) - 1):
            got = [c.strip() for c in body.nth(i).locator("th, td").all_text_contents()]
            want = [page.evaluate(fmt, rows[i].get(c)) for c in cols]
            assert got == want, (s["id"], i)
        href = panel.locator("a[download]").get_attribute("href")
        lines = unquote(href.split(",", 1)[1]).lstrip("﻿").split("\r\n")
        assert len(lines) == len(rows) + 1 and lines[0] == ",".join(cols), s["id"]
        assert panel.locator("a[download]").get_attribute("download") == f"{s['id']}.csv"
    assert not errors, errors
    # --vendor: nothing but the theme's web fonts (which fall back to system
    # fonts offline) is requested for D3 scenes.
    assert [u for u in requests if "fonts.g" not in u] == [], requests
    page.close()


def test_csv_download_delivers_the_rows(pw, tmp_path):
    story, js = _story()
    r = build(story, tmp_path / "dl", scenes=js, vendor=True)
    page, errors, _ = _offline_page(pw, r.html)
    panel = page.locator('[data-scene-data="s-waffle"]')
    panel.wait_for(timeout=15000)
    panel.locator("summary").click()
    with page.expect_download() as info:
        panel.locator("a[download]").click()
    path = info.value.path()
    text = Path(path).read_bytes().decode("utf-8-sig")
    assert text.split("\r\n") == ["label,value", "Gas,38", "Renewables,34", "Coal,18",
                                  "Nuclear,10"]
    page.close()


def test_long_tables_show_50_rows_then_all(pw, tmp_path):
    rows = [{"day": f"2024-01-{d:02d}", "n": d * 1000.5} for d in range(1, 29)] * 3
    story = {"meta": dict(META, lang="de"), "datasets": {"d": rows},
             "scenes": [{"id": "s-long", "dataset": "d", "headline": "Long", "alt": "A table.",
                         "table_columns": ["n", "day"]}]}
    r = build(story, tmp_path / "long", scenes={"s-long": recipe_js("line-reveal", "s-long")})
    page, errors, _ = _offline_page(pw, r.html)
    panel = page.locator('[data-scene-data="s-long"]')
    panel.locator("summary").click()
    assert panel.locator("tbody tr").count() == 50
    assert panel.locator("thead th").all_text_contents() == ["n", "day"]
    # meta.lang drives number formatting: German uses "." for thousands.
    assert panel.locator("tbody tr").first.locator("th").text_content() == "1.000,5"
    panel.locator(".scene-data__all").click()
    assert panel.locator("tbody tr").count() == 84
    assert not errors, errors
    page.close()


def test_slides_mode_t_key_and_clicks_stay_on_the_slide(pw, tmp_path):
    story, js = _story(mode="slides")
    r = build(story, tmp_path / "sl", scenes=js)
    page, errors, _ = _offline_page(pw, r.html, viewport={"width": 1280, "height": 720})
    page.wait_for_selector("details.scene-data", state="attached", timeout=15000)
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(500)
    ind = lambda: page.text_content("[data-slide-indicator]")  # noqa: E731
    before = ind()
    cur = page.locator(".scene.is-current .scene-data")
    assert cur.evaluate("d => d.open") is False
    page.keyboard.press("t")
    assert cur.evaluate("d => d.open") is True
    assert cur.locator("table").is_visible()
    cur.locator("summary").click()                  # closing it must not advance the deck
    assert ind() == before and cur.evaluate("d => d.open") is False
    assert not errors, errors
    page.close()


def test_vet_checks_the_tables_and_catches_a_wrong_one(tmp_path):
    from dstory.vet import browser_available
    if not browser_available()[0]:
        pytest.skip("no browser")
    story, js = _story()
    r = build(story, tmp_path / "v", scenes=js, vendor=True, vet=True, browser=True)
    assert r.passed, [i for d in r.report.dimensions for i in d.issues]
    # Tamper with one cell after the panel is built: the vet must notice.
    html = r.html.read_text(encoding="utf-8")
    bad = html.replace("</body>", """<script>
      setTimeout(() => { const c = document.querySelector('[data-scene-data="s-waffle"] tbody td');
                         if (c) c.textContent = '99'; }, 50);
    </script></body>""")
    r.html.write_text(bad, encoding="utf-8")
    report = vet(r.html, data=r.project / "data.json", browser=True)
    a11y = next(d for d in report.dimensions if d.name.startswith("Accessibility"))
    assert any("s-waffle: table row 1" in i for i in a11y.issues), a11y.issues


def test_superlative_fix_reaches_the_reader(pw, tmp_path):
    """#20: the reader sees the real biggest mover and is told the chart is a subset."""
    pd = pytest.importorskip("pandas")
    rows = []
    for i in range(19):
        base = 1000 + 100 * i
        rows += [(2019, f"City{i:02d}", base), (2023, f"City{i:02d}", round(base * (1.05 + 0.01 * i)))]
    rows += [(2019, "Smallville", 10), (2023, "Smallville", 80)]
    df = pd.DataFrame(rows, columns=["year", "city", "pop"])
    r = build(df, tmp_path / "cities", vendor=True, vet=True, browser=True)
    assert r.passed, [i for d in r.report.dimensions for i in d.issues]
    page, errors, _ = _offline_page(pw, r.html)
    text = page.inner_text("#scene-shift")
    assert "Smallville rose 8-fold" in text and "the text compares every city" in text
    labels = page.locator("#scene-shift svg text").all_text_contents()
    assert "Smallville" in labels and "City00" in labels
    assert not errors, errors
    page.close()
