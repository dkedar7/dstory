"""Runtime fixes reach existing projects: `dstory bundle` refreshes untouched
story.js / story.css copies from older releases, keeps edited ones, and
`dstory upgrade` reports, restores and (with --force) replaces them."""
import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from dstory import _runtime_history, init
from dstory.bundle import bundle
from dstory.cli import cli
from dstory.scaffold import _packaged_runtime, _runtime_hash, runtime_status

OLD_JS = "// story.js as shipped by an older dstory\nconsole.log('old');\n"
OLD_CSS = "/* story.css as shipped by an older dstory */\nbody { color: red; }\n"


@pytest.fixture
def old_release(monkeypatch):
    """Pretend OLD_JS / OLD_CSS were shipped by an earlier release."""
    known = dict(_runtime_history.KNOWN)
    known["story.js"] = known["story.js"] | {_runtime_hash(OLD_JS)}
    known["story.css"] = known["story.css"] | {_runtime_hash(OLD_CSS)}
    monkeypatch.setattr(_runtime_history, "KNOWN", known)


def _project(tmp_path):
    p = tmp_path / "proj"
    init(p, brand="editorial-noir")
    d = json.loads((p / "data.json").read_text(encoding="utf-8"))
    d["meta"]["sources"] = [{"name": "x"}]
    (p / "data.json").write_text(json.dumps(d), encoding="utf-8")
    return p


def test_current_templates_are_in_the_shipped_history():
    # Fails when story.js / story.css change without re-running
    # scripts/runtime_history.py, which would make the next release's copies
    # look "edited" to every later dstory.
    for name in ("story.js", "story.css"):
        assert _runtime_hash(_packaged_runtime(name)) in _runtime_history.KNOWN[name], (
            f"{name} changed: run `python scripts/runtime_history.py`")


def test_every_released_story_js_is_known():
    root = Path(__file__).resolve().parent.parent
    try:
        tags = subprocess.run(["git", "tag", "--list", "v*"], cwd=root, capture_output=True,
                              text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        tags = []
    if not tags:
        pytest.skip("no git tags here (shallow CI checkout)")
    for tag in tags:
        for name in ("story.js", "story.css"):
            r = subprocess.run(["git", "show", f"{tag}:src/dstory/templates/{name}"], cwd=root,
                               capture_output=True, text=True, encoding="utf-8")
            if r.returncode == 0:
                assert _runtime_hash(r.stdout) in _runtime_history.KNOWN[name], (tag, name)


def test_fresh_project_is_current(tmp_path):
    assert runtime_status(_project(tmp_path)) == {"story.js": "current", "story.css": "current"}


def test_bundle_refreshes_an_untouched_old_copy(tmp_path, old_release):
    p = _project(tmp_path)
    (p / "story.js").write_text(OLD_JS, encoding="utf-8")
    (p / "story.css").write_text(OLD_CSS + "\n\n/* --- brand extras: acme.css --- */\n.acme{}\n",
                                 encoding="utf-8")
    assert runtime_status(p) == {"story.js": "stale", "story.css": "stale"}
    r = bundle(p)
    assert "Updated story.js to this dstory version." in r.warnings
    assert runtime_status(p) == {"story.js": "current", "story.css": "current"}
    html = r.out.read_text(encoding="utf-8")
    assert "sceneLede" in html and "console.log('old')" not in html
    css = (p / "story.css").read_text(encoding="utf-8")
    assert css.endswith("/* --- brand extras: acme.css --- */\n.acme{}\n")   # brand kept
    assert "color: red" not in css


def test_bundle_keeps_an_edited_copy_and_says_how_to_replace_it(tmp_path):
    p = _project(tmp_path)
    edited = _packaged_runtime("story.js") + "\n// my tweak\n"
    (p / "story.js").write_text(edited, encoding="utf-8")
    r = bundle(p)
    assert any("story.js was edited" in w and "dstory upgrade proj --force" in w
               for w in r.warnings), r.warnings
    assert (p / "story.js").read_text(encoding="utf-8") == edited
    assert "// my tweak" in r.out.read_text(encoding="utf-8")


def test_no_upgrade_leaves_old_copies(tmp_path, old_release):
    p = _project(tmp_path)
    (p / "story.js").write_text(OLD_JS, encoding="utf-8")
    bundle(p, upgrade=False)
    assert runtime_status(p)["story.js"] == "stale"


def test_upgrade_command(tmp_path, old_release):
    p = _project(tmp_path)
    runner = CliRunner()
    r = runner.invoke(cli, ["upgrade", str(p)])
    assert r.exit_code == 0 and "story.js is current" in r.output
    (p / "story.js").write_text(OLD_JS, encoding="utf-8")
    (p / "story.css").unlink()
    r = runner.invoke(cli, ["upgrade", str(p)])
    assert "Updated story.js" in r.output and "Restored missing story.css" in r.output
    (p / "story.js").write_text("// mine\n", encoding="utf-8")
    r = runner.invoke(cli, ["upgrade", str(p)])
    assert "kept" in r.output and (p / "story.js").read_text(encoding="utf-8") == "// mine\n"
    r = runner.invoke(cli, ["upgrade", str(p), "--force"])
    assert r.exit_code == 0 and "Replaced edited story.js" in r.output
    backups = list((p / ".dstory-backup").glob("story.js.*"))
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == "// mine\n"
    assert runtime_status(p) == {"story.js": "current", "story.css": "current"}
    assert runner.invoke(cli, ["upgrade", str(tmp_path / "nope")]).exit_code == 1
