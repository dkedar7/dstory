# dstory

> Turn DataFrames into NYT-style scrollytelling and slide-deck data stories — one self-contained HTML file you can email, host, or present. Pure Python in, no JavaScript required.

**[📖 Documentation](https://dkedar7.github.io/dstory/)** ·
**[▶ Live demo: *Ctrl-Alt-Reinvent — Microsoft, 1975–2025*](https://dkedar7.github.io/dstory/demo/)** — a 40-scene data essay built with dstory ·
**[▶ Cookbook gallery](https://dkedar7.github.io/dstory/gallery/)** — the chart recipes, rendered ·
**[▶ Theme showcase](https://dkedar7.github.io/dstory/themes/)** — same story, eight personalities ·
**[▶ Morph showcase](https://dkedar7.github.io/dstory/morphs/)** — bars curl into pies, live, zero JS

`dstory` is the deterministic infrastructure for data stories: a one-call builder, a single-file bundler, a 5-dimension vetter (renders / data fidelity / editorial integrity / visual / a11y), a brand system for your colors and typography, and pydantic schemas that surface authoring bugs at build time instead of delivery time.

## Who is this for?

- **Python data scientists (no JS):** animated chart sequences via declarative [Vizzu](#vizzu-scenes-no-javascript) scenes, plus a [cookbook](#the-cookbook) of finished D3 charts you copy and own. DataFrame → story.html in one notebook cell.
- **Authors comfortable with D3:** full creative control — scenes are plain JS files you write; dstory does everything else and stays out of your chart code.
- **AI-assisted authoring:** dstory is the substrate the companion **data-storytelling** Claude skill builds on — the agent writes the bespoke D3; the vetter gates what ships.

## Status

Alpha — under active development. API may change before 1.0.

## Install

```bash
pip install dstory                     # core: schema + brand + scaffold + bundle
pip install "dstory[vet]"              # adds Playwright for browser-driven vetting
pip install "dstory[prep]"             # adds pandas for data-prep helpers
pip install "dstory[all]"              # everything

# After installing the [vet] extra, install Chromium:
playwright install chromium
```

## Quick start: notebook, zero JavaScript

One cell, DataFrame to shippable HTML:

```python
import pandas as pd
from dstory import build
from dstory.prep import to_long

df = pd.DataFrame({
    "month":   ["Jan", "Feb", "Mar", "Apr"],
    "Signups": [1000, 1500, 2900, 3400],
    "Churn":   [200, 240, 250, 260],
})

result = build({
    "meta": {"title": "Q1 Growth", "theme": "scientific-bright"},
    "scenes": [{
        "id": "scene-growth", "kind": "vizzu", "dataset": "metrics",
        "alt": "Animated bar-to-line sequence: signups more than tripled while churn stayed flat.",
        "series": [
            {"name": "month", "type": "dimension"},
            {"name": "variable", "type": "dimension"},
            {"name": "value", "type": "measure"},
        ],
        "frames": [
            {"headline": "Signups took off in March",
             "config": {"channels": {"x": "month", "y": "value", "color": "variable"},
                        "geometry": "rectangle"}},
            {"headline": "While churn barely moved",
             "config": {"channels": {"x": "month", "y": "value", "color": "variable"},
                        "geometry": "line"}},
        ],
    }],
    "datasets": {"metrics": to_long(df, id_vars="month")},
}, "q1-growth", vet=True)

result.html    # → q1-growth/dist/story.html — open it, scroll, the chart morphs
result.passed  # → True (the 5-dimension vet report)
```

`kind: "vizzu"` scenes are fully declarative — frames animate between any
chart configuration (bar → line → stacked → polar…, 40+ types; see
[`references/vizzu-chart-gallery.md`](src/dstory/references/vizzu-chart-gallery.md)).
No scene JS file exists for this story at all.

## The cookbook

When you want the bespoke-D3 look without writing D3 from scratch: 10 complete,
themed, responsive scene renderers — **[see them rendered](https://dkedar7.github.io/dstory/gallery/)**.

```bash
dstory recipes                                        # list: line-reveal, beeswarm, bump-chart, ...
dstory scene my-story scene-growth --from line-reveal # copy one in, wired and ready
```

A recipe is source code dropped into *your* project — edit it freely, it's
yours. Each documents its dataset columns and `scene.config` options in the
file header. All are theme-token driven and respect `prefers-reduced-motion`.
There is still no `BarChart()` API and never will be: recipes are starting
points, not abstractions.

## Quick start (CLI)

```bash
# 1. Scaffold a project from one of the 8 bundled themes
dstory init my-story --theme editorial-noir --audience general-public

# 2. Add scenes: from the cookbook, a blank stub, or by hand
dstory scene my-story scene-trend --from line-reveal
#    ...then edit my-story/data.json (datasets, headlines, claims)

# 3. Preview while authoring
dstory preview my-story

# 4. Bundle to a single self-contained HTML file
dstory bundle my-story --vendor
# → my-story/dist/story.html  (--vendor inlines d3/scrollama/Motion: works offline)

# 5. Vet before delivery
dstory vet my-story/dist/story.html --data my-story/data.json
```

Other commands: `dstory themes` (the 8 brand presets), `dstory recipes` (the cookbook), `dstory --help`.

## Claims that can't drift from the data

```python
from dstory.prep import compute_ratio, compute_claim

ratio = compute_ratio(after=2900, before=1000)        # 2.9
claim = compute_claim(
    id="c1",
    text_template="Signups {phrase} in Q1",           # → "Signups tripled in Q1"
    value=ratio,
)
```

`compute_claim()` derives the phrase from the value using the same vocabulary
the vetter checks ("doubled"…"quintupled", percentages), so a claim built this
way cannot fail data-fidelity vetting — and a hand-written claim that drifts
from its value blocks the build.

## How is this different from…?

| | dstory |
|------|------|
| **Streamlit / Dash** | No server. The output is one HTML file that works from an email attachment. Narrative-first (scroll/slides), not dashboard-first. |
| **ipyvizzu-story** | dstory's vizzu scenes cover the same ground, then add: 5 other scene kinds (scrolly D3, full-bleed, pinned…), a brand/theming system, claim-vs-data vetting, and a11y/editorial gates. |
| **Quarto** | Quarto renders documents; dstory builds bespoke *graphics-led* stories with scroll-driven chart morphs, and vets the output in a real browser before you ship. |
| **Flourish / Datawrapper** | Code-first and version-controlled; your data never leaves your machine; no per-seat licensing. But you bring the polish — dstory brings the rails. |

## Brand system

Brands let consumers fit `dstory` to their visual system without forking the package.

A brand is a TOML file (or a `Brand` Python object) defining color tokens, typography, motion personality, atmosphere, and chart palette. The 8 bundled presets are themselves brand TOMLs.

```toml
# acme-brand.toml
[brand]
name    = "Acme Corp"
extends = "minimal-light"               # inherit base; override below

[colors]
accent   = "#FF6B35"
accent_2 = "#1B4332"

[colors.categorical]
palette  = ["#FF6B35", "#1B4332", "#3A86FF", "#FFBE0B", "#8338EC", "#06A77D", "#D62828"]

[typography]
display      = "'Fraunces', Georgia, serif"
body         = "'Inter Tight', system-ui, sans-serif"
google_fonts = ["Fraunces:opsz,wght@9..144,400;9..144,700",
                "Inter+Tight:wght@400;500;600"]
```

Use it via CLI or Python:

```bash
dstory init acme-story --theme ./acme-brand.toml
```

```python
from dstory import Brand, init
brand = Brand.from_toml("acme-brand.toml")     # or .from_preset("editorial-noir").extend(accent="#FF6B35")
init("acme-story", brand=brand)
```

The 8 bundled presets:

| Name | Vibe |
|------|------|
| `editorial-noir` | Urgent, somber, magazine-cover serious |
| `scientific-bright` | Rigorous, optimistic, paper-like |
| `tech-glow` | Dense, dark, terminal-influenced |
| `minimal-light` | Restrained, gallery, lots of whitespace |
| `warm-print` | Print-magazine warmth, ledger feel |
| `playful-pastel` | Friendly, illustrative, kid- and student-friendly |
| `brutalist` | Raw, unapologetic, monospace-heavy |
| `data-fi` | Futurist, cinematic, chart-as-art |

## Scene kinds

A `data.json` story is composed of scenes; each declares its `kind`:

- `simple` — single chart-driven moment (headline + commentary + chart mount)
- `scrolly` — sticky chart + stepping text; chart morphs on each step (custom D3 logic)
- `bleed` — full-viewport cinematic moment
- `pinned` — central object pinned for one scroll-section, transformed by scroll progress
- `vizzu` — animated data pivots declared as `frames[]`; supports rectangle/circle/line/area geometries × cartesian/polar coordinates × all channel combos. See [`references/vizzu-chart-gallery.md`](src/dstory/references/vizzu-chart-gallery.md) for the 40+ chart types this enables.
- `custom` — chrome-free; the renderer owns the entire `<section>` mount. Use for kinetic typography, embedded interactives, full-bleed magazine layouts, anything the four-h2-then-mount pattern doesn't fit.

### Per-scene layout overrides

| Field | Values | Effect |
|------|------|------|
| `width` | `narrow` (~36rem) / `default` (~56rem) / `wide` (~78rem) / `full` (100%) | Override the scene's max-width without touching CSS |
| `chrome` | `true` (default) / `false` | When `false`, omit the auto-generated h2/p/source elements; renderer takes full control |

### Reaching every reader

`meta` fields that widen who can read (and share) the story:

| Field | Effect |
|------|------|
| `lang` / `dir` | Set `<html lang dir>` — screen-reader voice, hyphenation, RTL layout |
| `description` | `<meta name="description">` + Open Graph/Twitter description (falls back to `deck`) |
| `share_image` | og:image / twitter:image for link unfurls (absolute URL) |
| `hero_image` | Full-bleed hero photo with a theme-aware scrim; local files are inlined at bundle time |

Per scene, set `alt` — one sentence stating what the chart shows *and* the
takeaway. It becomes `role="img"` + `aria-label` on the chart mount, and the
vetter flags chart scenes that lack it. The template also ships a
skip-to-content link, a reading progress bar, `prefers-reduced-motion`
support, a print stylesheet (browser print → clean PDF handout), and
`#slide-N` deep links in slides mode.

The vetter is audience-aware too: it scores the story's prose (Flesch reading
ease) against `meta.audience` and notes when the writing is harder than that
audience should have to work for.

For project-wide CSS overrides, set `Story.extra_css` in your data:

```python
story = Story.model_validate({
    "meta": {...},
    "extra_css": ".my-special-scene { display: grid; ... }",
    ...
})
```

The bundler appends `extra_css` as a final `<style>` block, overriding anything in story.css.

## Story modes

By default the story plays as a scroll-driven essay. Set `meta.mode: "slides"` in `data.json` to flip it into a click/keyboard slide deck (arrow keys, click-to-advance, prev/next buttons, position indicator). Same scenes, same charts, same theme — different pacing.

| `meta.mode` | Feels like | Pick for |
|------|------|------|
| `"scroll"` (default) | A film | Published web essays, blogs, mobile, social shares |
| `"slides"` | A presentation | Live talks, exec briefings, screen-shared meetings, walkthroughs |

## Vetting (mandatory)

`dstory vet` (or `dstory.vet()`) grades the bundled HTML on five dimensions:

1. **Renders correctly** — headless browser at 1440/768/480, no console errors, charts paint
2. **Data fidelity** — every numeric claim cross-checked against `data.json` (catches "tripled" vs `value=2.4`)
3. **Editorial integrity** — no slop phrases, no placeholders, sources present, headlines are insights
4. **Visual quality** — full-page screenshots saved at all viewports for manual review
5. **Accessibility & ethics** — color contrast, no PII leaks, dual-axis warnings, alt text

A bundled story is "ready to ship" only when all five pass.

## Project layout

```
dstory/
├── src/dstory/
│   ├── api.py          # build() — Story → bundled HTML in one call
│   ├── schema.py       # pydantic models for data.json (Story, Meta, Scene, Claim, ...)
│   ├── brand.py        # Brand class — TOML loader, preset extension, CSS emission
│   ├── scaffold.py     # init() — copy template + write theme.css
│   ├── bundle.py       # bundle() — inline CSS/JS/images/data; --vendor for offline
│   ├── vet.py          # vet() — 5-dimension report (Playwright optional)
│   ├── prep.py         # pandas helpers + compute_claim() (vetter-aligned)
│   ├── cli.py          # `dstory` CLI
│   ├── cookbook/       # 10 complete scene recipes (+ registry & demos)
│   ├── themes/         # 8 preset brand TOMLs
│   └── templates/      # HTML/CSS/JS skeleton copied into new projects
├── docs/gallery/       # rendered cookbook gallery (GitHub Pages)
├── tests/              # 134 tests, pytest (browser e2e skips without Chromium)
└── pyproject.toml
```

## Why does this exist?

Data storytelling is two distinct jobs:

1. **Plumbing** — scaffolding, bundling, validating, vetting. Deterministic. Same bug shouldn't be re-fixed in every project.
2. **Creative work** — the story arc, the chart design, the annotation language, the editorial voice. Varies by piece.

`dstory` packages the plumbing so you don't reinvent it (or its bugs) per project. The creative work — written in plain JS/D3 in your `scenes/*.js` files — stays under your control. There is intentionally no `BarChart()` component in this library.

For the creative authoring guide (story arcs, audience adaptation, chart selection, scrollytelling patterns, anti-slop rules), see the companion **data-storytelling** Claude skill.

## License

MIT — see [LICENSE](LICENSE).
