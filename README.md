# dstory

> Build interactive scrollytelling and slide-deck data stories from Python — scaffold, brand, validate, bundle, and vet a single self-contained HTML file.

**[▶ Live demo: *Ctrl-Alt-Reinvent — Microsoft, 1975–2025*](https://dkedar7.github.io/dstory/)** — a 40-scene data essay built with dstory: a custom Microsoft brand, 16 distinct chart idioms (sankey, chord, ridgeline, calendar heatmap, 3D, world map…), one self-contained HTML file.

`dstory` is the deterministic infrastructure for building NYT/FT/Pudding-style data stories: a tested scaffolder, a single-file bundler, a 5-dimension vetter (renders / data fidelity / editorial integrity / visual / a11y), a brand system that lets anyone swap their own colors and typography without touching source code, and pydantic schemas that surface authoring bugs at build time instead of at delivery time.

The chart authoring (D3, custom morphs, bespoke annotations) stays your job — that's where the creative variety lives. `dstory` handles everything else.

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

## Quick start (CLI)

```bash
# 1. Scaffold a project from one of the 8 bundled themes
dstory init my-story --theme editorial-noir --audience general-public

# 2. Edit my-story/data.json and write scene JS files in my-story/scenes/
#    (See the dstory data-storytelling skill for the creative authoring guide.)

# 3. Bundle to a single self-contained HTML file
dstory bundle my-story
# → my-story/dist/story.html  (open it directly in a browser, no server needed)

# 4. Vet before delivery
dstory vet my-story/dist/story.html --data my-story/data.json
```

Other commands:
- `dstory themes` — list the 8 bundled brand presets
- `dstory --help` — full CLI reference

## Quick start (Python API)

```python
from dstory import Brand, Story, init, bundle, vet
from dstory.prep import compute_ratio, compute_claim, to_records
import pandas as pd

# Pick a brand (or load a custom TOML)
brand = Brand.from_preset("scientific-bright")

# Scaffold the project
init("/tmp/my-story", brand=brand, audience="technical-peer", mode="scroll")

# Crunch data with pandas
df = pd.DataFrame({"month": ["Jan","Feb","Mar"], "users": [1000, 1500, 2900]})
ratio = compute_ratio(after=df.users.iloc[-1], before=df.users.iloc[0])

# Build a claim that's guaranteed to pass the vetter
claim = compute_claim(
    id="c1",
    text_template="Users {phrase} between January and March",
    value=ratio,                   # 2.9 → "tripled"
)

# Validate data.json with pydantic before writing
story = Story.model_validate({
    "meta": {"title": "Growth", "theme": "scientific-bright", "audience": "technical-peer"},
    "claims": [claim],
    "scenes": [{"id": "scene-growth", "kind": "simple",
                "headline": "Users tripled in Q1", "commentary": claim["text"],
                "dataset": "users"}],
    "datasets": {"users": to_records(df)},
})
# ... write story.model_dump_json() to my-story/data.json ...

# Bundle and vet
result = bundle("/tmp/my-story")
report = vet(result.out, data="/tmp/my-story/data.json")
print("PASS" if report.passed else "BLOCKED")
```

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
│   ├── schema.py       # pydantic models for data.json (Story, Meta, Scene, Claim, ...)
│   ├── brand.py        # Brand class — TOML loader, preset extension, CSS emission
│   ├── scaffold.py     # init() — copy template + write theme.css
│   ├── bundle.py       # bundle() — inline CSS/JS/images, embed data.json
│   ├── vet.py          # vet() — 5-dimension report (Playwright optional)
│   ├── prep.py         # pandas helpers + compute_claim() (vetter-aligned)
│   ├── cli.py          # `dstory` CLI
│   ├── themes/         # 8 preset brand TOMLs
│   └── templates/      # HTML/CSS/JS skeleton copied into new projects
├── tests/              # 70 tests, pytest
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
