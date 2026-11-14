"""Scaffold a new story project from the bundled template + a Brand."""

from __future__ import annotations

import json
import re
import shutil
from importlib.resources import as_file, files
from pathlib import Path
from typing import Optional

from .brand import Brand
from .schema import Audience, Mode


PACKAGE_TEMPLATES = "dstory.templates"


def _copy_templates(dest: Path) -> None:
    """Copy the bundled templates directory into `dest`.

    Walks the package data via Traversable.iterdir(), copying each file. Works
    whether the package is installed normally, extracted from a wheel/zip, or
    namespaced across multiple roots (MultiplexedPath).
    """
    src_root = files(PACKAGE_TEMPLATES)

    def _walk(node, rel: Path) -> None:
        for child in node.iterdir():
            child_rel = rel / child.name
            if child.is_dir():
                (dest / child_rel).mkdir(parents=True, exist_ok=True)
                _walk(child, child_rel)
            elif child.is_file():
                target = dest / child_rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(child.read_bytes())

    dest.mkdir(parents=True, exist_ok=True)
    _walk(src_root, Path("."))


def _patch_html_attrs(html: str, *, theme: str, audience: str) -> str:
    """Set data-theme and data-audience on the <html> root."""
    html = re.sub(r'data-theme="[^"]*"',    f'data-theme="{theme}"', html)
    html = re.sub(r'data-audience="[^"]*"', f'data-audience="{audience}"', html)
    return html


def _patch_html_google_fonts(html: str, brand: Brand) -> str:
    """Replace the bundled <link href='...fonts.googleapis.com...'> with the
    brand's google_fonts URL (or remove the link if the brand opts out)."""
    url = brand.google_fonts_url()
    pattern = r'<link\s+href="https://fonts\.googleapis\.com[^"]*"\s+rel="stylesheet">'
    if url is None:
        return re.sub(pattern, "", html)
    return re.sub(pattern, f'<link href="{url}" rel="stylesheet">', html)


_DSTORY_SCENES_SENTINEL = "<!-- DSTORY:SCENES"


def wire_scenes(slug: str | Path, scene_ids: list[str]) -> None:
    """Patch index.html to load each scene script via a `<script defer>` tag.

    Looks for the `<!-- DSTORY:SCENES ... -->` sentinel left by the scaffold
    and replaces it with `<script src="scenes/<id>.js" defer></script>` tags.
    If the sentinel was already replaced, locates the existing block of scene
    tags (right after `<script src="story.js">`) and rewrites them.

    Idempotent — same scene_ids → same output.
    Defensive against HTML comments — strips them first so commented-out
    `<script>` examples aren't mistaken for live tags.
    """
    project = Path(slug)
    index = project / "index.html"
    if not index.exists():
        raise FileNotFoundError(f"index.html not found in {project}")

    html = index.read_text(encoding="utf-8")
    new_tags = "\n  ".join(
        f'<script src="scenes/{sid}.js" defer></script>' for sid in scene_ids
    )

    # 1. If the sentinel is present, replace it.
    if _DSTORY_SCENES_SENTINEL in html:
        # The sentinel is a single-line HTML comment; replace it with new tags.
        new_html, n = re.subn(
            r"<!-- DSTORY:SCENES[^>]*-->",
            new_tags, html, count=1,
        )
        if n > 0:
            index.write_text(new_html, encoding="utf-8")
            return

    # 2. Sentinel is gone — strip existing scene tags (only LIVE ones, not commented),
    # then re-insert. To skip commented tags, temporarily strip HTML comments before matching.
    comments: list[str] = []
    placeholder = "\x00DSTORY_COMMENT_{idx}\x00"
    def stash_comment(m: re.Match) -> str:
        comments.append(m.group(0))
        return placeholder.format(idx=len(comments) - 1)
    html_no_comments = re.sub(r"<!--[\s\S]*?-->", stash_comment, html)

    # Strip live scene tags
    html_no_comments = re.sub(
        r'\s*<script\s+src="scenes/[^"]+\.js"\s+defer></script>',
        "", html_no_comments,
    )

    # Insert new tags after the story.js script tag, OR before </body>.
    if '<script src="story.js" defer></script>' in html_no_comments:
        html_no_comments = html_no_comments.replace(
            '<script src="story.js" defer></script>',
            f'<script src="story.js" defer></script>\n  {new_tags}',
            1,
        )
    else:
        html_no_comments = html_no_comments.replace(
            "</body>", f"  {new_tags}\n</body>", 1,
        )

    # Restore comments
    def restore(m: re.Match) -> str:
        return comments[int(m.group(1))]
    new_html = re.sub(r"\x00DSTORY_COMMENT_(\d+)\x00", restore, html_no_comments)

    index.write_text(new_html, encoding="utf-8")


