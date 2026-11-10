"""Generate the zero-config gallery example: one small CSV drafted with
`dstory.draft()` and built in two themes, written to docs/drafted/.

Nothing here is hand-written story content: the scenes, headlines, claims and
alt text all come from draft(). Each build must pass the vetter (browser checks included when Chromium is installed).

Usage:  uv run --extra prep python scripts/build_draft_example.py
"""

from __future__ import annotations

import html as html_mod
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

import dstory

DOCS = Path(__file__).resolve().parent.parent / "docs" / "drafted"
CSV = DOCS / "mix.csv"
THEMES = ["warm-print", "data-fi"]
TITLE = "Gas took coal's place"
SOURCE = "Illustrative power-mix shares (synthetic data)"
# The second example: a spreadsheet export (numbers as text with thousands
# separators) of an additive measure, which gets the animated Vizzu opener.
GEN_CSV = DOCS / "generation.csv"
GEN_TITLE = "Solar and wind filled the gap coal left"
GEN_SOURCE = "Illustrative generation by source (synthetic data)"
# The third: 8 metros of very different sizes, built offline (--vendor).
# draft() picks small multiples with independent scales, and range-dots
# because 8 categories are too many for slope-chart labels.
METRO_CSV = DOCS / "metros.csv"
METRO_TITLE = "Every market cooled after 2021"
METRO_SOURCE = "Illustrative home sales by metro, in thousands (synthetic data)"


def main() -> int:
    df = pd.read_csv(CSV)
    tmp = Path(tempfile.mkdtemp(prefix="dstory-drafted-"))
    explain = ""
    for theme in THEMES:
        d = dstory.draft(df, title=TITLE, theme=theme, source=SOURCE)
        explain = d.explain()
        result = dstory.build(d.story, tmp / theme, scenes=d.scenes, vet=True)
        if not result.passed:
            for dim in result.report.dimensions:
                for issue in dim.issues:
                    print(f"  VET ISSUE [{dim.name}]: {issue}")
            return 1
        shutil.copyfile(result.html, DOCS / f"{theme}.html")
        print(f"  wrote {DOCS / f'{theme}.html'} ({result.bundle.size_bytes / 1024:.1f} KB)")

    g = dstory.draft(pd.read_csv(GEN_CSV), title=GEN_TITLE, theme="editorial-noir",
                     source=GEN_SOURCE)
    result = dstory.build(g.story, tmp / "generation", scenes=g.scenes, vet=True)
    if not result.passed:
        for dim in result.report.dimensions:
            for issue in dim.issues:
                print(f"  VET ISSUE [{dim.name}]: {issue}")
        return 1
    shutil.copyfile(result.html, DOCS / "generation.html")
    print(f"  wrote {DOCS / 'generation.html'} ({result.bundle.size_bytes / 1024:.1f} KB)")

    m = dstory.draft(pd.read_csv(METRO_CSV), title=METRO_TITLE, theme="minimal-light",
                     source=METRO_SOURCE)
    result = dstory.build(m.story, tmp / "metros", scenes=m.scenes, vendor=True, vet=True)
    if not result.passed:
        for dim in result.report.dimensions:
            for issue in dim.issues:
                print(f"  VET ISSUE [{dim.name}]: {issue}")
        return 1
    shutil.copyfile(result.html, DOCS / "metros.html")
    print(f"  wrote {DOCS / 'metros.html'} ({result.bundle.size_bytes / 1024:.1f} KB)")
    write_index(explain, g.explain(), m.explain())
    return 0


