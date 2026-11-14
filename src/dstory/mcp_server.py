"""`dstory mcp`: dstory as an MCP server over stdio (#21, milestone 1).

An AI assistant drafts a story from a data file, vets it, looks at it and
bundles it, and gets structured results back: which claim drifted, which
dimension failed, and a screenshot it can see. The tools are thin wrappers
over dstory.agent; this module only adds the transport. Needs the [mcp] extra.
"""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from typing import Any, Optional

from . import agent

try:  # the [mcp] extra; module-level so FastMCP can resolve the tool annotations
    from mcp.server.fastmcp import FastMCP, Image
except ImportError:  # pragma: no cover - `dstory mcp` prints an install hint
    FastMCP = Image = None

INSTRUCTIONS = """\
dstory turns a data file into a single, self-contained HTML data story whose
numbers are checked against the data. Typical loop: draft_story on the user's
file -> read `vet.failures` -> get_screenshot to look at a scene -> edit the
project's data.json (headlines, commentary, claims) -> bundle_story ->
vet_story until `passed` is true. Never hand back a story whose vet failed.
"""


def _quiet(fn, *args, **kwargs):
    """Run fn with stdout sent to stderr: stdout is the MCP channel."""
    with contextlib.redirect_stdout(sys.stderr):
        return fn(*args, **kwargs)


def make_server(root: str | Path = "."):
    if FastMCP is None:
        raise ImportError('dstory mcp needs the MCP SDK: pip install "dstory[mcp]"')

    root = Path(root).resolve()
    server = FastMCP("dstory", instructions=INSTRUCTIONS)

    @server.tool()
    def draft_story(path: str, title: Optional[str] = None, theme: Optional[str] = None,
                    mode: str = "scroll", out: Optional[str] = None,
                    source: Optional[str] = None, vendor: bool = False,
                    opener: bool = True) -> dict[str, Any]:
        """Draft a vetted data story from a data file (CSV, TSV, JSON, Parquet, Excel).

        Picks the charts, writes headlines and alt text from the data, bundles one
        self-contained HTML file and vets it. Returns the project directory, the
        HTML path, the scenes, the claims (each number the prose states, tied to
        the data), a plain-English explanation of every choice, and the vet report.
        `path` and `out` are relative to the server root. mode: "scroll" or
        "slides". vendor=True inlines the runtime libraries so the file works offline.
        """
        return _quiet(agent.draft_story, path, root=root, out=out, title=title, theme=theme,
                      mode=mode, source=source, vendor=vendor, opener=opener)

    @server.tool()
    def vet_story(project: str, browser: bool = True) -> dict[str, Any]:
        """Vet a project's bundled story (dist/story.html) on five dimensions:
        renders, data fidelity, editorial integrity, visual quality, accessibility.

        Returns {passed, complete, failures: [{dimension, message, claim, scene}],
        dimensions: [...]}, the same JSON as `dstory vet --json`. browser=False
        runs only the static checks (fast; renders and visual are skipped).
        """
        return _quiet(agent.vet_story, project, root=root, browser=None if browser else False)

    @server.tool()
    def bundle_story(project: str, vendor: bool = False) -> dict[str, Any]:
        """Bundle a project's index.html + data.json into dist/story.html after
        you edit data.json. If a claim contradicts its value, nothing is written
        and the result lists the drift ({"bundled": false, "claim_drift": [...]})."""
        return _quiet(agent.bundle_story, project, root=root, vendor=vendor)

    @server.tool()
    def get_screenshot(project: str, scene: Optional[str] = None,
                       width: int = 1440, height: int = 900) -> Image:
        """A PNG of the bundled story as a reader sees it: the first screen, or the
        named scene (its id, e.g. "scene-shift") scrolled into view. Use a width
        of 390 to check the phone layout."""
        png = _quiet(agent.get_screenshot, project, root=root, scene=scene,
                     width=width, height=height)
        return Image(data=png, format="png")

    return server


def _preload() -> None:
    """Import the heavy optional modules before the server starts.

    Imported lazily inside a tool call, numpy's extension module can stall on
    Windows once the stdio transport's threads are running; loading it up
    front also makes the first draft_story call faster."""
    for name in ("pandas", "playwright.sync_api"):
        try:
            __import__(name)
        except ImportError:
            pass
    from . import api, draft, vet  # noqa: F401


def run(root: str | Path = ".") -> None:
    _preload()
    make_server(root).run()
