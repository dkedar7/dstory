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


def test_real_vizzu_chart_passes_paint_check(tmp_path):
    _browser_or_skip()
    proj = _project(tmp_path, "real")
    res = bundle(proj, vendor=True)
    report = vet(res.out, data=proj / "data.json", browser=True)
    renders = _renders(report)
    assert not any("did not paint" in i for i in renders.issues), renders.issues
    assert report.passed, [i for d in report.dimensions for i in d.issues]
