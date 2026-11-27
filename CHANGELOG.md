# Changelog

All notable changes to `dstory` are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.15.4] - 2026-11-27

### Fixed

- The claim drift check now reads the common ways of stating a change that it
  used to miss (#49): "cut in half", fractions ("fell by a third", "rose by a
  quarter", "down two-thirds", "three-quarters"), "per cent" and "pct",
  one-word "tenfold" / "threefold", and "twice as many". A headline that says
  "cut in half" over a 20% fall now stops `dstory bundle` and fails
  `dstory vet`.
- A claim's own `text` is held to the same phrases as scene prose: one parser
  reads both, so "fell by half", "three times higher" or "ten-fold" in a
  claim that contradicts its value now blocks the build too.

## [0.15.3] - 2026-11-26

### Fixed

- In scroll mode a `simple` scene now fills its column (56rem, or its
  `width`) whatever its headline (#48). It used to shrink to fit its text, so
  a short headline like "Sales rose" got a 300 px chart with 6 px labels on a
  1440 px screen, and charts changed width from scene to scene. Scrolly
  scenes get the same fix. Re-run `dstory bundle` to pick it up.
- `dstory vet` fails a scroll-mode scene that is narrower than 3/4 of its
  column, so bundles made by 0.15.2 or older are caught.

## [0.15.2] - 2026-11-25

### Security

- `dstory bundle` no longer inlines any file that `meta.hero_image` names
  (#47). A `data.json` could point it at `../../.aws/credentials` or an
  absolute path, and the file shipped base64-encoded inside the story.
  `hero_image` is now inlined only from inside the project, and only when it
  is an image; otherwise it is dropped with a warning.
- Local files that `index.html` inlines must match their tag: `.css` for a
  stylesheet, `.js` for a script, an image for `<img>`. Under `dstory mcp`,
  none may come from outside `--root`. From the CLI, an asset outside the
  project is still inlined, with a deprecation warning.
- `dstory vet` fails a bundle whose `hero_image` or `<img>` carries a data
  URI that is not an image, which catches stories bundled by 0.15.1 or older.

## [0.15.1] - 2026-11-24

### Fixed
- `dstory vet --data data.json` now checks that the file it vets carries that
  data (#45). Every check read `data.json`, but readers see the copy inlined
  in story.html, so a stale bundle (data.json edited, `dstory bundle` not
  re-run), or `--data` from another story, got "safe to deliver". Data
  fidelity now compares the inlined datasets, scenes and claims with
  `data.json` and names the first difference: "Dataset 'rev' in story.html
  differs from data.json (row 1, value: 100 in story.html vs 900 in
  data.json). The bundle is stale ...: re-run `dstory bundle`."
- `to_records()` writes null for `pd.NA` from pandas' nullable dtypes
  (`Int64`, `Float64`, `string`, `boolean`, as from `convert_dtypes()` or
  `read_csv(dtype_backend="numpy_nullable")`) and for NaN in numpy float32
  columns (#46). `build()` crashed with `PydanticSerializationError` before.

## [0.15.0] - 2026-11-23

### Security
- Story data can no longer run script in the reader's browser (#44).
  `meta.lang` went into `<html lang="...">` unescaped, and `extra_css` could
  close its own `<style>` block, so a data.json written by someone else (a
  teammate, an AI agent, a scraped config) could inject a `<script>`, and
  `dstory vet` still said "safe to deliver". `meta.lang` is now
  attribute-escaped, with a warning when it is not a language tag. "</style"
  in any inlined CSS is neutralised, with a warning for `extra_css`. A source
  `url` that is not http(s), mailto or relative (`javascript:`, `data:`) is
  shown as plain text. The vetter fails each of these, and any markup between
  `<html>` and `<head>`.

### Added
- A mistyped scene or step key is no longer dropped without a word (#34).
  `build()` (as a UserWarning) and `dstory bundle` warn once per unknown key
  that looks like a field, with a did-you-mean: `headine` -> `headline`,
  `alt_text` -> `alt`, `source` -> `source_line`, a step's `text` ->
  `commentary`. Keys that resemble no field stay silent, since custom
  renderers may read their own.

### Changed
- `compute_claim()` now writes claims the way `dstory draft` does (#39). A
  change of 5.5x or more reads "rose 12-fold" instead of "increased by
  1100.0%", and a change that rounds to 0.0% reads "held steady, a 0% change"
  instead of "increased by 0.0%". Both forms pass the vetter. Pass
  `style="percent"` (also on `derive_claim_text`) to keep the old wording.

### Fixed
- The CLI no longer drops text in square brackets. Without Playwright,
  `dstory vet` and `dstory draft` told you to run `pip install "dstory"`
  because the console read `[vet]` as styling; it now says
  `pip install "dstory[vet]"`. Vet issues, notes, bundle warnings and output
  paths are printed as written.
- A numeric claim with no `from` (hand-written, or drafted before 0.14.3)
  now gets a note from `dstory vet` and a warning from `dstory bundle` naming
  it: edits to data.json are not checked against it. It still builds; re-run
  `dstory draft` or add `from` to tie it to the data.
- The docs site now deploys from the latest release tag instead of main, so it
  no longer documents features PyPI does not have yet (#32).

## [0.14.6] - 2026-11-22

### Fixed
- A percent change or ratio from a negative base no longer flips the story
  (#42). `compute_pct_change(after=-300, before=-100)` returned +200, so
  `compute_claim()` wrote "Net income tripled" under a loss that tripled, and
  the vetter passed it. `compute_pct_change()` and `compute_ratio()` now raise
  `ValueError` for a negative base, as they already did for zero, and as
  `dstory draft` already refused one. `compute_claim()` raises for a change
  across zero (100 to -50, "-150%") instead of writing a claim the vetter
  blocks. The vetter fails a claim whose `from` has a negative base, and its
  sign-change message now mentions "turned positive" too.
- `to_records()` and `to_long()` write a date column (every value midnight,
  no timezone) as "2024-01-01", not "2024-01-01T00:00:00" (#43), and `NaT`
  as null instead of "NaT". The line-reveal, dot-timeline and small-multiples
  recipes also read "2024-01-01T00:00:00", so data written by older versions
  still draws. When a recipe drops every row, it now says how many rows it
  had, which format it expected and a sample row, instead of "empty dataset".

## [0.14.5] - 2026-11-21

### Fixed
- One long word no longer squeezes a chart to a sliver (#41). In scrolly and
  Vizzu scenes, a German compound ("Photovoltaikfreiflächenanlagen...") or a
  URL in a step or frame headline widened the text column until the chart was
  54 px wide at 768 px, and the page scrolled sideways. The two columns now
  keep their halves (`minmax(0, 1fr)`, also in slides mode and on phones), and
  headings, steps and prose break a word only when it can't fit. When custom
  CSS still crowds a chart, `dstory vet` names the long word in that scene's
  text instead of pointing at the data.

## [0.14.4] - 2026-11-20

### Fixed
- A drafted bar chart of more than 12 rows no longer names the wrong row as
  lowest (#40). `dstory draft` kept only the 12 largest, then wrote "X ranks
  last" and "X has the lowest ..." about the 12th, and the vetter passed it.
  The text now ranks every row, the chart keeps the 11 largest plus the true
  lowest, and both the step and the alt text tell the reader the chart is a
  subset. The "lowest" statement is a claim (`c-rank-low`) whose `from`
  ranking is rechecked by bundle and vet, so an edit to data.json that moves
  the bottom fails. A gap of 5.5x or more now reads "CA's population is
  67-fold that of WY" instead of "6624% higher".

## [0.14.3] - 2026-11-19

### Fixed
- Claims can no longer go stale when the data changes (#38). Edit a drafted
  story's data.json as the README says, and a headline like "Coal share fell
  24 points, the biggest shift of any source" used to ship next to a chart
  showing a 2-point fall. Every claim `dstory draft` writes now records where
  its number comes from (`"from"`: dataset rows, the operation, and any
  "biggest" / "largest" / "least" ranking). `dstory bundle` (ClaimDriftError)
  and `dstory vet` (Data fidelity) recompute it and fail on a mismatch, naming
  the claim with the old and new numbers. Hand-written claims opt in with
  `compute_claim(..., from_=claim_from(...))`.

## [0.14.2] - 2026-11-18

### Fixed
- The template-text check from 0.14.1 no longer blocks real prose (#37).
  "Super Bowl XXX", "2025 figures TBD", "most new capacity goes here" and
  "table {A1}" pass. A field that is only a marker ("TBD", "XXX"), a note to
  self ("TBD: the June number"), a bracketed marker ("[TBD]", "(XXX)"),
  `{{…}}`, `[Insert …]`, a template slot such as `{phrase}` or `{headline}`,
  "Headline goes here" and FIXME / TKTK still fail. A marker that could be
  either is now a note, and `meta.vet.allow_text: ["Super Bowl XXX"]`
  silences the check for copy you mean.
- `Report.to_json()` / `dstory vet --json` now fill `scene` for editorial
  failures, so an agent can route the fix without parsing the message (#37).
- Slides on a phone stack the chart over the text, as scroll mode does (#36).
  Scrolly and Vizzu slides kept two columns at every width, squeezing the
  chart to 66 px of a 390 px screen.
- The vetter renders at a 390 px phone instead of 480 px and fails a chart
  squeezed narrower than 240 px and half the screen, which neither overflows
  nor fails to paint, so it used to pass (#36).

## [0.14.1] - 2026-11-17

### Fixed
- The vetter fails a story that still has template text in it (#35). The
  "Untitled Story" title that `dstory init` writes, `{{source}}` or `{pct}`
  slots, `[Insert headline here]`, "Your commentary goes here.", and bare
  XXX / TBD / FIXME / TKTK markers in any reader-facing field (meta title,
  subtitle, deck, author, credits, source names; scene headline, commentary,
  alt, source line, steps, frames, annotations) now fail Editorial integrity,
  and each failure names the field, e.g. `scene 'scene-trend' headline still
  has template text`. Text a scene hides (`chrome: false`) is not checked.
  `dstory bundle` also warns when `meta.title` is still the default.

## [0.14.0] - 2026-11-16

### Added
- `dstory mcp`: dstory as an MCP server, so Claude Code, Claude Desktop, Cursor
  or any MCP client can draft, vet, look at and bundle a story, with the
  vetter as its feedback loop (#21, milestone 1). Tools: `draft_story`,
  `vet_story`, `get_screenshot` (an image the assistant can see) and
  `bundle_story` (a drifted claim comes back as data, not a traceback).
  Paths are confined to `--root`. Install with `pip install "dstory[mcp]"`;
  without it, `dstory mcp` prints the install line.
- `dstory vet --json`: the report as JSON, the same schema `vet_story`
  returns, with a flat `failures` list naming the claim and scene behind each
  failure. The exit code is unchanged. `Report.to_json()` gains `skipped`,
  `failures` and a `key` per dimension; existing fields are unchanged.
- `dstory.agent`: the tools as plain functions returning dicts.

### Fixed
- The vetter's PII check no longer blocks ordinary numbers (#33). It scanned
  all of data.json as text, so an 11-digit budget ($12.5B) or a computed mean
  such as 14285.714285714286 failed as a "phone-shaped number" and stopped
  `dstory draft` and `build(vet=True)`. It now reads only strings (numbers are
  measurements, not contact details), matches phones as people write them
  (`555-123-4567`, `(555) 123-4567`, `555.123.4567`, `+1 555 123 4567`, which
  it used to miss), and names the value and where it is, e.g.
  `'555-123-4567' at datasets.d[1].contact`.

## [0.13.2] - 2026-11-15

### Fixed
- A thousands separator no longer splits a number in the vetter (#31).
  "Revenue fell 1,200%" against a +1200% claim passed and bundled, while a
  correct "a 1,200% increase" was blocked as "200%", and so was a correct
  hand-written claim. Claim text and scene prose now read "1,200" as 1200 in
  every check (percent, points, N-fold, Nx, N times), and a misgrouped
  "1,2000%" is checked as 12000 rather than skipped.
- CLI error messages and install hints keep their square brackets. Rich read
  `[prep]` as markup, so `dstory draft` without pandas told you to run
  `pip install "dstory"`, which installs nothing new; it now says
  `pip install "dstory[prep]"`. Any error text with brackets in it (claim ids,
  extras) is printed as written.

## [0.13.1] - 2026-11-14

### Fixed
- The vetter now catches scene prose that contradicts its claim in percent,
  "Nx" / "N times" or direction, not only in ratio words (#29). "Churn fell
  30%" against a claim that churn rose 30%, "Signups grew 5x" against a 2.9x
  ratio, or "up 5 points" against a 2-point claim now fail data fidelity, and
  `build()` / `dstory bundle` stop with `ClaimDriftError`. A scene whose claims
  are all in points (as drafted stories' are) can no longer say "quintupled"
  or "rose 30%" with no claim of that kind behind it. Figures with no
  direction (a level or a share) are not checked. If a scene states a change
  you have no claim for, register one, or bundle with `--no-check-claims`.

## [0.13.0] - 2026-11-13

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
- **Upgrading dstory upgrades your projects.** `dstory bundle` (and
  `bundle()`) now refreshes a project's `story.js` / `story.css` when they are
  untouched copies from any earlier release, so runtime fixes (#27, #28)
  reach existing projects with no action. Edited copies are kept with a
  warning. New `dstory upgrade SLUG [--force]` shows the state, restores a
  deleted file, or replaces edited ones after backing them up to
  `.dstory-backup/`. `--no-upgrade` / `upgrade=False` opts out.

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
  existing CLI project gets it on its next `dstory bundle` (#27).
- Scrolly and pinned scenes show their own `headline` and `commentary`. They
  were accepted but never rendered, so the scene `dstory draft` writes for a
  plain ranking ("Red leads on wins") shipped without its headline. They now
  open the text column of a scrolly scene and sit above a pinned graphic (and
  above the active step on a slide); `"chrome": false` still hides them. The
  vetter now grades only text a reader can see: the placeholder scan reads the
  page, the scene prose and the data tables instead of the raw data.json, and
  hidden headlines are not scored. Existing CLI projects get it on their next
  `dstory bundle` (#28).

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
