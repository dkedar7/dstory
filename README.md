# dstory

> Turn DataFrames into NYT-style scrollytelling and slide-deck data stories — one self-contained HTML file you can email, host, or present. Pure Python in, no JavaScript required.

**[📖 Documentation](https://dkedar7.github.io/dstory/)** ·
**[▶ Live demo: *Ctrl-Alt-Reinvent — Microsoft, 1975–2025*](https://dkedar7.github.io/dstory/demo/)** — a 40-scene data essay built with dstory ·
**[▶ Cookbook gallery](https://dkedar7.github.io/dstory/gallery/)** — the chart recipes, rendered ·
**[▶ Theme showcase](https://dkedar7.github.io/dstory/themes/)** — same story, eight personalities ·
**[▶ Morph showcase](https://dkedar7.github.io/dstory/morphs/)** — bars curl into pies, live, zero JS

`dstory` is the deterministic infrastructure for data stories: a one-call builder, a single-file bundler, a 5-dimension vetter (renders / data fidelity / editorial integrity / visual / a11y), a brand system for your colors and typography, and pydantic schemas that surface authoring bugs at build time instead of delivery time.

## In 30 seconds

```bash
pip install "dstory[all]" && playwright install chromium
dstory draft sales.csv            # -> sales/dist/story.html
```

or, in a notebook, `dstory.build(pd.read_csv("sales.csv"), "sales")`.

You get one HTML file to email or host (`--vendor` also inlines the chart
libraries, so it works with no network). It picks the charts and writes the
headlines from your numbers, and every number in the prose is checked against
the data before the file is written. Every chart comes with a data table, a
CSV download, a keyboard explorer for screen readers, and a Listen button.
Add `--mode slides` for a deck. Then edit `sales/data.json` and run
`dstory bundle sales` to make it yours. The rest of this page covers authoring
by hand.

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
             # grouped bars: churn sits beside signups instead of hiding behind them
             "config": {"channels": {"x": ["month", "variable"], "y": "value", "color": "variable"},
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

With `vet=True`, `build()` runs the browser checks (does every chart paint, any
console errors, screenshots) whenever Playwright and Chromium are installed, and
warns when it can't. If that happens, `result.report.skipped` lists what wasn't
checked. Run `pip install "dstory[vet]" && playwright install chromium` to get the full gate.

`kind: "vizzu"` scenes are fully declarative — frames animate between any
chart configuration (bar → line → stacked → polar…, 40+ types; see
[`references/vizzu-chart-gallery.md`](src/dstory/references/vizzu-chart-gallery.md)).
No scene JS file exists for this story at all.

## Zero-config: `dstory draft`

Skip the dict entirely. Point dstory at a data file and get a vetted story:

```bash
dstory draft mix.csv --theme warm-print --source "Power-mix shares"
#  -> mix/dist/story.html, vetted (browser checks too when Chromium is installed)
```

`draft` profiles the table (time, category and measure columns; wide tables
are melted), picks scenes by rule, maps the columns onto cookbook recipes, and
writes headlines, commentary and alt text from computed facts. Every number in
that prose is a registered claim, so the vetter checks it against the data.
Deterministic and offline: no model, no key. It reads CSV, TSV, JSON, Parquet
and Excel; `--mode slides`, `--vendor`, `--max-scenes` and `--no-vet` work as
elsewhere. The output is a normal project: edit `mix/data.json`, then
`dstory bundle mix`.

Real exports are messy, and `draft` copes:

- Numbers stored as text ("$1,200", "12%", "(300)") are read as numbers.
- A stray typo or blank cell is dropped and named in `explain()`
  (`(cleaned) sales: read as numbers; 1 non-numeric value dropped ('abc')`),
  rather than aborting the draft.
- Time columns are recognised from their values: "Jan 2024", "2024 Q1" or
  "Q1 2024", and evenly spaced years in a column with any name.

The same thing from Python, with a DataFrame:

```python
import pandas as pd, dstory

df = pd.read_csv("mix.csv")                    # year, source, share_pct
d = dstory.draft(df, title="Gas took coal's place", theme="warm-print")
print(d.explain())
result = dstory.build(d.story, "mix", scenes=d.scenes, vet=True)
result.passed                                  # True

dstory.build(df, "mix")                        # or: a DataFrame straight in
```

```text
Scenes:
  1. scene-trend: line-reveal over year x share_pct -- time series detected; share_pct is a share, compared in percentage points, so it follows the largest source in 2024 (Gas)
  2. scene-shift: slope-chart of source, 2014 vs 2024 -- category x first/last period (4 source values present in both)
  3. scene-race: bump-chart of source rank by share_pct -- the top source changed (Coal in 2014, Gas in 2024)
  4. scene-mix: waffle of source by share_pct in 2024 -- share_pct sums to ~100 per year
Claims (6), each checked by the vetter:
  c-trend: Gas share rose 16 points between 2014 and 2024
  c-shift: Coal share fell 24 points between 2014 and 2024, the biggest shift of any source
  ...
```

Rules today:

| Data | Scene |
|---|---|
| an additive measure over time, split by 2 to 7 categories | an animated **Vizzu opener**: the total as stacked bars, which morph into one line per category as you scroll |
| time x measure | `line-reveal` |
| 3 to 8 categories over 4+ periods (when the opener didn't already split them) | `small-multiples`, one panel per category ("Every metro peaked in 2021") |
| category x first/last period | `slope-chart`, or `range-dots` past 7 categories, where slope labels collide |
| the top-ranked category changed over time | `bump-chart` ("Gas overtook Coal to rank first by 2024") |
| shares summing to ~100 (or ~1) | `waffle` |
| anything else | one safe `bar-steps` scene |

The prose follows newsroom conventions so a reader can't be misled:

- Shares are compared in percentage points ("fell 24 points"), not relative
  percent.
- Big multiples read as "rose 12-fold", not "rose 1100%".
- A change across zero is described ("turned negative in 2023"), never given as
  a percent.
- Daily dates read "on Jan 2, 2024".
- Separate columns (Signups, Churn) are never summed into a total.
- The opener only stacks when the total is real: no gaps, no negative values,
  and a measure that adds up.
- A summed "Total" line covers only periods where every category reports. A
  missing or dropped cell never shows up as a fall. With fewer than 3 complete
  periods, the trend follows the largest category instead, and `explain()`
  names the gap.
- Small-multiple panels share one scale, so heights compare. When the largest
  panel is 10x the smallest (or the columns are separate series), each panel
  gets its own labelled scale and the text says "compare shapes, not heights".

Vizzu loads WebAssembly from its CDN, so it can't be inlined. An offline
build (`--vendor`, or `build(df, vendor=True)`) therefore keeps the D3 line
chart instead of the opener. Pass `--no-opener` (`opener=False`) to always use
the line chart.

The vetter enforces the same rules for hand-written claims:

- `unit: "pp"` claims are checked as points. Build them with
  `prep.compute_point_change()`.
- "N-fold" is checked against the ratio.
- A direction verb ("rose", "fell") must match the sign.
- A percent fall beyond 100% fails.

`d.story` is a plain data.json dict, so edit it like one;
`d.to_project("mix")` writes a normal project instead. Needs the `[prep]`
extra (`pip install "dstory[prep]"`).
**[See one CSV drafted in two themes](https://dkedar7.github.io/dstory/drafted/)**.

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

Other commands: `dstory draft data.csv` (a vetted story from a data file, zero config), `dstory themes` (the 8 brand presets), `dstory theme my-story warm-print` (re-theme a project), `dstory upgrade my-story` (bring a project's runtime up to date), `dstory recipes` (the cookbook), `dstory --help`.

**Upgrading dstory upgrades your projects.** A project keeps its own copy of
`story.js` and `story.css`. After `pip install -U dstory`, the next
`dstory bundle` replaces copies you never touched with the new version, so
fixes reach stories you made months ago. A copy you edited is kept, and the
bundle tells you so; `dstory upgrade my-story --force` replaces it after saving
yours to `.dstory-backup/`. `--no-upgrade` on `dstory bundle` (or
`upgrade=False` in `bundle()`) keeps everything as it is.

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
and windows the vetter checks ("doubled"…"quintupled", percentages), so a claim
built this way cannot fail data-fidelity vetting — and a hand-written claim that
drifts from its value blocks the build: `build()` and `dstory bundle` refuse to
write it (`ClaimDriftError`; opt out with `check_claims=False` /
`--no-check-claims`). `compute_ratio()` and
`compute_pct_change()` tag their result with its unit, and the claim records it
(`"unit": "ratio"` or `"pct"`), so a 3.4× ratio is never printed as "3.4%" and a
+2% change is never called "doubled". For a plain float, pass
`kind="ratio"` or `kind="pct"`.

A claim is only as good as the words the reader sees, so the vetter also checks
the prose around it. Give a claim a `scene` and every change that scene's
headline, commentary, steps or alt text states must fit one of its claims:
"doubled"…"quintupled", "N-fold", "5x", "three times over", "fell by half", a
percent change with a direction ("rose 30%", "down 4%", "a 30% drop") and a
change in points ("up 2 points"). The direction counts, so "Churn fell 30%"
against a claim that churn rose 30% stops the build, as does editing the
headline to "quintupled" and forgetting the claim. A bare figure with no
direction ("12% of users", "made up 47%") is a level or a share, not a change,
and is left alone. If a scene states a second change, register a claim for it
too. A registered claim whose text appears in no reader-facing prose is flagged
as well.

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

To re-theme an existing project, set `meta.theme` in `data.json` and run
`dstory bundle` (it switches when `theme.css` is still the stock preset, and
warns, keeping your edits, when it isn't), or run `dstory theme my-story warm-print`
(or a brand `.toml`) to switch outright. An unknown name in `meta.theme` gets a
warning that lists the presets.

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
- `scrolly` — sticky chart + stepping text; chart morphs on each step (custom D3 logic). The scene's own `headline` and `commentary` open the text column, above the steps.
- `bleed` — full-viewport cinematic moment
- `pinned` — central object pinned for one scroll-section, transformed by scroll progress. The scene's `headline` and `commentary` sit above it.

Every kind except `custom` shows the scene `headline` and `commentary` you write; `"chrome": false` hides them (and the source line) on `simple`, `scrolly` and `pinned` scenes. The vetter grades only text a reader can see, so hidden text is never scored or blocked on.
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

### Every chart ships its data

Under every scene that has a `dataset`, the bundled story carries a collapsed
**Data** panel, with no code from you:

- a real `<table>` of the rows behind the chart, with a caption and column
  headers. Screen-reader users can read every number; sighted readers can check
  a claim. Long tables show 50 rows, then "Show all".
- a **Download CSV** link built from the inlined rows as a `data:` URL, so it
  works offline. Text that a spreadsheet would run as a formula (a leading
  `=`, `+`, `-`, `@`, tab or their full-width forms) gets a `'` prefix, so a
  scraped `-2+3+cmd|...` cell cannot run; plain numbers like `-5` are kept.
- numbers formatted for `meta.lang` (`"de"` reads `1.000,5`). Years, IDs and
  codes stay ungrouped (`2020`, not `2,020`): integer columns named like
  `year`, `*_id`, `code`, `fips` or `zip`, or holding only values 1000 to 2999.
  Override per column with `"table_format": {"sold": "raw"}` (or `"number"`).
- in slides mode, a small tab in the corner; press `t` to open it.
- in print, every table opens, so a PDF handout carries the data.

It is renderer-agnostic, so it works for your own D3 and for Vizzu scenes too,
and projects made by older versions get it when you re-bundle them. The vetter
opens each story in Chromium and checks that every table and CSV matches
`data.json` (row count, columns, first and last rows).

Tune it in `data.json`:

```json
"meta":   {"a11y": {"table": true, "download": false, "explorer": true, "sonify": true}},
"scenes": [{"id": "s1", "a11y": {"table": false}, "table_columns": ["month", "value"]}]
```

or leave it out of a bundle with `dstory bundle my-story --no-a11y-extras`
(`build(..., a11y_extras=False)`). A chart scene with no `alt` *and* no table
fails the vet, however the table was turned off: a screen-reader user would get
nothing.

### Every chart reads out loud

Every chart with a `dataset` can also be read with the keyboard, again with no
code from you. Tab to a chart (it gets a focus ring) and a readout pinned to the
bottom of the screen, also announced to screen readers through an `aria-live`
region, summarises it:

> Growth was a coastal story. West, 6 points, from 100 to 171, rising; Northeast,
> 6 points, from 100 to 158, rising; …

Then:

| Key | Does |
|---|---|
| `←` `→` | previous / next point: "2020: index 108 (West), 2 of 6" |
| `↑` `↓` | previous / next series, at the same x |
| `Home` `End` | first / last point |
| `Enter` | the summary again |
| `Esc` | leave the chart (in slides mode the arrows go back to the deck) |

It reads the data, not the drawing, so it works for every recipe, your own D3
and Vizzu. It picks the columns from `scene.config` (`x`, `y`, `label`, `series`,
`start`, `end`…) or, failing that, from the data: dates become "May 2024", text
columns name the points, and a repeating text column becomes the series. The
vetter tabs into each chart, presses `Home` and `End`, and fails the story if a
chart cannot be reached or reads numbers that are not in its dataset. Turn it off
with `"a11y": {"explorer": false}` in `meta` or a scene; `--no-a11y-extras`
leaves it out along with the tables.

### Every chart can be heard

Next to each chart's **Data** summary sits a **▶ Listen** button. Press it and
the chart plays as sound: every point is a short tone, higher for a bigger
value (two octaves, the lowest value to the highest) and panning left to right
as the series goes on. A chart with several series plays them one after
another, each announced first ("West, 6 points, from 100 to 171, rising"),
both to screen readers and on screen. With a chart focused, `L` plays just the
series you're on, and `Esc` stops.

It is plain Web Audio inside the HTML file, with no library and no network.
Nothing plays until a reader asks. A scatter plays along its x axis; a chart
with no numbers (a timeline of dates and labels) gets no button. The vetter
checks that every chart that can be heard has its button, plays one tone per
value, and never plays a bigger value at a lower pitch. Turn it off with
`"a11y": {"sonify": false}` in `meta` or a scene; `--no-a11y-extras` leaves it
out with the tables and the explorer.

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
├── tests/              # pytest; browser e2e (kind × mode matrix included) skips without Chromium
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
