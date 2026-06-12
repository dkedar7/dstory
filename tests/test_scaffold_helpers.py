"""wire_scenes(), write_scene(), and init(merge=True) — battle-test fixes."""
import re
from pathlib import Path

import pytest

from dstory import init, wire_scenes, write_scene
from dstory.vet import check_editorial


def test_wire_scenes_replaces_placeholder(tmp_path: Path):
    dest = init(tmp_path / "demo", brand="editorial-noir")
    # Sentinel is present after init
    html = (dest / "index.html").read_text()
    assert "DSTORY:SCENES" in html

    wire_scenes(dest, ["scene-a", "scene-b"])
    out = (dest / "index.html").read_text()
    assert 'src="scenes/scene-a.js"' in out
    assert 'src="scenes/scene-b.js"' in out
    # Sentinel is gone
    assert "DSTORY:SCENES" not in out


def test_wire_scenes_idempotent(tmp_path: Path):
    dest = init(tmp_path / "demo", brand="editorial-noir")
    wire_scenes(dest, ["scene-a", "scene-b"])
    first = (dest / "index.html").read_text()
    wire_scenes(dest, ["scene-a", "scene-b"])
    second = (dest / "index.html").read_text()
    assert first == second


def test_wire_scenes_handles_missing_sentinel(tmp_path: Path):
    """If the sentinel was already removed, fall back to inserting after story.js."""
    dest = init(tmp_path / "demo", brand="editorial-noir")
    # Strip the sentinel
    html = (dest / "index.html").read_text()
    html = re.sub(r"<!-- DSTORY:SCENES.*?-->", "", html)
    (dest / "index.html").write_text(html)

    wire_scenes(dest, ["scene-c"])
    out = (dest / "index.html").read_text()
    assert 'src="scenes/scene-c.js"' in out


def test_wire_scenes_ignores_commented_script_tags(tmp_path: Path):
    """Commented-out example <script> tags must not be treated as live tags."""
    dest = init(tmp_path / "demo", brand="editorial-noir")
    # Inject a commented-out example tag (simulating template guidance)
    html = (dest / "index.html").read_text()
    html = html.replace(
        "</body>",
        '<!-- example: <script src="scenes/example-foo.js" defer></script> -->\n</body>',
    )
    (dest / "index.html").write_text(html)

    wire_scenes(dest, ["scene-real"])
    out = (dest / "index.html").read_text()
    # The real scene tag is wired
    assert 'src="scenes/scene-real.js"' in out
    # The commented-out example is preserved as a comment, NOT as a live tag
    assert '<!-- example: <script src="scenes/example-foo.js"' in out
    # No live tag for example-foo
    live_tags = re.sub(r"<!--[\s\S]*?-->", "", out)
    assert 'src="scenes/example-foo.js"' not in live_tags


def test_write_scene_writes_and_wires(tmp_path: Path):
    dest = init(tmp_path / "demo", brand="editorial-noir")
    target = write_scene(dest, "scene-x",
                         "STORY.register('scene-x', function(m,d,s){});\n")
    assert target.exists()
    assert target.name == "scene-x.js"
    out = (dest / "index.html").read_text()
    assert 'src="scenes/scene-x.js"' in out


def test_write_scene_multiple_calls_no_duplicates(tmp_path: Path):
    dest = init(tmp_path / "demo", brand="editorial-noir")
    write_scene(dest, "scene-a", "// a\n")
    write_scene(dest, "scene-b", "// b\n")
    write_scene(dest, "scene-a", "// a updated\n")  # write same id again
    out = (dest / "index.html").read_text()
    # Should only have one tag for scene-a
    assert out.count('src="scenes/scene-a.js"') == 1
    assert out.count('src="scenes/scene-b.js"') == 1


def test_init_merge_preserves_scenes(tmp_path: Path):
    dest = tmp_path / "demo"
    init(dest, brand="editorial-noir")
    # Author writes a scene
    (dest / "scenes" / "my-scene.js").write_text("// my work\n")
    wire_scenes(dest, ["my-scene"])
    custom_data = '{"meta": {"title": "custom"}}'
    (dest / "data.json").write_text(custom_data)

    # Re-init with merge=True (e.g., to upgrade dstory)
    init(dest, brand="editorial-noir", merge=True)

    # Scene + data preserved
    assert (dest / "scenes" / "my-scene.js").read_text() == "// my work\n"
    assert (dest / "data.json").read_text() == custom_data
    # Scene tag re-wired
    out = (dest / "index.html").read_text()
    assert 'src="scenes/my-scene.js"' in out


def test_init_merge_refreshes_framework(tmp_path: Path):
    """Merge mode should still bring in new story.css/story.js from the package."""
    dest = tmp_path / "demo"
    init(dest, brand="editorial-noir")
    # User makes a typo in story.css
    (dest / "story.css").write_text("/* corrupted by user */\n")

    init(dest, brand="editorial-noir", merge=True)
    # Framework restored
    new_css = (dest / "story.css").read_text()
    assert ".scene--scrolly" in new_css
    assert "corrupted" not in new_css


def test_init_uses_settimeout_not_raf_for_layout_wait():
    """Init's layout-settle wait must use setTimeout, not requestAnimationFrame.

    rAF can be starved on very long pages (>10k px) when other scripts are
    initializing — observed during the Bloomberg battle-test where 17 scenes
    on a 17000-px page caused init() to hang at the rAF await. setTimeout(16)
    is more reliable.
    """
    from importlib.resources import files
    story_js = files("dstory.templates").joinpath("story.js").read_text()
    # The layout-settle wait should NOT use raf
    assert "requestAnimationFrame(r)" not in story_js or "// allowed-raf" in story_js, \
        "init()'s layout wait must use setTimeout, not requestAnimationFrame"


def test_editorial_vetter_does_not_demand_source_line_on_bleed(tmp_path: Path):
    """Bleed scenes are intentionally data-free; vetter should not note about them.
    Chart-bearing scenes (with dataset) should still trigger the note."""
    data = {
        "meta": {"title": "T"},
        "scenes": [
            {"id": "scene-a", "kind": "bleed",   "headline": "Big moment"},
            {"id": "scene-b", "kind": "scrolly", "headline": "Chart", "dataset": "x"},
        ],
        "datasets": {"x": [{"v": 1}]},
    }
    dim = check_editorial("<html></html>", data)
    # scene-a is bleed → no note about source_line
    assert not any("scene-a" in n and "source_line" in n for n in dim.notes)
    # scene-b is scrolly with dataset → still gets the note
    assert any("scene-b" in n and "source_line" in n for n in dim.notes)