def write_index(explain: str, gen_explain: str = "", metro_explain: str = "") -> None:
    esc = html_mod.escape
    links = "\n".join(
        f'    <a class="card" href="{t}.html"><strong>{t}</strong><span>Open the story</span></a>'
        for t in THEMES)
    code = (
        'import pandas as pd, dstory\n\n'
        'df = pd.read_csv("mix.csv")            # year, source, share_pct\n'
        f'd = dstory.draft(df, title="{TITLE}", theme="warm-print",\n'
        f'                 source="{SOURCE}")\n'
        'print(d.explain())\n'
        'dstory.build(d.story, "mix", scenes=d.scenes, vet=True)\n\n'
        '# or, with no Python at all:\n'
        f'#   dstory draft mix.csv --theme warm-print --source "{SOURCE}"'
    )
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>dstory.draft: one CSV, two themes</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; padding: 3rem 1.5rem; background: #faf7f2; color: #1a1a1a;
         font: 16px/1.55 system-ui, sans-serif; }}
  main {{ max-width: 52rem; margin: 0 auto; }}
  h1 {{ font-size: 2.2rem; margin: 0 0 0.5rem; }}
  h2 {{ font-size: 1.15rem; margin: 2.25rem 0 0.5rem; }}
  p {{ color: #444; max-width: 60ch; }}
  pre {{ background: #f3efe8; padding: 0.9rem 1rem; border-radius: 6px; overflow-x: auto;
        font-size: 0.82rem; line-height: 1.45; }}
  .cards {{ display: grid; gap: 1rem; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }}
  .card {{ display: block; padding: 1.1rem 1.25rem; background: #fff; border: 1px solid #e4ded4;
          border-radius: 6px; text-decoration: none; color: inherit; }}
  .card span {{ display: block; color: #777; font-size: 0.85rem; margin-top: 0.25rem; }}
  footer {{ margin-top: 3rem; color: #777; font-size: 0.85rem; }}
  a {{ color: inherit; }}
</style>
</head>
<body>
<main>
  <h1>One CSV, two themes, zero config</h1>
  <p><code>dstory.draft()</code> profiled <a href="mix.csv">mix.csv</a>, picked the scenes,
     mapped the columns onto cookbook recipes and wrote every headline from computed
     facts. Each number in the prose is a registered claim the vetter checks.
     The same draft is built in two themes below.</p>
  <div class="cards">
{links}
  </div>
  <h2>The code</h2>
  <pre>{esc(code)}</pre>
  <h2>What <code>explain()</code> said</h2>
  <pre>{esc(explain)}</pre>
  <h2>A messy export, with an animated opener</h2>
  <p><a href="generation.csv">generation.csv</a> looks like a real spreadsheet export:
     every number is text with thousands separators ("410,000"). <code>draft()</code>
     reads the column as numbers and says so (a cell it can't read would be dropped and
     named). Because generation adds up across sources, the story opens with an animated
     Vizzu chart: the total as stacked bars, which morph into one line per source as you
     scroll.</p>
  <div class="cards">
    <a class="card" href="generation.html"><strong>editorial-noir</strong><span>Open the story</span></a>
  </div>
  <pre>dstory draft generation.csv --source "{esc(GEN_SOURCE)}"</pre>
  <pre>{esc(gen_explain)}</pre>
  <h2>Eight markets, eight sizes: small multiples and range-dots</h2>
  <p><a href="metros.csv">metros.csv</a> has home sales for 8 metros, from Phoenix (about
     90,000 a year) to Fargo (about 3,400). On one shared scale the small markets would be
     flat lines along the floor, so <code>draft()</code> gives each panel its own scale,
     labels it, and tells the reader to compare shapes, not heights. Eight categories are
     too many for slope-chart labels, so the before/after scene is a range-dots chart.
     This one is built with <code>--vendor</code>: it works with no network at all.</p>
  <div class="cards">
    <a class="card" href="metros.html"><strong>minimal-light, offline</strong><span>Open the story</span></a>
  </div>
  <pre>dstory draft metros.csv --vendor --theme minimal-light</pre>
  <pre>{esc(metro_explain)}</pre>
  <h2>Every chart ships its data</h2>
  <p>Open any story above and look under a chart: a collapsed <strong>Data</strong>
     panel holds an accessible table of the exact rows behind it, and a
     <strong>Download CSV</strong> link that works offline. Nobody wrote either: the
     bundler adds them to every scene with a dataset, and the vetter checks in a browser
     that each table and CSV match <code>data.json</code>. In slides mode, press
     <kbd>t</kbd>. Turn them off per scene with <code>"a11y": {{"table": false}}</code>, or for
     a whole bundle with <code>dstory bundle --no-a11y-extras</code>.</p>
  <h2>Every chart reads out loud</h2>
  <p>Press <kbd>Tab</kbd> until a chart is outlined, in any story above. A readout
     summarises it (for the metros: each city, from where it started to where it ended,
     and where it peaked). Then <kbd>&larr;</kbd> <kbd>&rarr;</kbd> step through the points
     (&ldquo;2019: homes sold 10.8 (Boise), 4 of 9&rdquo;), <kbd>&uarr;</kbd> <kbd>&darr;</kbd>
     switch series at the same date, <kbd>Home</kbd> and <kbd>End</kbd> jump to the ends,
     and <kbd>Esc</kbd> hands the keys back. The same text goes to screen readers through
     an <code>aria-live</code> region. It reads the data, not the drawing, so it works for
     recipes, hand-written D3 and Vizzu alike, and the vetter presses the keys to check
     it. Turn it off with <code>"a11y": {{"explorer": false}}</code>.</p>
  <footer>
    Generated by <code>scripts/build_draft_example.py</code> ·
    <a href="../index.html">docs</a> · <a href="../gallery/index.html">cookbook gallery</a> ·
    <a href="https://github.com/dkedar7/dstory">dkedar7/dstory</a>
  </footer>
</main>
</body>
</html>
"""
    (DOCS / "index.html").write_text(page, encoding="utf-8")
    print(f"  wrote {DOCS / 'index.html'}")


if __name__ == "__main__":
    sys.exit(main())
