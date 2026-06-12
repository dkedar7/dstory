"""Bundle a story project into a single self-contained HTML file.

Inlines local CSS/JS, embeds data.json as window.__STORY_DATA__, base64-encodes
referenced images. CDN-hosted assets are left as external references.

This is the Python equivalent of the old `bundle_story.sh` — same regex strategy
but with a tighter, testable interface and a typed result.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .schema import Story


@dataclass
class BundleResult:
    out: Path
    size_bytes: int
    inlined_styles: int
    inlined_scripts: int
    inlined_images: int
    warnings: list[str]


def bundle(slug: str | Path, *, validate: bool = True) -> BundleResult:
    """Bundle <slug>/index.html → <slug>/dist/story.html.

    Args:
        slug: project directory.
        validate: if True (default), validate data.json against the Story schema
                  before bundling and raise on errors.
    """
    project = Path(slug)
    if not project.is_dir():
        raise FileNotFoundError(f"Project directory not found: {project}")

    index = project / "index.html"
    if not index.exists():
        raise FileNotFoundError(f"index.html not found in {project}")

    data_json = project / "data.json"
    if not data_json.exists():
        raise FileNotFoundError(f"data.json not found in {project}")

    if validate:
        raw = json.loads(data_json.read_text(encoding="utf-8"))
        story = Story.model_validate(raw)
        issues = story.validate_dataset_refs()
        if issues:
            raise ValueError(
                "data.json validation issues (fix before bundling):\n  - "
                + "\n  - ".join(issues)
            )

    html = index.read_text(encoding="utf-8")
    warnings: list[str] = []
    counts = {"styles": 0, "scripts": 0, "images": 0}

    # 1. Inline <link rel="stylesheet" href="LOCAL.css">
    def repl_css(m: re.Match) -> str:
        href = m.group("href")
        if _is_remote(href):
            return m.group(0)
        p = (project / href).resolve()
        if not p.exists():
            warnings.append(f"CSS file not found: {href}")
            return m.group(0)
        counts["styles"] += 1
        return _inline_style(p)

    # Two attribute orders for stylesheets
    html = re.sub(
        r'<link\s+[^>]*rel="stylesheet"[^>]*href="(?P<href>[^"]+)"[^>]*/?>',
        repl_css, html, flags=re.IGNORECASE,
    )
    html = re.sub(
        r'<link\s+[^>]*href="(?P<href>[^"]+)"[^>]*rel="stylesheet"[^>]*/?>',
        repl_css, html, flags=re.IGNORECASE,
    )

    # 2. Inline <script src="LOCAL.js"> (and type="module" variants)
    def repl_script(m: re.Match) -> str:
        full = m.group(0)
        src  = m.group("src")
        if _is_remote(src):
            return full
        p = (project / src).resolve()
        if not p.exists():
            warnings.append(f"Script file not found: {src}")
            return full
        counts["scripts"] += 1
        is_module = 'type="module"' in full or "type='module'" in full
        return _inline_script(p, is_module=is_module)

    html = re.sub(
        r'<script\b[^>]*\bsrc="(?P<src>[^"]+)"[^>]*></script>',
        repl_script, html, flags=re.IGNORECASE,
    )

    # 3. Inject data.json on window.__STORY_DATA__ just before </head>
    raw_data = json.loads(data_json.read_text(encoding="utf-8"))
    embed = json.dumps(raw_data, ensure_ascii=False)
    inject = f"<script>window.__STORY_DATA__ = {embed};</script>"
    if "</head>" in html:
        html = html.replace("</head>", f"{inject}\n</head>", 1)
    else:
        html = inject + html

    # 3a. If data.json includes Story.extra_css, append it as a final <style>
    # block so it overrides anything in story.css. This is the supported way
    # to ship custom layout overrides without touching theme/brand CSS.
    extra_css = raw_data.get("extra_css")
    if isinstance(extra_css, str) and extra_css.strip():
        extra_inject = f'<style data-src="story.extra_css">\n{extra_css}\n</style>'
        if "</head>" in html:
            html = html.replace("</head>", f"{extra_inject}\n</head>", 1)
        else:
            html = extra_inject + html

    # 4. Inline <img src="LOCAL.*"> as base64 data URIs
    def repl_img(m: re.Match) -> str:
        pre, src, post = m.group(1), m.group(2), m.group(3)
        if _is_remote(src) or src.startswith("data:"):
            return m.group(0)
        p = (project / src).resolve()
        if not p.exists():
            warnings.append(f"Image file not found: {src}")
            return m.group(0)
        counts["images"] += 1
        return f"{pre}{_data_uri(p)}{post}"

    html = re.sub(
        r'(<img\b[^>]*\bsrc=")([^"]+)(")',
        repl_img, html, flags=re.IGNORECASE,
    )

    # 5. Patch <title> from meta.title (template ships a default placeholder).
    meta = raw_data.get("meta") or {}
    title = meta.get("title")
    if isinstance(title, str) and title.strip():
        from html import escape as _escape
        safe_title = _escape(title.strip())
        html = re.sub(
            r"<title>.*?</title>",
            lambda _m: f"<title>{safe_title}</title>",
            html, count=1, flags=re.S,
        )

    # Write output
    out = project / "dist" / "story.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    size = out.stat().st_size
    if size > 500 * 1024:
        warnings.append(
            f"Bundle is {size/1024:.1f} KB — over 500 KB target. Consider trimming images/data."
        )

    return BundleResult(
        out=out, size_bytes=size,
        inlined_styles=counts["styles"],
        inlined_scripts=counts["scripts"],
        inlined_images=counts["images"],
        warnings=warnings,
    )


# ---------- helpers ----------

def _is_remote(url: str) -> bool:
    return url.startswith(("http://", "https://", "//"))


def _inline_style(p: Path) -> str:
    return f'<style data-src="{p.name}">\n{p.read_text(encoding="utf-8")}\n</style>'


def _inline_script(p: Path, *, is_module: bool) -> str:
    type_attr = ' type="module"' if is_module else ""
    return f'<script{type_attr}>\n{p.read_text(encoding="utf-8")}\n</script>'


def _data_uri(p: Path) -> str:
    mime, _ = mimetypes.guess_type(p.name)
    mime = mime or "application/octet-stream"
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"