def write_scene(slug: str | Path, scene_id: str, js_source: str, *, wire: bool = True) -> Path:
    """Write a scene JS file to <slug>/scenes/<scene_id>.js and (by default) wire it.

    The wire step is idempotent — re-calling write_scene with the same id replaces
    the file but doesn't duplicate the script tag in index.html.
    """
    project = Path(slug)
    scenes_dir = project / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    target = scenes_dir / f"{scene_id}.js"
    target.write_text(js_source, encoding="utf-8")

    if wire:
        # Re-wire to include this scene id (preserve any existing wired ids).
        # Strip HTML comments first so commented-out example tags don't count.
        index = (project / "index.html").read_text(encoding="utf-8")
        index_no_comments = re.sub(r"<!--[\s\S]*?-->", "", index)
        existing = re.findall(
            r'<script\s+src="scenes/([^"]+)\.js"\s+defer></script>',
            index_no_comments,
        )
        ids = list(dict.fromkeys(existing + [scene_id]))  # de-dupe, keep order
        wire_scenes(project, ids)

    return target


def init(
    slug: str | Path,
    *,
    brand: Brand | str = "editorial-noir",
    audience: Audience = "general-public",
    mode: Mode = "scroll",
    title: str = "Untitled Story",
    overwrite: bool = False,
    merge: bool = False,
) -> Path:
    """Scaffold a new story project.

    Args:
        slug: directory name (or path) to create.
        brand: a Brand instance OR a preset name (e.g., "editorial-noir").
        audience: drives commentary density / chart complexity hints.
        mode: "scroll" (default) or "slides".
        title: starter title written into data.json's meta.
        overwrite: if False (default), refuse to write into a non-empty dir
                   (unless `merge=True`).
        merge: if True, preserve user-authored scenes/, data.json, and any
               wired scene tags in index.html — only refresh the framework
               files (story.js, story.css, theme.css, template index sections).
               Useful for upgrading to a new dstory version without re-authoring.

    Returns:
        The created project directory path.
    """
    dest = Path(slug)
    is_existing_non_empty = dest.exists() and any(dest.iterdir())
    if is_existing_non_empty and not (overwrite or merge):
        raise FileExistsError(
            f"{dest} exists and is not empty (pass overwrite=True or merge=True)."
        )
    dest.mkdir(parents=True, exist_ok=True)

    # In merge mode, save the user's scenes/, data.json, and any wired scene tags
    # before re-copying templates, then restore them.
    saved_scenes_dir: Path | None = None
    saved_data: bytes | None = None
    saved_scene_ids: list[str] = []
    if merge and is_existing_non_empty:
        scenes_dir = dest / "scenes"
        if scenes_dir.exists():
            import tempfile
            tmp = tempfile.mkdtemp(prefix="dstory-merge-")
            saved_scenes_dir = Path(tmp) / "scenes"
            shutil.copytree(scenes_dir, saved_scenes_dir)
        if (dest / "data.json").exists():
            saved_data = (dest / "data.json").read_bytes()
        if (dest / "index.html").exists():
            existing_html = (dest / "index.html").read_text(encoding="utf-8")
            saved_scene_ids = re.findall(
                r'<script\s+src="scenes/([^"]+)\.js"\s+defer></script>',
                existing_html,
            )

    if isinstance(brand, str):
        brand = Brand.from_preset(brand)

    # 1. Copy templates
    _copy_templates(dest)

    # 2. Write theme.css from brand
    (dest / "theme.css").write_text(brand.css(), encoding="utf-8")

    # 3. Patch index.html (theme + audience attrs, google fonts URL)
    index_path = dest / "index.html"
    html = index_path.read_text(encoding="utf-8")
    theme_slug = _slugify(brand.name) if brand.name else "custom"
    html = _patch_html_attrs(html, theme=theme_slug, audience=audience)
    html = _patch_html_google_fonts(html, brand)

    # If brand has a wordmark, inline it as a base64 data URI in the hero (optional).
    if brand.wordmark and brand.wordmark.exists():
        html = _inject_wordmark(html, brand.wordmark)

    # If brand has a favicon, inline it as a data-URI <link rel="icon">.
    if brand.favicon and brand.favicon.exists():
        html = _inject_favicon(html, brand.favicon)

    # If brand has extra_css, append to story.css (won't reorder tokens)
    if brand.extra_css and brand.extra_css.exists():
        story_css_path = dest / "story.css"
        story_css = story_css_path.read_text(encoding="utf-8")
        extra = brand.extra_css.read_text(encoding="utf-8")
        story_css_path.write_text(
            story_css + f"\n\n/* --- brand extras: {brand.extra_css.name} --- */\n" + extra,
            encoding="utf-8",
        )

    index_path.write_text(html, encoding="utf-8")

    # 4. Write data.json skeleton
    data = {
        "meta": {
            "title": title,
            "subtitle": "",
            "deck": "",
            "author": "",
            "published": "",
            "theme": theme_slug,
            "audience": audience,
            "mode": mode,
            "sources": [],
        },
        "claims": [],
        "scenes": [],
        "datasets": {},
    }
    (dest / "data.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # 5. Make output dirs
    (dest / "dist").mkdir(exist_ok=True)
    (dest / "vetting" / "screenshots").mkdir(parents=True, exist_ok=True)

    # 6. Merge mode: restore the user's data.json + scenes/ + re-wire scenes
    if merge:
        if saved_data is not None:
            (dest / "data.json").write_bytes(saved_data)
        if saved_scenes_dir is not None:
            scenes_target = dest / "scenes"
            if scenes_target.exists():
                shutil.rmtree(scenes_target)
            shutil.copytree(saved_scenes_dir, scenes_target)
            shutil.rmtree(saved_scenes_dir.parent)  # cleanup tempdir
        if saved_scene_ids:
            wire_scenes(dest, saved_scene_ids)

    return dest


def project_theme(project: str | Path) -> str | None:
    """The theme a project currently looks like: index.html's data-theme."""
    index = Path(project) / "index.html"
    if not index.exists():
        return None
    m = re.search(r'<html\b[^>]*\bdata-theme="([^"]*)"', index.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def theme_css_is_pristine(project: str | Path) -> bool:
    """True when theme.css is exactly what its preset generates (nobody has
    edited it, and it did not come from a brand TOML)."""
    from .brand import list_presets
    project = Path(project)
    current = project_theme(project)
    css = project / "theme.css"
    if current not in list_presets() or not css.exists():
        return False
    norm = lambda t: t.replace("\r\n", "\n").strip()  # noqa: E731
    return norm(css.read_text(encoding="utf-8")) == norm(Brand.from_preset(current).css())


def apply_theme(project: str | Path, brand: Brand | str, *, update_data: bool = True) -> str:
    """Re-theme an existing project: rewrite theme.css, the <html data-theme>
    attribute and the web-font link from a preset name or Brand. With
    update_data, meta.theme in data.json is set to match. Returns the slug.

    Scenes, data and story.css are left alone (a brand's extra_css or
    wordmark is not re-applied; re-run init(..., merge=True) for those)."""
    project = Path(project)
    if isinstance(brand, str):
        brand = Brand.from_preset(brand)
    slug = _slugify(brand.name) if brand.name else "custom"
    (project / "theme.css").write_text(brand.css(), encoding="utf-8")
    index = project / "index.html"
    html = index.read_text(encoding="utf-8")
    html = re.sub(r'data-theme="[^"]*"', f'data-theme="{slug}"', html, count=1)
    html = _patch_html_google_fonts(html, brand)
    index.write_text(html, encoding="utf-8")
    data_path = project / "data.json"
    if update_data and data_path.exists():
        data = json.loads(data_path.read_text(encoding="utf-8"))
        data.setdefault("meta", {})["theme"] = slug
        data_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return slug


# ---------- keeping a project's runtime current ----------
#
# `init` copies story.js and story.css into the project, so a fix to either
# never reached a project made with an older dstory. These helpers tell an
# untouched copy from an older release (safe to refresh) from one the author
# edited (kept unless forced, and then backed up first).

RUNTIME_FILES = ("story.js", "story.css")
_BRAND_EXTRAS = "/* --- brand extras:"


def _runtime_hash(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()[:16]


def _split_brand_extras(css: str) -> tuple[str, str]:
    """story.css may end with a brand's extra_css block; split it off."""
    css = css.replace("\r\n", "\n")
    i = css.find(_BRAND_EXTRAS)
    if i < 0:
        return css, ""
    base = css[:i]
    if base.endswith("\n\n"):
        base = base[:-2]
    return base, "\n\n" + css[i:]


def _packaged_runtime(name: str) -> str:
    return (files(PACKAGE_TEMPLATES) / name).read_text(encoding="utf-8")


def runtime_status(project: str | Path) -> dict[str, str]:
    """For each runtime file: "current", "stale" (an untouched copy from an
    older dstory release), "edited" (matches no release) or "missing"."""
    from ._runtime_history import KNOWN
    project = Path(project)
    out: dict[str, str] = {}
    for name in RUNTIME_FILES:
        path = project / name
        if not path.exists():
            out[name] = "missing"
            continue
        text = path.read_text(encoding="utf-8")
        if name == "story.css":
            text = _split_brand_extras(text)[0]
        h = _runtime_hash(text)
        if h == _runtime_hash(_packaged_runtime(name)):
            out[name] = "current"
        elif h in KNOWN.get(name, ()):
            out[name] = "stale"
        else:
            out[name] = "edited"
    return out


def upgrade_runtime(project: str | Path, *, force: bool = False,
                    restore_missing: bool = True) -> list[str]:
    """Bring a project's story.js / story.css up to this dstory version.

    Untouched copies from older releases are replaced (story.css keeps any
    brand extras appended to it). Edited files are kept and reported, unless
    `force`, which first saves them to .dstory-backup/. Returns one note per
    file changed or kept."""
    import time
    project = Path(project)
    notes: list[str] = []
    for name, state in runtime_status(project).items():
        if state == "current" or (state == "missing" and not restore_missing):
            continue
        path = project / name
        if state == "edited" and not force:
            notes.append(f"{name} was edited, so it was kept at its old version. "
                         f"Run `dstory upgrade {project.name} --force` to replace it "
                         "(your copy is backed up first).")
            continue
        new = _packaged_runtime(name)
        if state in ("edited", "stale") and name == "story.css":
            new += _split_brand_extras(path.read_text(encoding="utf-8"))[1]
        if state == "edited":
            backup = project / ".dstory-backup" / f"{name}.{time.strftime('%Y%m%d-%H%M%S')}"
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
            notes.append(f"Replaced edited {name}; your copy is in "
                         f"{backup.relative_to(project).as_posix()}.")
        elif state == "stale":
            notes.append(f"Updated {name} to this dstory version.")
        else:
            notes.append(f"Restored missing {name}.")
        path.write_text(new, encoding="utf-8")
    return notes


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _file_data_uri(path: Path, default_mime: str = "application/octet-stream") -> str:
    import base64, mimetypes
    mime, _ = mimetypes.guess_type(path.name)
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime or default_mime};base64,{data}"


def _inject_favicon(html: str, favicon_path: Path) -> str:
    """Inline a favicon as a data-URI <link rel="icon"> — no extra file to ship."""
    uri = _file_data_uri(favicon_path, default_mime="image/png")
    link = f'<link rel="icon" href="{uri}">'
    return html.replace("</head>", f"  {link}\n</head>", 1)


def _inject_wordmark(html: str, wordmark_path: Path) -> str:
    """Inline an SVG/PNG wordmark into the hero as a data URI, top-right."""
    uri = _file_data_uri(wordmark_path, default_mime="image/svg+xml")
    snippet = (
        f'<img class="hero__wordmark" alt="" '
        f'src="{uri}" '
        f'style="position:absolute;top:1.5rem;right:1.5rem;height:32px;opacity:0.85;z-index:2">'
    )
    # Inject immediately after .hero opening tag
    return re.sub(r'(<header\s+class="hero"[^>]*>)', r'\1\n      ' + snippet, html, count=1)


# ---------- starter scene stubs ----------

_STARTER_SIMPLE = '''\
// scenes/{id}.js — kind: "simple". Draw once into the mount.
window.STORY.register("{id}", (mount, data, scene) => {{
  const records = data.datasets[scene.dataset] || [];
  const w = mount.clientWidth, h = Math.max(mount.clientHeight, 300);
  const svg = d3.select(mount).append("svg")
    .attr("viewBox", `0 0 ${{w}} ${{h}}`)
    .attr("width", "100%").attr("height", h);
  // TODO: draw the chart. Theme tokens: var(--accent), var(--cat-1)..--cat-7,
  // var(--ink-soft) etc. Use the .annotation class for callout text.
}});
'''

_STARTER_SCROLLY = '''\
// scenes/{id}.js — kind: "scrolly". Sticky chart, morph on each step.
window.STORY.register("{id}", (mount, data, scene) => {{
  const records = data.datasets[scene.dataset] || [];
  const w = mount.clientWidth, h = mount.clientHeight;
  const svg = d3.select(mount).append("svg")
    .attr("viewBox", `0 0 ${{w}} ${{h}}`)
    .attr("width", "100%").attr("height", "100%");
  // TODO: initial draw.
  return {{
    onStep(i, direction) {{
      // TODO: morph the chart for step i (matches scene.steps[i] in data.json).
    }},
  }};
}});
'''

_STARTER_PINNED = '''\
// scenes/{id}.js — kind: "pinned". One pinned object, driven by scroll progress 0..1.
window.STORY.register("{id}", (mount, data, scene) => {{
  // TODO: initial draw into `mount`.
  return {{
    onProgress(p) {{
      // TODO: transform the visual as p goes 0 → 1 (slides mode shows p=1).
    }},
  }};
}});
'''

_STARTER_BLEED = '''\
// scenes/{id}.js — kind: "bleed". Full-viewport background; headline text is
// rendered by the framework from scene.headline / scene.commentary.
window.STORY.register("{id}", (mount, data, scene) => {{
  // TODO: paint the cinematic backdrop into `mount` (canvas, SVG, gradient...).
}});
'''

_STARTER_CUSTOM = '''\
// scenes/{id}.js — kind: "custom". Chrome-free: you own the entire <section>.
window.STORY.register("{id}", (mount, data, scene) => {{
  // `mount` IS the <section>. Build any layout; read scene.headline /
  // scene.commentary / scene.source_line yourself if you want them shown.
}});
'''

_STARTER_VIZZU = '''\
// scenes/{id}.js — kind: "vizzu".
// NOTE: vizzu scenes are fully declarative: define `series` and `frames[]`
// in data.json and you need no JS file at all (`dstory scene --kind vizzu`
// no longer writes one). Registering a renderer here REPLACES the built-in
// Vizzu renderer, so an empty function leaves the chart blank. To remove this
// file, delete it; `dstory bundle` drops its dangling <script> tag.
window.STORY.register("{id}", (mount, data, scene) => {{
  // TODO: drive your own Vizzu instance, or delete this file.
}});
'''

_STARTERS: dict[str, str] = {
    "simple":  _STARTER_SIMPLE,
    "scrolly": _STARTER_SCROLLY,
    "pinned":  _STARTER_PINNED,
    "bleed":   _STARTER_BLEED,
    "custom":  _STARTER_CUSTOM,
    "vizzu":   _STARTER_VIZZU,
}


def starter_scene_js(scene_id: str, kind: str = "simple") -> str:
    """Return a starter scene script for `kind`, ready for write_scene().

    Each stub registers a renderer with the correct contract for its kind
    (scrolly returns onStep, pinned returns onProgress, ...).
    """
    if kind not in _STARTERS:
        raise ValueError(f"Unknown scene kind {kind!r}. One of: {sorted(_STARTERS)}")
    return _STARTERS[kind].format(id=scene_id)
