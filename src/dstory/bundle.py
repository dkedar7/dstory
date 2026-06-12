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


def bundle(slug: str | Path, *, validate: bool = True, vendor: bool = False) -> BundleResult:
    """Bundle <slug>/index.html → <slug>/dist/story.html.

    Args:
        slug: project directory.
        validate: if True (default), validate data.json against the Story schema
                  before bundling and raise on errors.
        vendor: if True, download the CDN-hosted runtime libraries (d3,
                scrollama, Motion) and inline them, so the story works fully
                offline. Vizzu can't be vendored (it fetches WebAssembly at
                runtime); its loader is dropped when the story has no vizzu
                scenes, or kept with a warning when it does. Requires network
                at bundle time; adds ~300 KB.
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

    # 3-pre. Inline a project-local hero image as a data URI so the bundle
    # stays self-contained (story.js reads meta.hero_image at runtime).
    meta = raw_data.get("meta") or {}
    hero_image = meta.get("hero_image")
    if (isinstance(hero_image, str) and hero_image
            and not _is_remote(hero_image) and not hero_image.startswith("data:")):
        p = (project / hero_image).resolve()
        if p.exists():
            meta["hero_image"] = _data_uri(p)
            counts["images"] += 1
        else:
            warnings.append(f"Hero image not found: {hero_image}")

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
    title = meta.get("title")
    if isinstance(title, str) and title.strip():
        from html import escape as _escape
        safe_title = _escape(title.strip())
        html = re.sub(
            r"<title>.*?</title>",
            lambda _m: f"<title>{safe_title}</title>",
            html, count=1, flags=re.S,
        )

    # 6. Patch <html lang dir> from meta (template defaults to lang="en").
    html = _patch_lang_dir(html, lang=meta.get("lang"), dir_=meta.get("dir"))

    # 7. Inject <meta name="description"> + Open Graph / Twitter card tags so
    # shared links unfurl with the story's title and dek instead of nothing.
    social = _social_meta_tags(meta)
    if social and "</head>" in html:
        html = html.replace("</head>", f"{social}\n</head>", 1)

    # 8. Vendor CDN runtime libraries for full offline self-containment.
    if vendor:
        html = _vendor_remote_scripts(html, raw_data, warnings)

    # 9. Anything we inline (<script src>, stylesheet <link>, <img src>) that
    # still points at a local file means the inlining regexes missed it (odd
    # quoting, multiline tag) — the "self-contained" file would silently
    # depend on files that won't ship with it. Warn loudly.
    for ref in _leftover_local_refs(html):
        warnings.append(
            f"Local reference survived bundling: {ref} — the output is NOT "
            "self-contained. Check the tag's quoting/format in index.html."
        )

    # Write output
    out = project / "dist" / "story.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    size = out.stat().st_size
    size_target_kb = 1500 if vendor else 500
    if size > size_target_kb * 1024:
        warnings.append(
            f"Bundle is {size/1024:.1f} KB — over {size_target_kb} KB target. "
            "Consider trimming images/data."
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


def _patch_lang_dir(html: str, *, lang: Optional[str], dir_: Optional[str]) -> str:
    """Set lang (and dir, when not the ltr default) on the <html> root tag."""
    def repl(m: re.Match) -> str:
        tag = m.group(0)
        if isinstance(lang, str) and lang.strip():
            safe = lang.strip()
            if re.search(r'\blang="[^"]*"', tag):
                tag = re.sub(r'\blang="[^"]*"', f'lang="{safe}"', tag)
            else:
                tag = tag[:-1] + f' lang="{safe}">'
        if dir_ in ("rtl", "auto"):
            if re.search(r'\bdir="[^"]*"', tag):
                tag = re.sub(r'\bdir="[^"]*"', f'dir="{dir_}"', tag)
            else:
                tag = tag[:-1] + f' dir="{dir_}">'
        return tag
    return re.sub(r"<html\b[^>]*>", repl, html, count=1)


def _social_meta_tags(meta: dict) -> str:
    """Build description + Open Graph + Twitter card tags from story meta.

    description falls back to deck, then subtitle. share_image must be an
    absolute URL — og:image scrapers don't resolve data URIs.
    """
    from html import escape

    def clean(key: str) -> str:
        v = meta.get(key)
        return v.strip() if isinstance(v, str) else ""

    title  = clean("title")
    desc   = clean("description") or clean("deck") or clean("subtitle")
    author = clean("author")
    image  = clean("share_image")

    tags: list[str] = []
    def tag(attr: str, name: str, content: str) -> None:
        tags.append(f'<meta {attr}="{name}" content="{escape(content, quote=True)}">')

    if desc:   tag("name", "description", desc)
    if author: tag("name", "author", author)
    if title:
        tag("property", "og:title", title)
        tag("name", "twitter:title", title)
    if desc:
        tag("property", "og:description", desc)
        tag("name", "twitter:description", desc)
    if title or desc:
        tag("property", "og:type", "article")
        tag("name", "twitter:card", "summary_large_image" if image else "summary")
    if image:
        tag("property", "og:image", image)
        tag("name", "twitter:image", image)
    return "\n".join(tags)


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


# ---------- vendoring ----------

# Motion is loaded as an ESM module in the template (with a window.MOTION
# bridge); to vendor it we swap in the UMD build and recreate the bridge.
_MOTION_UMD_URL = "https://cdn.jsdelivr.net/npm/motion@10/dist/motion.min.js"
_MOTION_BRIDGE = (
    "window.MOTION = { animate: Motion.animate, stagger: Motion.stagger, "
    "inView: Motion.inView, scroll: Motion.scroll, spring: Motion.spring };\n"
    'window.dispatchEvent(new Event("motion:ready"));'
)


def _fetch(url: str, timeout: float = 30.0) -> str:
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "dstory-bundler"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _vendor_remote_scripts(html: str, raw_data: dict, warnings: list[str]) -> str:
    """Inline CDN-hosted runtime libs so the bundle works offline.

    - UMD <script src="https://..."> tags (d3, scrollama): fetched and inlined.
    - The Motion ESM-bridge module: replaced with the UMD build + bridge.
    - The Vizzu ESM module: can't be vendored (it streams a .wasm at runtime).
      Dropped when the story has no vizzu scenes; kept with a warning when it does.
    """
    # 1. UMD scripts.
    def repl_remote(m: re.Match) -> str:
        url = m.group("src")
        try:
            js = _fetch(url)
        except Exception as e:
            warnings.append(f"Vendor: could not fetch {url} ({e}) — left as CDN reference.")
            return m.group(0)
        return f'<script data-vendored="{url}">\n{js}\n</script>'

    html = re.sub(
        r'<script\b[^>]*\bsrc="(?P<src>https?://[^"]+)"[^>]*></script>',
        repl_remote, html, flags=re.IGNORECASE,
    )

    # 2. Module blocks. Find each <script type="module">…</script> and decide
    # by its import URL.
    module_blocks = re.findall(r'<script\s+type="module">[\s\S]*?</script>', html)
    has_vizzu_scenes = any(
        s.get("kind") == "vizzu" for s in raw_data.get("scenes", [])
    )
    for block in module_blocks:
        if "/npm/motion@" in block:
            try:
                js = _fetch(_MOTION_UMD_URL)
                replacement = (
                    f'<script data-vendored="{_MOTION_UMD_URL}">\n{js}\n</script>\n'
                    f"<script>\n{_MOTION_BRIDGE}\n</script>"
                )
                html = html.replace(block, replacement, 1)
            except Exception as e:
                warnings.append(
                    f"Vendor: could not fetch Motion UMD build ({e}) — left as CDN module."
                )
        elif "vizzu" in block.lower():
            if has_vizzu_scenes:
                warnings.append(
                    "Vendor: Vizzu can't be inlined (it loads WebAssembly at runtime) — "
                    "vizzu scenes still need network access."
                )
            else:
                html = html.replace(block, "", 1)

    return html


def _leftover_local_refs(html: str) -> list[str]:
    """Local file references in tags the bundler should have inlined.

    Matches both quote styles deliberately — the inlining regexes only handle
    double quotes, so a single-quoted attribute is exactly the case this
    safety net exists to catch.
    """
    refs: list[str] = []
    for pattern in (
        r'<script\b[^>]*\bsrc=(["\'])(?P<ref>[^"\']+)\1',
        r'<link\b[^>]*\brel=(["\'])stylesheet\1[^>]*\bhref=(["\'])(?P<ref>[^"\']+)\2',
        r'<link\b[^>]*\bhref=(["\'])(?P<ref>[^"\']+)\1[^>]*\brel=(["\'])stylesheet\3',
        r'<img\b[^>]*\bsrc=(["\'])(?P<ref>[^"\']+)\1',
    ):
        for m in re.finditer(pattern, html, flags=re.IGNORECASE):
            ref = m.group("ref")
            if not _is_remote(ref) and not ref.startswith(("data:", "#")):
                refs.append(ref)
    return sorted(set(refs))
