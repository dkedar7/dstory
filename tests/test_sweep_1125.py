"""Sweep 2026-11-25.

#47: `dstory bundle` inlined any local file that meta.hero_image named
(absolute or ../ paths, any type), so a data.json could ship a secret inside
the story. hero_image is now inlined only from inside the project and only
when it is an image; index.html assets must match their tag's type and, under
`dstory mcp --root`, stay inside the root. The vetter fails a bundled file
that is not an image.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from dstory import build
from dstory.bundle import bundle
from dstory.vet import embedded_data, vet

SECRET = b"AWS_SECRET=abc123\n"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==")


def _story():
    return {"meta": {"title": "Sales held steady", "published": "2026-11-25",
                     "sources": [{"name": "Ledger"}]},
            "scenes": [{"id": "s", "kind": "simple", "dataset": "d",
                        "source_line": "Ledger", "headline": "Sales held steady",
                        "alt": "Line chart of sales, flat at 10."}],
            "datasets": {"d": [{"date": "2024-01-01", "value": 10},
                               {"date": "2024-02-01", "value": 10}]}}


@pytest.fixture
def layout(tmp_path):
    """root/s is the project; outside/ sits next to root, like the issue."""
    root = tmp_path / "root"
    res = build(_story(), root / "s", vet=False)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "credentials").write_bytes(SECRET)
    (outside / "secret.txt").write_bytes(SECRET)
    (outside / "photo.png").write_bytes(PNG)
    (outside / "shared.js").write_text("window.SHARED = 1;", encoding="utf-8")
    return root, res.project, outside


def _set_hero(project: Path, value: str):
    p = project / "data.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["meta"]["hero_image"] = value
    p.write_text(json.dumps(d), encoding="utf-8")


def _assert_no_secret(html: str):
    assert base64.b64encode(SECRET).decode().rstrip("=")[:20] not in html
    assert "AWS_SECRET" not in html


def test_the_issue_repro_through_the_mcp_tool(layout):
    from dstory.agent import bundle_story
    root, project, _ = layout
    _set_hero(project, "../../outside/credentials")
    out = bundle_story("s", root=root)
    html = Path(out["html"]).read_text(encoding="utf-8")
    _assert_no_secret(html)
    assert "hero_image" not in (embedded_data(html)["meta"])
    assert any("../../outside/credentials" in w and "not inlined" in w for w in out["warnings"])


@pytest.mark.parametrize("name", ["secret.txt", "photo.png"])
def test_absolute_paths_outside_the_project_are_refused(layout, name):
    _, project, outside = layout
    _set_hero(project, str(outside / name))
    r = bundle(project)
    html = r.out.read_text(encoding="utf-8")
    _assert_no_secret(html)
    assert "data:image/png" not in html     # even a real picture: data.json may not reach out
    assert any("not inlined" in w for w in r.warnings), r.warnings


def test_a_non_image_inside_the_project_is_refused(layout):
    _, project, _ = layout
    (project / "notes.txt").write_bytes(SECRET)
    _set_hero(project, "notes.txt")
    r = bundle(project)
    _assert_no_secret(r.out.read_text(encoding="utf-8"))
    assert any("not a hero image file" in w for w in r.warnings), r.warnings


def test_a_project_image_still_inlines(layout):
    _, project, _ = layout
    (project / "assets").mkdir()
    (project / "assets" / "hero.png").write_bytes(PNG)
    _set_hero(project, "assets/hero.png")
    r = bundle(project)
    meta = embedded_data(r.out.read_text(encoding="utf-8"))["meta"]
    assert meta["hero_image"].startswith("data:image/png;base64,")
    assert not [w for w in r.warnings if "inlined" in w], r.warnings


def _add_tags(project: Path, tags: str):
    p = project / "index.html"
    p.write_text(p.read_text(encoding="utf-8").replace("</body>", tags + "\n</body>", 1),
                 encoding="utf-8")


def test_index_html_tags_must_name_the_right_kind_of_file(layout):
    _, project, _ = layout
    _add_tags(project, '<script src="../../outside/secret.txt"></script>'
                       '<img src="../../outside/credentials" alt="x">')
    r = bundle(project)
    html = r.out.read_text(encoding="utf-8")
    _assert_no_secret(html)
    assert "outside/secret.txt" not in html
    assert sum("not inlined" in w for w in r.warnings) == 2, r.warnings


def test_outside_assets_still_inline_from_the_cli_but_are_deprecated(layout):
    _, project, _ = layout
    _add_tags(project, '<script src="../../outside/shared.js"></script>')
    r = bundle(project)
    assert "window.SHARED = 1;" in r.out.read_text(encoding="utf-8")
    assert any("deprecated" in w and "shared.js" in w for w in r.warnings), r.warnings


def test_the_mcp_root_confines_index_html_assets(layout):
    from dstory.agent import bundle_story
    root, project, _ = layout
    _add_tags(project, '<script src="../../outside/shared.js"></script>')
    out = bundle_story("s", root=root)
    assert "window.SHARED" not in Path(out["html"]).read_text(encoding="utf-8")
    assert any("outside the allowed root" in w for w in out["warnings"]), out["warnings"]


def _fidelity_a11y(html_path: Path, data_path: Path):
    rep = vet(html_path, data=data_path, browser=False)
    return next(d for d in rep.dimensions if d.name.startswith("Accessibility"))


def test_vet_fails_a_bundle_that_carries_a_non_image(layout):
    """A story.html made by 0.15.1 or older from the issue's data.json."""
    _, project, _ = layout
    r = bundle(project)
    html = r.out.read_text(encoding="utf-8")
    data = embedded_data(html)
    bad = "data:text/plain;base64," + base64.b64encode(SECRET).decode()
    data["meta"]["hero_image"] = bad
    old = html
    marker = "window.__STORY_DATA__ = "
    i = old.index(marker) + len(marker)
    _, end = json.JSONDecoder().raw_decode(old[i:])
    old = old[:i] + json.dumps(data) + old[i + end:]
    old = old.replace("</body>", '<img src="data:application/octet-stream;base64,QQ==" alt="x">'
                      "</body>", 1)
    p = project / "dist" / "old.html"
    p.write_text(old, encoding="utf-8")
    dj = project / "data.json"
    raw = json.loads(dj.read_text(encoding="utf-8"))
    raw["meta"]["hero_image"] = bad
    dj.write_text(json.dumps(raw), encoding="utf-8")
    dim = _fidelity_a11y(p, dj)
    assert not dim.passed
    assert any("'data:text/plain' URI, not an image" in i for i in dim.issues), dim.issues
    assert any("'data:application/octet-stream' URI" in i for i in dim.issues), dim.issues


def test_vet_passes_an_image_hero(layout):
    _, project, _ = layout
    (project / "hero.png").write_bytes(PNG)
    _set_hero(project, "hero.png")
    r = bundle(project)
    dim = _fidelity_a11y(r.out, project / "data.json")
    assert not any("not an image" in i for i in dim.issues), dim.issues
