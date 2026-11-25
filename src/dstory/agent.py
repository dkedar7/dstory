"""Structured, JSON-friendly operations for AI assistants (#21).

These are the functions behind `dstory mcp`. They take plain arguments and
return plain dicts, so the transport (MCP today) stays swappable and every
tool can be tested without a server. Every path is confined to a root
directory (the server's `--root`, default the current directory): an agent
cannot read or write outside it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

READERS = {".csv": "read_csv", ".tsv": "read_csv", ".txt": "read_csv", ".json": "read_json",
           ".parquet": "read_parquet", ".xlsx": "read_excel", ".xls": "read_excel"}


class AgentError(ValueError):
    """A request the tool cannot carry out; the message says what to change."""


def resolve(path: str | Path, root: str | Path) -> Path:
    """`path` (absolute, or relative to `root`) as an absolute path inside root."""
    root_p = Path(root).resolve()
    p = Path(path)
    p = (p if p.is_absolute() else root_p / p).resolve()
    if p != root_p and root_p not in p.parents:
        raise AgentError(f"{path} is outside the allowed root {root_p}. Use a path inside it, "
                         "or start the server with a wider --root.")
    return p


def _project(project: str | Path, root: str | Path) -> Path:
    p = resolve(project, root)
    if not (p / "data.json").is_file() or not (p / "index.html").is_file():
        raise AgentError(f"{p} is not a dstory project (no index.html and data.json). "
                         "Create one with draft_story first.")
    return p


def _scene_summary(story: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for s in story.get("scenes", []):
        if isinstance(s, dict):
            out.append({k: s.get(k) for k in ("id", "kind", "headline", "dataset", "alt")
                        if s.get(k) is not None})
    return out


def draft_story(path: str, *, root: str | Path = ".", out: Optional[str] = None,
                title: Optional[str] = None, theme: Optional[str] = None,
                mode: str = "scroll", audience: str = "general-public",
                source: Optional[str] = None, max_scenes: int = 5,
                vendor: bool = False, opener: bool = True,
                browser: Optional[bool] = None) -> dict[str, Any]:
    """Draft, bundle and vet a story from a data file, like `dstory draft`."""
    try:
        import pandas as pd
    except ImportError as e:  # pragma: no cover - the [mcp] extra pulls in [prep]
        raise AgentError('draft_story needs pandas: pip install "dstory[prep]"') from e
    from .api import build
    from .draft import draft

    src = resolve(path, root)
    if not src.is_file():
        raise AgentError(f"No such data file: {src}")
    reader = READERS.get(src.suffix.lower())
    if reader is None:
        raise AgentError(f"Unsupported file type {src.suffix!r}. Use one of: "
                         f"{', '.join(sorted(READERS))}.")
    kwargs = {"sep": "\t"} if src.suffix.lower() == ".tsv" else {}
    try:
        df = getattr(pd, reader)(src, **kwargs)
    except Exception as e:  # pandas raises many types; pass the message on
        raise AgentError(f"Could not read {src.name}: {e}") from e

    target = resolve(out or src.stem.lower().replace(" ", "-"), root)
    if title is None:
        title = src.stem.replace("_", " ").replace("-", " ").strip().capitalize() or "Untitled story"
    d = draft(df, title=title, theme=theme, audience=audience, mode=mode,
              max_scenes=max_scenes, source=source, opener=opener and not vendor)
    result = build(d.story, target, scenes=d.scenes, vendor=vendor, vet=True,
                   browser=browser, overwrite=True)
    return {
        "project": str(target),
        "html": str(result.html),
        "data_json": str(target / "data.json"),
        "scenes": _scene_summary(d.story),
        "claims": d.story.get("claims", []),
        "explain": d.explain(),
        "vet": result.report.to_json() if result.report else None,
    }


def vet_story(project: str, *, root: str | Path = ".",
              browser: Optional[bool] = None) -> dict[str, Any]:
    """Vet a project's bundled story. Same JSON as `dstory vet --json`."""
    from .vet import vet

    p = _project(project, root)
    html = p / "dist" / "story.html"
    if not html.is_file():
        raise AgentError(f"{html} does not exist yet. Run bundle_story first.")
    return vet(html, data=p / "data.json", browser=browser).to_json()


def bundle_story(project: str, *, root: str | Path = ".", vendor: bool = False) -> dict[str, Any]:
    """Bundle a project into dist/story.html, like `dstory bundle`.

    A claim that contradicts its value stops the bundle; the error comes back
    as `{"bundled": false, "claim_drift": [...]}` rather than an exception, so
    an agent can read which claim drifted and fix it."""
    from .bundle import ClaimDriftError, bundle

    p = _project(project, root)
    try:
        r = bundle(p, vendor=vendor, root=Path(root).resolve())
    except ClaimDriftError as e:
        lines = [ln.strip()[2:] for ln in str(e).splitlines() if ln.strip().startswith("- ")]
        return {"bundled": False, "claim_drift": lines, "message": str(e).splitlines()[0]}
    return {"bundled": True, "html": str(r.out), "bytes": r.size_bytes,
            "self_contained": r.self_contained, "warnings": list(r.warnings)}


def _screenshot(html: Path, scene: Optional[str], width: int, height: int) -> bytes:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(html.as_uri(), wait_until="load")
            page.wait_for_timeout(600)
            if scene is None:
                return page.screenshot(full_page=False)
            loc = page.locator(f'section[data-scene="{scene}"]')
            if loc.count() == 0:
                ids = page.evaluate(
                    "[...document.querySelectorAll('section[data-scene]')].map(s => s.dataset.scene)")
                raise AgentError(f"No scene {scene!r} in the story. Scenes: {', '.join(ids)}.")
            if page.evaluate("document.body.classList.contains('story-mode--slides')"):
                # Slides: step forward until the scene is the active slide.
                for _ in range(60):
                    if loc.first.is_visible():
                        break
                    page.keyboard.press("ArrowRight")
                    page.wait_for_timeout(250)
            loc.first.scroll_into_view_if_needed()
            page.wait_for_timeout(1200)          # let the chart's entrance finish
            return page.screenshot(full_page=False)
        finally:
            browser.close()


def get_screenshot(project: str, *, root: str | Path = ".", scene: Optional[str] = None,
                   width: int = 1440, height: int = 900) -> bytes:
    """A PNG of the bundled story as a reader sees it: the first screen, or
    the named scene scrolled into view."""
    from .vet import _off_event_loop, browser_available

    p = _project(project, root)
    html = p / "dist" / "story.html"
    if not html.is_file():
        raise AgentError(f"{html} does not exist yet. Run bundle_story first.")
    ok, why = browser_available()
    if not ok:
        raise AgentError(f"No browser for screenshots ({why}). Run: playwright install chromium")
    return _off_event_loop(_screenshot, html, scene, int(width), int(height))


def as_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)
