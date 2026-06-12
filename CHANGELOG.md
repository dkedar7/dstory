# Changelog

All notable changes to `dstory` are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## [0.3.1] - 2026-06-02

### Fixed
- **Bundler now sets `<title>` from `meta.title`.** Previously every bundled
  story shipped with the template default `<title>Untitled Story</title>`.
  The title is HTML-escaped before injection.
- **Repaired a corrupted `templates/index.html`** that had accumulated ~1,000
  duplicate `<title>` lines. Collapsed back to the intended 92-line skeleton.
- **Repaired a corrupted `.gitignore`** that had thousands of duplicate
  `.python-version` lines.

### Added
- `LICENSE` file (MIT) — previously declared in `pyproject.toml` and linked
  from the README but missing from the tree.
- Regression tests for the title patch (incl. HTML escaping) and for
  template-skeleton integrity (guards against the duplicate-line corruption
  returning). Suite is now 70 tests.

## [0.3.0]

### Added
- `kind: "custom"` scenes — chrome-free; the renderer owns the entire
  `<section>` mount. For kinetic typography, embedded interactives, and
  full-bleed layouts that the default four-h2-then-mount pattern doesn't fit.
- Per-scene `width` field (`narrow` / `default` / `wide` / `full`).
- Per-scene `chrome` flag (`false` omits the auto-generated h2/p/source).
- `Story.extra_css` — appended as a final `<style>` block at bundle time,
  overriding `story.css`.
- `references/vizzu-chart-gallery.md` documenting 40+ Vizzu chart types.
- `wire_scenes()` / `write_scene()` scaffold helpers and `init(merge=True)`.

### Fixed
- Vetter no longer false-positives on missing `source_line` for chrome-free
  (`bleed` / `custom`) scenes.
- Long-page layout-settle now uses `setTimeout` rather than
  `requestAnimationFrame`, which could starve on very tall pages.
