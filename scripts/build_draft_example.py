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
    write_index(explain, g.explain())
    return 0


def write_index(explain: str, gen_explain: str = "") -> None:
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
