"""#18: a blank Vizzu canvas must fail "Renders correctly"; `dstory scene
--kind vizzu` writes no trap; a deleted scene file doesn't break the bundle."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from dstory import vet
from dstory.bundle import bundle
from dstory.scaffold import init, starter_scene_js, write_scene

ROWS = [{"year": "2022", "line": "A", "riders": 10}, {"year": "2022", "line": "B", "riders": 20},
        {"year": "2024", "line": "A", "riders": 30}, {"year": "2024", "line": "B", "riders": 15}]
SCENE = {"id": "scene-morph", "kind": "vizzu", "dataset": "morph", "source_line": "MTA",
         "alt": "Bars: A rose from 10 to 30 while B fell from 20 to 15.",
         "series": [{"name": "year", "type": "dimension"}, {"name": "line", "type": "dimension"},
                    {"name": "riders", "type": "measure"}],
         "frames": [{"headline": "Line A overtook Line B",
                     "config": {"channels": {"x": ["year", "line"], "y": "riders", "color": "line"},
                                "geometry": "rectangle"}}]}


def _project(tmp_path: Path, name: str) -> Path:
    proj = init(tmp_path / name, brand="minimal-light", title="Line A overtook Line B")
    d = json.loads((proj / "data.json").read_text(encoding="utf-8"))
    d["meta"].update(sources=[{"name": "MTA"}], published="2026-11-07")
    d["datasets"] = {"morph": ROWS}
    d["scenes"] = [SCENE]
    (proj / "data.json").write_text(json.dumps(d), encoding="utf-8")
    return proj


def _cli(*args, cwd=None):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-m", "dstory.cli", *args], capture_output=True,
                          env=env, cwd=cwd, timeout=300)


# ---------- static ----------

def test_scene_kind_vizzu_writes_no_js(tmp_path):
    proj = _project(tmp_path, "vz")
    proc = _cli("scene", str(proj), "scene-morph", "--kind", "vizzu")
    out = proc.stdout.decode("utf-8")
    assert proc.returncode == 0, out
    assert "need no JS file" in out and '"frames"' in out
    assert not (proj / "scenes" / "scene-morph.js").exists()
    assert "scenes/scene-morph.js" not in (proj / "index.html").read_text(encoding="utf-8")


def test_deleted_scene_file_is_dropped_from_bundle(tmp_path):
    proj = _project(tmp_path, "del")
    write_scene(proj, "scene-morph", starter_scene_js("scene-morph", "vizzu"))
    (proj / "scenes" / "scene-morph.js").unlink()
    res = bundle(proj)
    html = res.out.read_text(encoding="utf-8")
    assert "scenes/scene-morph.js" not in html
    assert res.self_contained
    assert any("dropped its <script> tag" in w for w in res.warnings)
    proc = _cli("bundle", str(proj))
    assert proc.returncode == 0, proc.stdout.decode("utf-8")


def test_cli_bundle_exits_nonzero_when_not_self_contained(tmp_path):
    proj = _project(tmp_path, "left")
    idx = proj / "index.html"
    # A multi-line tag the inliner can't match survives bundling.
    idx.write_text(idx.read_text(encoding="utf-8").replace(
        "</body>", '<img\n src="local.png">\n</body>'), encoding="utf-8")
    proc = _cli("bundle", str(proj))
    out = proc.stdout.decode("utf-8")
    if "survived bundling" not in out:
        pytest.skip("inliner handled the tag; nothing survived")
    assert proc.returncode == 1 and "not self-contained" in out


# ---------- browser ----------

def _browser_or_skip():
    pytest.importorskip("playwright.sync_api")
    import importlib
    vetmod = importlib.import_module("dstory.vet")
    ok, why = vetmod.browser_available()
    if not ok:
        pytest.skip(why)


def _renders(report):
    return next(d for d in report.dimensions if d.name == "Renders correctly")


def test_blank_vizzu_canvas_fails_renders(tmp_path):
    _browser_or_skip()
    proj = _project(tmp_path, "blank")
    write_scene(proj, "scene-morph", starter_scene_js("scene-morph", "vizzu"))  # the 0.8.0 trap
    res = bundle(proj, vendor=True)
    report = vet(res.out, data=proj / "data.json", browser=True)
    renders = _renders(report)
    assert not renders.passed
    assert any("did not paint" in i and "scene-morph" in i for i in renders.issues), renders.issues


def test_drafted_opener_animates_for_the_reader(tmp_path):
    """#11 milestone 3: `dstory draft` opens with stacked bars that morph into
    lines; the reader sees an inked canvas and both frame headlines, and the
    story passes the full browser vet."""
    _browser_or_skip()
    pd = pytest.importorskip("pandas")
    years = list(range(2015, 2025))
    series = {"Coal": [410, 400, 380, 350, 330, 300, 280, 250, 230, 210],
              "Gas": [300, 310, 330, 340, 360, 370, 380, 390, 395, 400],
              "Solar": [20, 28, 40, 55, 75, 100, 130, 165, 200, 240]}
    pd.DataFrame([{"year": y, "source": s, "twh": v} for s, vals in series.items()
                  for y, v in zip(years, vals)]).to_csv(tmp_path / "grid.csv", index=False)
    proc = _cli("draft", "grid.csv", "--source", "Synthetic grid data", cwd=tmp_path)
    out = proc.stdout.decode("utf-8")
    assert proc.returncode == 0, out
    assert "scene-opener: vizzu opener" in out and "OVERALL: PASS" in out
    assert "PASS (partial)" not in out

    from playwright.sync_api import sync_playwright
    from dstory.vet import PAINT_AUDIT_JS
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto((tmp_path / "grid" / "dist" / "story.html").as_uri(), wait_until="load")
        page.evaluate("document.querySelector('#scene-opener .step[data-step=\"0\"]')"
                      ".scrollIntoView({block: 'center'})")
        page.wait_for_function(f"!{PAINT_AUDIT_JS.strip()}.includes('scene-opener')", timeout=10000)
        text = page.inner_text("#scene-opener")
        assert "Total twh rose 16% between 2015 and 2024" in text
        assert "In 2024, Gas made up 47% of the total" in text
        shot0 = page.locator('[data-mount="scene-opener"]').screenshot()
        page.evaluate("document.querySelector('#scene-opener .step[data-step=\"1\"]')"
                      ".scrollIntoView({block: 'center'})")
        page.wait_for_timeout(2500)                     # the morph to lines
        shot1 = page.locator('[data-mount="scene-opener"]').screenshot()
        assert shot0 != shot1, "the opener did not morph to its second frame"
        assert not errors, errors
        b.close()


def test_real_vizzu_chart_passes_paint_check(tmp_path):
    _browser_or_skip()
    proj = _project(tmp_path, "real")
    res = bundle(proj, vendor=True)
    report = vet(res.out, data=proj / "data.json", browser=True)
    renders = _renders(report)
    assert not any("did not paint" in i for i in renders.issues), renders.issues
    assert report.passed, [i for d in report.dimensions for i in d.issues]
