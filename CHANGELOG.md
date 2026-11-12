# Changelog

All notable changes to `dstory` are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Every chart can be heard** (#14, milestone 3, which completes #14). Every
  chart with a numeric series gets a **▶ Listen** button beside its Data
  summary, with no code changes. Each point plays as a short tone: pitch
  follows the value over two octaves, pan follows its position left to right.
  Series play one after another, each announced first through the explorer's
  `aria-live` readout (also shown on screen while it plays). With a chart
  focused, `L` plays the current series; `Esc` stops.
  - Web Audio only: no library, no network, never autoplays. A scatter plays
    along x. Charts with no numbers get no button.
  - `a11y.sonify` (meta or scene) turns it off; `--no-a11y-extras` leaves it
    out with the tables and the explorer.
  - The vetter checks every chart that can be heard has its button, plays one
    tone per value, and never maps a bigger value to a lower pitch.
- `dstory theme SLUG THEME`: re-theme a project from a preset or brand TOML.

### Changed
- The Data panel now sits in a `.scene-tools` row under the chart, shared with
  the Listen button. Themes that styled `.scene > .scene-data` should target
  `.scene-tools` for placement; the panel itself is unchanged.

### Fixed
- The vetter catches prose that has drifted from its claim: a headline edited
  to "quintupled" while the registered claim (value 2.9) still says
  "tripled". Every ratio word or N-fold in a scene's headline, commentary,
  steps, frames, alt or annotation must fit one of the claims tied to that
  scene, or data fidelity fails, and `build()` / `dstory bundle` stop with
  `ClaimDriftError`. The "claim not found in prose" check now searches only
  reader-facing text; it used to search the inlined data.json, so it always
  found the claim itself and never fired (#25).
- `dstory bundle` honours `meta.theme` in a CLI project. When it names another
  preset and `theme.css` is the stock preset, the project switches; when
  `theme.css` was edited, it is kept with a warning; an unknown name warns with
  the preset list (it will become an error). New `dstory theme SLUG THEME`
  re-themes a project from a preset or a brand TOML and updates `meta.theme`
  (#26).
- Slides mode: a deck with a Vizzu scene is navigable as soon as the page is
  ready. Arrow keys used to do nothing (counter "0 / 0") until Vizzu loaded,
  4 s offline, and presses were dropped. A Vizzu slide now applies its frame
  when its controller arrives. New projects and `build()` get it directly; an
  existing CLI project keeps its copied `story.js` until it is refreshed with
  `dstory.init("SLUG", brand="<its theme>", merge=True)` (#27).

## [0.12.0] - 2026-11-10

### Added
- **Every chart reads out loud** (#14, milestone 2). Every scene with a
  `dataset` gets a keyboard chart explorer, with no code changes. Tab to a
  chart and an `aria-live` readout (also shown on screen while the chart has
  focus) summarises each series: "West, 6 points, from 100 to 171, rising".
  The arrow keys step through the points ("Jan 2024: 1,200,000, 1 of 6"); up
  and down switch series at the same x; `Home`, `End`, `Enter` (summary) and
  `Esc` (leave) also work. In slides mode the arrows belong to the focused
  chart until `Esc`.
  - It reads the data, not the drawing: columns come from `scene.config` or
    are inferred, ISO dates are read as "May 2024" in `meta.lang`. It works for
    recipes, custom D3 in a recipe-style mount, and Vizzu. Scenes of
    `kind: "custom"` keep the table but get no explorer.
  - It is injected by the bundler, so older projects get it on re-bundle.
  - `a11y.explorer` (meta or scene) turns it off; `--no-a11y-extras` leaves
    it out with the tables.
  - The vetter tabs into each chart, presses `Home` and `End`, and fails a
    chart that cannot be reached or that reads numbers missing from its
    dataset.

### Changed
- A chart mount with a dataset is now `role="application"` with
  `aria-roledescription="chart"` (it was `role="img"`), so screen readers pass
  the arrow keys to the explorer. Its `aria-label` (`scene.alt`) is unchanged;
  with the explorer off it stays `role="img"`.

### Fixed
- The Data panel's CSV now neutralises formulas that start with `-` (and the
  full-width `＝ ＋ － ＠`), not just `=`, `+`, `@`: a scraped
  `-2+3+cmd|' /C calc'!A0` cell no longer reaches a spreadsheet as a live
  formula. Numbers stored as text (`"-5"`, `"-1.2%"`) are left as they are (#23).
- The Data table no longer shows years and IDs as quantities (`2,020`,
  `10,001`). Integer columns named like a year, ID or code, or holding only
  values 1000 to 2999, are shown ungrouped. New `scene.table_format`
  (`{"col": "raw" | "number"}`) overrides it per column. The vetter's table
  check uses the same rule (#24).
- `dstory vet` now fails a chart with no `alt` when the bundle was made with
  `--no-a11y-extras` / `a11y_extras=False`, as documented. Such bundles now
  carry a `<meta name="dstory:a11y-extras" content="off">` marker; bundles
  from before 0.11 keep the old note and a hint to re-bundle (#22).

## [0.11.0] - 2026-11-09

### Added
- **Every chart ships its data** (#14, milestone 1). Every scene with a
  `dataset` now gets a collapsed **Data** panel in the bundled story, with no
  code changes:
  - an accessible `<table>` of its rows: caption, column headers, row
    headers, 50 rows then "Show all", numbers formatted for `meta.lang`;
  - a **Download CSV** link built from the inlined rows (a `data:` URL, so it
    works offline). Text a spreadsheet would run as a formula is quoted.
  - In slides mode it is a corner tab, and `t` toggles it. Print opens every
    table.
  - It is injected by the bundler, so it works for custom D3 and Vizzu scenes,
    and for projects made by older versions once they are re-bundled.
- `meta.a11y` / `scene.a11y` (`{"table": bool, "download": bool}`) and
  `scene.table_columns` to tune it. `validate_dataset_refs()` reports
  `table_columns` that aren't in the dataset.
- `dstory bundle --no-a11y-extras`, `bundle(a11y_extras=False)` and
  `build(a11y_extras=False)` leave the panel out.
- **The vetter checks the data a reader sees.** In Chromium, every data
  scene's table and CSV must match `data.json`: row count, columns, and the
  first and last rows. A scene with no `alt` and its table turned off now
  fails "Accessibility & ethics": a screen-reader user would get nothing.

### Fixed
- **No false superlatives when range-dots trims categories** (#20). Past 15
  categories, "the biggest shift of any city" and "changed least" were
  computed over the 15 shown, so a dropped city that rose 8-fold went unseen.
  They are now computed over every category in both periods. The chart keeps
  the 15 largest in the last period, plus any category the text names. The
  commentary and alt text say the chart is a subset, and `explain()` reports
  the real count. (0.10.0's CHANGELOG said range-dots "keeps up to 15, sorted
  by change". It kept the 15 largest by final value, then sorted those by
  change.)

## [0.10.0] - 2026-11-08

### Added
- **Small multiples in drafts** (#11, final milestone). With 3 to 8
  categories over 4 or more periods, `draft()` and `dstory draft` add a
  `scene-panels` scene: one mini line chart per category. The headline is
  the shape the panels share ("Every metro peaked in 2021", "Every city but
  Tulsa rose between 2018 and 2023"). The scene is skipped when the Vizzu
  opener already splits the lines.
- **Independent scales.** The `small-multiples` recipe takes
  `config.scale: "independent"`. Each panel then gets its own y-range,
  labelled with its min and max. `draft()` uses it when the largest panel is
  10x the smallest, or when the columns are separate series. The commentary
  then says so: "Each panel has its own scale, so compare shapes, not
  heights." The default stays `"shared"`.
- **Range-dots for many categories.** The before/after scene uses
  `range-dots` instead of `slope-chart` past 7 categories, where slope labels
  collide. It keeps up to 15, sorted by change.
- Docs: a third drafted gallery example (`docs/drafted/metros.html`). It shows
  8 metros of very different sizes, built offline with `--vendor`.

### Changed
- `draft()` now hands 8 to 10 categories to `range-dots`; 0.9.0 used
  `slope-chart` for them.

### Fixed
- **A missing cell no longer reads as a fall in the "Total" headline** (#19).
  A period where one category had no value (a blank, a missing row, or a
  typo `draft()` dropped) used to be summed anyway. That gave headlines like
  "Total sales fell 40%" while every region grew. The total now covers only
  periods where every category reports. With fewer than 3 such periods, it
  follows the largest category instead, and `explain()` names the gap.

## [0.9.0] - 2026-11-07

### Added
- **The animated opener** (#11, milestone 3). When a measure adds up across 2
  to 7 categories over time, `draft()` and `dstory draft` open with a Vizzu
  scene. The first frame shows the total as stacked bars ("Total gwh rose 29%
  between 2015 and 2024"). It then morphs into one line per category ("In
  2024, Gas made up 38% of the total"). Every number is a vetted claim.
  - It is skipped when the stack wouldn't be a real total: a missing value,
    negative values, shares, or a measure that doesn't add up.
  - It is also skipped for `--vendor` builds, because Vizzu can't be inlined.
  - Opt out with `opener=False` or `--no-opener`.
- **Messy spreadsheet numbers.**
  - `draft()` reads text columns that are numbers ("$1,200", "12%", "(300)")
    as numbers.
  - It drops a stray typo or blank cell and names it in `explain()`, instead
    of failing with "no numeric measure column".
  - A column becomes a measure when at least 80% of its non-blank values
    parse, or when only one value doesn't.
- **Time columns from values.** Month names ("Jan 2024"), quarters ("2024 Q1",
  "Q1 2024", "2024-Q1") and evenly spaced years in a column of any name are
  read as time. Quarters are labelled "Q1 2024" in the prose.
- `BundleResult.self_contained`: False when a local file reference survived
  bundling.
- Docs: a second drafted gallery example (`docs/drafted/generation.html`), a
  spreadsheet export with the animated opener.

### Changed
- `dstory scene <slug> <id> --kind vizzu` no longer writes a JS stub (#18).
  Vizzu scenes are declarative, and a registered renderer replaced the
  built-in one and left the chart blank. The command now prints the data.json
  snippet to add. `starter_scene_js(id, "vizzu")` is unchanged for API users;
  its comment now warns about the override.
- `dstory bundle` exits 1 when the output is not self-contained.
- "The sharpest move" commentary is skipped when nothing moved.

### Fixed
- **A blank Vizzu canvas now fails "Renders correctly"** (#18). The paint
  audit samples each canvas and requires real ink: more than 1% of pixels
  differ from the background. Previously any canvas with a size counted as
  painted, so a blank chart passed the vet.
- **Deleting a scene's JS file no longer breaks the bundle** (#18). `bundle()`
  drops a `<script src>` tag whose file is missing and warns, instead of
  shipping a tag that fails to load in every reader's browser.

## [0.8.0] - 2026-11-06

### Added
- **`dstory draft <file>`: the zero-config story, no Python needed** (#11,
  milestone 2). Reads CSV, TSV, JSON, Parquet or Excel and drafts the story. It
  then bundles one self-contained HTML and vets it, browser checks included
  when Chromium is installed. It prints `explain()` and the vet table, and
  exits 1 when the vet blocks. Options: `--title`, `--theme`, `--mode`,
  `--audience`, `--source`, `--max-scenes`, `--vendor`, `--no-vet`,
  `--no-browser`, `--out` and `--overwrite`.
- **New draft rule, `bump-chart`**: when the top-ranked category changes over
  time (3 to 12 periods), `draft()` adds a race scene, for example "Gas
  overtook Coal to rank first by 2024", with the new leader highlighted.
- **Percentage-point claims**: `prep.compute_point_change()`, a `PointChange`
  value and claim `unit: "pp"`. The vetter checks "fell 24 points" against
  the value and its sign.
- **"N-fold" phrasing**: ratios of 5.5 or more read as "rose 12-fold"
  (`prep.fold_phrase()`), and the vetter checks the multiple against the
  ratio.
- `draft()` sets `meta.published` to the draft date.

### Changed
- `draft()` compares shares in percentage points rather than relative percent
  ("Coal share fell 24 points", not "fell 61.5%").
- **Wide tables are no longer summed.** One column per series (Signups,
  Churn) now follows the largest series instead of adding unlike measures
  into a "Total value".
- **The no-number fallback headline states a direction.** It reads "Net
  income fell between 2020 and 2023" instead of "How net income has moved".
- **Daily dates read as dates**: "on Jan 2, 2024", not "in 2024-01-02".
- When the trend scene already names the biggest mover, the slope scene
  states the comparison ("No source moved more than Gas") instead of
  repeating the trend headline.
- **The vetter checks direction verbs.** "rose 12%" with a negative value now
  fails; previously only "increased" and "decreased" were checked. The full
  list is: rose, fell, grew, gained, climbed, jumped, dropped, declined, lost,
  shrank, slid and slumped.

### Fixed
- **`draft()` no longer writes a percent change across zero** (#17).
  - A series that ends negative gets "Net income turned negative in 2023"
    instead of "fell 200%".
  - The slope scene drops "the biggest shift of any X" when a category
    couldn't be measured on the same scale. A category that crossed zero is
    named ("E turned negative by 2024").
  - "Sharpest move" commentary is only written when every step was
    measurable.
  - The vetter fails any percent claim below -100%.

## [0.7.0] - 2026-11-05

### Added
- **`dstory.draft(df, title=...)`: zero-config DataFrame to vetted story**
  (#11, milestone 1). Profiles columns (temporal / categorical / measure,
  cardinality, ID-like), melts wide tables with `to_long()`, and picks scenes
  by rule: time x measure → `line-reveal`, category x first/last period →
  `slope-chart`, shares summing to ~100 (or ~1) → `waffle`, otherwise one safe
  `bar-steps` scene. Headlines, commentary and alt text come from computed
  facts; every number in the prose is a `compute_claim()` claim the vetter
  checks. Returns a `Draft` with `.story`, `.scenes`, `.explain()` and
  `.to_project(path)`. Deterministic and offline; needs the `[prep]` extra.
- **`build()` accepts a pandas DataFrame**: it drafts first, then builds.
  Dict and `Story` input behave exactly as before.
- Docs: a gallery example drafting one CSV in two themes (`docs/drafted/`,
  generated by `scripts/build_draft_example.py`).

### Changed
- **`build(vet=True)` now runs the browser checks by default** (#12) whenever
  Playwright and Chromium are available, including inside Jupyter (the checks
  run off the notebook's event loop). When they can't run, `build()` warns, the
  skipped dimensions are flagged (`report.skipped`, `report.complete`, and
  `"skipped"` in the JSON report), and `dstory vet --no-browser` prints
  `PASS (partial)`. Pass `browser=False` to keep static-only vetting.
- **Drifted claims block the build** (#9), as the README promised.
  `build()` and `dstory bundle` raise `ClaimDriftError` before writing
  anything; opt out with `check_claims=False` / `--no-check-claims`.
- **An unknown `meta.theme` is an error** (#13) listing the presets, instead
  of a silent fallback to `editorial-noir`.

### Fixed
- **Vizzu overdraw:** the README quickstart now groups its bars, so churn is
  visible next to signups. The vetter fails any Vizzu bar/area frame whose
  `color` series isn't stacked or grouped when the data shows the marks
  overlapping (#7).
- **Vizzu channel typos fail at build time:** a frame channel naming a series
  the scene doesn't declare is a validation error, not a browser crash (#12).
- **Slides mode:** charts fit their card at laptop sizes (1280×720 and up) for
  every cookbook recipe; the source line clears the slide controls. The
  browser vetter fails a chart that overflows its card (#8).
- **Vizzu scenes no longer hold back the charts after them** (#16). Non-Vizzu
  scenes paint immediately, and Vizzu scenes start up in parallel. Offline, a
  Vizzu mount shows its `alt` text instead of an empty box.
- `fmt_compact(999_999)` is `"1M"`, not `"1000K"` (#10), and `digits=0` no longer
  strips significant zeros (`10` stayed `"1"`).

## [0.6.0] - 2026-11-02

### Fixed
- **Security: story text can no longer break out of the bundled data script**
  (#1). `data.json` is embedded with every `<` escaped as `<` (plus
  U+2028/U+2029), so a `</script>` in a title or dataset value stays inert.
- **`compute_claim()` claims always pass vetting, and never state the wrong
  unit** (#2). `compute_ratio()` / `compute_pct_change()` return unit-tagged
  floats (`Ratio`, `PctChange`); claims record `"unit": "ratio" | "pct"`; prep
  and vet share one phrase-window table (`RATIO_WINDOWS`). A 3.4× ratio now
  reads "increased by 240.0%", not "3.4%"; a +2% change is never "doubled".
  The vetter honours `unit`, checks "increased/decreased by N%" direction, and
  no longer fails correct "decreased by N%" claims. `compute_claim()` takes a
  `kind=` argument and warns on an untagged float.
- **The browser vetter checks that charts paint** (#3). Every scene with a
  `dataset` or `frames` must draw something in its mount (svg marks, a sized
  canvas, an image, or HTML), and a recipe's `empty dataset` warning fails
  "Renders correctly".
- **The CLI no longer crashes on non-UTF-8 consoles** (#4). Unencodable
  characters print as `?` instead of raising `UnicodeEncodeError`.
- **No false dual-axis / 3D notes on `--vendor` bundles** (#5). Static checks
  skip `<script data-vendored>` library code.

## [0.5.1] - 2026-06-13

### Fixed
- **Vizzu scenes no longer queue a backlog of morphs on fast scrolling.**
  `chart.animate()` queues animations, so scrolling quickly through N steps
  played N back-to-back ~1s morphs while the text ran ahead of the chart.
  The runtime now uses a latest-wins scheduler: while a morph is in flight,
  only the newest requested frame is kept and stale intermediates are skipped.
  Same fix applies in slides mode (rapid arrow-keying). Authoring note:
  frames should stay self-contained (set `geometry`, `coordSystem`, and any
  `align`/`split` resets explicitly in every frame), since intermediate
  frames may be skipped. The prebuilt demo story on the docs site was
  patched in place; the morph showcase was rebuilt from the new template.

## [0.5.0] - 2026-06-12

The on-ramp release: pure-Python authors can now go DataFrame → story.html
without writing JavaScript, and authors who want the bespoke-D3 look start
from finished recipes instead of a blank file.

### Added — cookbook
- 10 complete, themed, responsive scene renderers shipped as package data:
  `line-reveal`, `slope-chart`, `beeswarm`, `bump-chart`, `annotated-scatter`,
  `waffle`, `dot-timeline`, `small-multiples`, `bar-steps` (scrolly),
  `range-dots`. All theme-token driven, `prefers-reduced-motion` aware, with
  dataset/config contracts documented in each file header.
- `dstory scene <slug> <id> --from <recipe>` copies a recipe in (wired,
  scene-id filled); `dstory recipes` lists them. Python: `recipe_js()`,
  `list_recipes()`, `recipe_demo()` (a runnable scene + dataset per recipe —
  also the fixture the gallery and e2e tests are built from).
- Rendered gallery at `docs/gallery/` (GitHub Pages), generated by
  `scripts/build_gallery.py`. Every recipe is browser-verified: the e2e suite
  builds a story containing all 10 demos and asserts each paints real marks
  with no page errors.

### Added — one-call build
- `dstory.build(story, path, *, scenes=, vendor=, vet=, browser=)` — Story
  (or plain dict) → scaffold + data.json + scene files + bundle (+ vet) in a
  single call. Returns `BuildResult` with `.html`, `.bundle`, `.report`,
  `.passed`. Makes the notebook path one cell.

### Added — offline self-containment
- `dstory bundle --vendor` (Python: `bundle(vendor=True)`) downloads and
  inlines the CDN runtime libs (d3, scrollama, Motion incl. a UMD bridge), so
  the bundled story works with no network at all. Vizzu can't be vendored (it
  streams WebAssembly); its loader is dropped when the story has no vizzu
  scenes, kept with a warning when it does.
- The bundler now warns loudly when a local `<script src>` / stylesheet
  `<link>` / `<img>` survives bundling (e.g. single-quoted attributes that
  dodge the inlining regexes) — previously this produced a silently
  non-self-contained file.

### Fixed
- `references/vizzu-chart-gallery.md` had snippets that break on Vizzu 0.18
  (the version the template loads): `align`/`split` belong on the axis
  *channel*, not the config root (root-level `align` errors out and kills the
  frame sequence), and stacking is explicit — composition charts (pie, donut,
  stacked column/area, streamgraph, waterfall, violin) need
  `[dimension, measure]` on the stacking axis or the marks silently overdraw.
  All affected snippets corrected; a "gotchas" section documents both traps.

### Changed
- README repositioned around the no-JavaScript path (Vizzu scenes + cookbook
  + `build()`), with an honest comparison table (Streamlit, ipyvizzu-story,
  Quarto, Flourish).
- CI gains a browser e2e job (installs Chromium; the Playwright tests no
  longer silently skip on every push).
- Dev environment pins `greenlet<3.5` on Windows (3.5.x wheels DLL-fail on
  some setups, breaking Playwright).

## [0.4.0] - 2026-06-12

### Added — audience reach & accessibility
- `meta.lang` and `meta.dir` (`ltr`/`rtl`/`auto`) — applied to `<html lang dir>`
  at bundle time and runtime. RTL stories now render correctly.
- `scene.alt` — text alternative for charts, wired to `role="img"` +
  `aria-label` on the chart mount. The vetter (static and browser-side) notes
  chart-bearing scenes that lack it.
- Skip-to-content link (visible on keyboard focus) and `aria-live` on the
  slides position indicator.
- Audience-aware readability check: the vetter scores story prose with Flesch
  reading ease and notes when it's harder than the declared `meta.audience`
  warrants (advisory note, not a failure; English prose only).
- Print stylesheet — browser print now yields a clean PDF handout (no
  atmosphere overlays, unpinned scrollytelling, page-break hints).

### Added — visual polish
- Reading progress bar in scroll mode (thin accent rail, top of viewport).
- Gentle entry reveal for `simple` scenes (headline → commentary → chart);
  honors `prefers-reduced-motion`.
- `meta.hero_image` — full-bleed hero background image with a theme-aware
  scrim for headline legibility. Project-local paths are inlined as data URIs
  at bundle time; remote URLs pass through.

### Added — sharing & delivery
- Bundler injects `<meta name="description">` + Open Graph + Twitter card
  tags from story meta (`meta.description` falls back to deck, then subtitle;
  optional `meta.share_image` for the card image).
- `Brand.favicon` is now wired in: inlined as a data-URI `<link rel="icon">`
  at scaffold time (it was previously parsed but unused).
- Slides mode deep-linking: the URL hash tracks `#slide-N` so a specific
  slide can be shared/bookmarked; incoming `#slide-N` links are honored.

### Added — claims & prep
- `quintupled` added to the claim vocabulary in **both** `prep` and the
  vetter (kept in sync, as with the existing phrases).
- `prep.fmt_compact()` (1234567 → "1.2M") and `prep.fmt_pct()` formatting
  helpers — no pandas required.

### Added — CLI & DX
- `dstory preview <slug>` — local dev server (unbundled projects fetch
  data.json, which browsers block under `file://`).
- `dstory scene <slug> <id> --kind <kind>` — write a starter scene script
  with the correct renderer contract for its kind (scrolly → `onStep`,
  pinned → `onProgress`, …) and wire it into index.html. Also available as
  `dstory.starter_scene_js()`.

### Changed
- **Playwright removed from core dependencies** — it was both a core dep and
  the `[vet]` extra; the README always documented it as optional. Core
  install is now pydantic + click + rich only.
- Browser vetting additionally flags chart mounts without `aria-label`
  (as notes) and `vet.run_browser_checks()` now returns a 4-tuple
  `(renders, visual, issues, notes)`.

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
