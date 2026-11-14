"""#21 milestone 1: `dstory vet --json` and `dstory mcp`.

The e2e test drives the real stdio server with the official MCP Python
client, the way Claude Code or Cursor would: draft a story from a CSV, vet
it, look at a scene, break a claim and see the vet name it, then open the
bundled file offline in Chromium and check the charts paint.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from dstory import agent
from dstory.cli import cli

ROOT = Path(__file__).resolve().parents[1]
MIX = ROOT / "docs" / "drafted" / "mix.csv"


# ---------- plain functions ----------

def test_paths_are_confined_to_root(tmp_path):
    assert agent.resolve("a/b", tmp_path) == (tmp_path / "a" / "b").resolve()
    for bad in ("../x", str(tmp_path.parent / "x"), "a/../../x"):
        with pytest.raises(agent.AgentError, match="outside the allowed root"):
            agent.resolve(bad, tmp_path)


def test_not_a_project_is_a_clear_error(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(agent.AgentError, match="not a dstory project"):
        agent.vet_story("empty", root=tmp_path, browser=False)


@pytest.fixture(scope="module")
def drafted(tmp_path_factory):
    pytest.importorskip("pandas")
    root = tmp_path_factory.mktemp("agent")
    shutil.copy(MIX, root / "mix.csv")
    out = agent.draft_story("mix.csv", root=root, title="Power mix", browser=False)
    return root, out


def test_draft_story_returns_structure(drafted):
    root, out = drafted
    assert Path(out["html"]).is_file()
    assert out["project"] == str((root / "mix").resolve())
    assert out["scenes"] and all("id" in s and "kind" in s for s in out["scenes"])
    assert out["claims"] and "explain" in out and "Profile" in out["explain"]
    assert out["vet"]["passed"] is True and out["vet"]["failures"] == []
    assert {d["key"] for d in out["vet"]["dimensions"]} >= {"data_fidelity", "editorial_integrity"}


def test_vet_json_matches_the_tool_and_keeps_exit_code(drafted):
    root, out = drafted
    html, data = out["html"], out["data_json"]
    r = CliRunner().invoke(cli, ["vet", html, "--data", data, "--no-browser", "--json"])
    assert r.exit_code == 0, r.output
    got = json.loads(r.stdout)
    tool = agent.vet_story("mix", root=root, browser=False)
    assert got.keys() == tool.keys()
    assert got["passed"] is True and got["skipped"]

    # Break a claim: the JSON names it, and the exit code is 1 as before.
    d = json.loads(Path(data).read_text(encoding="utf-8"))
    bad = dict(d["claims"][0], text="Gas quintupled", unit="ratio", value=1.1)
    d["claims"].append(dict(bad, id="c-bad"))
    broken = Path(data).with_name("broken.json")
    broken.write_text(json.dumps(d), encoding="utf-8")
    r = CliRunner().invoke(cli, ["vet", html, "--data", str(broken), "--no-browser", "--json"])
    assert r.exit_code == 1
    rep = json.loads(r.stdout)
    assert rep["passed"] is False
    assert any(f["claim"] == "c-bad" and f["dimension"] == "data_fidelity"
               for f in rep["failures"])


def test_bundle_story_reports_drift_as_data(drafted):
    root, out = drafted
    p = Path(out["data_json"])
    original = p.read_text(encoding="utf-8")
    d = json.loads(original)
    from dstory.vet import _scene_text_shown
    shown = {s["id"]: s for s in d["scenes"] if _scene_text_shown(s)}
    c = next(c for c in d["claims"] if c.get("scene") in shown and c.get("unit"))
    shown[c["scene"]]["headline"] = "Everything quintupled"
    p.write_text(json.dumps(d), encoding="utf-8")
    try:
        res = agent.bundle_story("mix", root=root)
        assert res["bundled"] is False
        assert any("quintupled" in line for line in res["claim_drift"])
    finally:
        p.write_text(original, encoding="utf-8")
    res = agent.bundle_story("mix", root=root)
    assert res["bundled"] is True and res["self_contained"] is True and res["bytes"] > 0


def test_mcp_command_without_sdk_prints_a_hint(monkeypatch):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "mcp" or name.startswith("mcp."):
            raise ImportError(name)
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    r = CliRunner().invoke(cli, ["mcp"])
    assert r.exit_code == 1
    assert 'pip install "dstory[mcp]"' in r.output
    assert "Traceback" not in r.output


# ---------- the real server, over stdio ----------

def test_mcp_server_end_to_end(tmp_path):
    pytest.importorskip("mcp")
    pytest.importorskip("pandas")
    pytest.importorskip("playwright.sync_api")
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    shutil.copy(MIX, tmp_path / "mix.csv")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from dstory.cli import cli; cli()", "mcp", "--root", str(tmp_path)])
    seen: dict = {}

    async def drive():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                tools = {t.name for t in (await s.list_tools()).tools}
                assert tools >= {"draft_story", "vet_story", "bundle_story", "get_screenshot"}

                r = await s.call_tool("draft_story", {"path": "mix.csv", "title": "Power mix",
                                                      "vendor": True})
                assert not r.isError, r.content
                out = r.structuredContent or json.loads(r.content[0].text)
                out = out.get("result", out)
                seen["draft"] = out

                r = await s.call_tool("vet_story", {"project": "mix"})
                assert not r.isError, r.content
                rep = r.structuredContent or json.loads(r.content[0].text)
                rep = rep.get("result", rep)
                assert rep["passed"] is True, rep["failures"]

                scene = out["scenes"][-1]["id"]
                r = await s.call_tool("get_screenshot", {"project": "mix", "scene": scene})
                assert not r.isError, r.content
                img = r.content[0]
                assert img.type == "image" and img.mimeType == "image/png"
                import base64
                assert base64.b64decode(img.data)[:8] == b"\x89PNG\r\n\x1a\n"

                # An agent breaks a claim; the vet names it.
                p = Path(out["data_json"])
                d = json.loads(p.read_text(encoding="utf-8"))
                d["claims"][0] = dict(d["claims"][0], value=d["claims"][0]["value"] * 7)
                p.write_text(json.dumps(d), encoding="utf-8")
                r = await s.call_tool("vet_story", {"project": "mix", "browser": False})
                rep = r.structuredContent or json.loads(r.content[0].text)
                rep = rep.get("result", rep)
                assert rep["passed"] is False
                assert any(f["claim"] == d["claims"][0]["id"] for f in rep["failures"])

                r = await s.call_tool("draft_story", {"path": "../outside.csv"})
                assert r.isError and "outside the allowed root" in r.content[0].text

    anyio.run(drive)

    # The bundled file works with every network request aborted.
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": 1280, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/*", lambda r: r.continue_() if r.request.url.startswith("file:")
                   else r.abort())
        page.goto(Path(seen["draft"]["html"]).as_uri())
        page.wait_for_timeout(1500)
        for sec in page.locator("section[data-scene]").all():
            sec.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
        painted = page.evaluate("""[...document.querySelectorAll('section[data-scene]')]
            .filter(s => s.querySelector('svg path, svg rect, svg circle, canvas')).length""")
        total = page.locator("section[data-scene]").count()
        b.close()
    assert not errors, errors
    assert total >= 2 and painted == total, (painted, total)
