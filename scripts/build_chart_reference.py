"""Render the bundled Vizzu chart-gallery reference (markdown, package data)
as a docs page at docs/charts/index.html, styled to match the docs site.

Usage:  uv run python scripts/build_chart_reference.py   (needs dev deps)
"""

from __future__ import annotations

import sys
from importlib import resources
from pathlib import Path

import markdown

DOCS_CHARTS = Path(__file__).resolve().parent.parent / "docs" / "charts"

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>dstory — Vizzu chart reference</title>
<meta name="description" content="Every Vizzu chart shape as a copy-paste JSON snippet for dstory's kind:vizzu scenes — 4 geometries x 2 coordinate systems x 7 channels.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,700&family=Inter+Tight:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #14110f; --bg-elev: #1d1916; --ink: #f2ece2; --ink-soft: #b8af9f;
    --ink-faint: #7a7265; --accent: #ff5c1f; --accent-2: #e8b34b; --rule: #332d27;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--ink);
         font: 16px/1.6 "Inter Tight", system-ui, sans-serif;
         -webkit-font-smoothing: antialiased; }}
  .wrap {{ max-width: 52rem; margin: 0 auto; padding: 2.5rem 1.5rem 6rem; }}
  .crumb {{ font-family: "JetBrains Mono", monospace; font-size: 0.78rem; }}
  .crumb a {{ color: var(--ink-soft); }}
  h1 {{ font-family: "Fraunces", Georgia, serif; font-size: 2.6rem; line-height: 1.05;
       letter-spacing: -0.015em; margin: 1rem 0; }}
  h2 {{ font-family: "Fraunces", Georgia, serif; font-size: 1.7rem; margin: 3rem 0 0.75rem; }}
  h2::before {{ content: "§ "; color: var(--accent); font-size: 1rem; vertical-align: 0.2em; }}
  h3 {{ font-weight: 600; font-size: 1.05rem; margin: 2rem 0 0.5rem; color: var(--accent-2); }}
  p, li {{ color: var(--ink-soft); }}
  strong {{ color: var(--ink); }}
  em {{ color: var(--ink-faint); }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  hr {{ border: 0; border-top: 1px solid var(--rule); margin: 3rem 0; }}
  pre {{ background: var(--bg-elev); border: 1px solid var(--rule); border-radius: 6px;
        padding: 0.9rem 1.1rem; overflow-x: auto; font-size: 0.8rem; line-height: 1.55; }}
  code {{ font-family: "JetBrains Mono", monospace; }}
  p code, li code, td code {{ background: var(--bg-elev); border: 1px solid var(--rule);
        border-radius: 3px; padding: 0.08rem 0.35rem; font-size: 0.82em; color: var(--ink); }}
  pre code {{ background: none; border: 0; padding: 0; color: var(--ink); }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.9rem; margin: 1rem 0; }}
  th, td {{ text-align: left; padding: 0.5rem 0.9rem 0.5rem 0; border-bottom: 1px solid var(--rule);
           color: var(--ink-soft); }}
  th {{ color: var(--ink); }}
  ol li, ul li {{ margin: 0.3rem 0; }}
  footer {{ border-top: 1px solid var(--rule); margin-top: 4rem; padding-top: 1.5rem;
           font-family: "JetBrains Mono", monospace; font-size: 0.78rem; color: var(--ink-faint); }}
  footer a {{ color: var(--ink-soft); }}
</style>
</head>
<body>
<div class="wrap">
  <p class="crumb"><a href="../index.html">dstory docs</a> / chart reference ·
     <a href="../morphs/index.html">see it morph live →</a></p>
{body}
  <footer>
    This page is generated from the reference shipped inside the package
    (<code>src/dstory/references/vizzu-chart-gallery.md</code>) ·
    <a href="../index.html">docs</a> ·
    <a href="../morphs/index.html">morph showcase</a> ·
    <a href="../gallery/index.html">cookbook gallery</a>
  </footer>
</div>
</body>
</html>
"""


def main() -> int:
    md_text = (
        resources.files("dstory.references")
        .joinpath("vizzu-chart-gallery.md")
        .read_text(encoding="utf-8")
    )
    body = markdown.markdown(md_text, extensions=["fenced_code", "tables"])
    DOCS_CHARTS.mkdir(parents=True, exist_ok=True)
    out = DOCS_CHARTS / "index.html"
    out.write_text(TEMPLATE.format(body=body), encoding="utf-8")
    print(f"  wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
