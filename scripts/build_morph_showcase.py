"""Generate the morph showcase: a live, scrollable vizzu story demonstrating
the breadth of the morph space (bar → polar → pie → bubble → treemap, etc.),
built with dstory itself and copied to docs/morphs/index.html.

Every frame sets geometry AND coordSystem explicitly — vizzu configs merge
differentially, so an unset coordSystem would leak from the previous frame
(and scrolling backwards would replay frames out of order).

Usage:  uv run python scripts/build_morph_showcase.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from dstory import build

DOCS_MORPHS = Path(__file__).resolve().parent.parent / "docs" / "morphs"

REGIONS = [
    {"Region": "Asia-Pacific", "Sales": 4200},
    {"Region": "Europe", "Sales": 3100},
    {"Region": "North America", "Sales": 2800},
    {"Region": "Latin America", "Sales": 1300},
    {"Region": "Africa", "Sales": 900},
]

TIMELINE = [
    {"Year": str(y), "Category": c, "Sales": v}
    for c, series in {
        "Hardware":  [320, 340, 310, 290, 260, 240],
        "Software":  [180, 220, 290, 380, 470, 560],
        "Services":  [150, 170, 210, 260, 330, 410],
        "Licensing": [90, 95, 100, 100, 105, 110],
    }.items()
    for y, v in zip(range(2019, 2025), series)
]

COUNTRIES = [
    {"Country": "Norway", "Continent": "Europe", "GDP": 82, "Lifespan": 83.2, "Pop": 5},
    {"Country": "Germany", "Continent": "Europe", "GDP": 54, "Lifespan": 81.1, "Pop": 84},
    {"Country": "Poland", "Continent": "Europe", "GDP": 36, "Lifespan": 77.9, "Pop": 38},
    {"Country": "Japan", "Continent": "Asia", "GDP": 42, "Lifespan": 84.7, "Pop": 124},
    {"Country": "South Korea", "Continent": "Asia", "GDP": 47, "Lifespan": 83.2, "Pop": 52},
    {"Country": "India", "Continent": "Asia", "GDP": 8, "Lifespan": 70.2, "Pop": 1430},
    {"Country": "United States", "Continent": "Americas", "GDP": 70, "Lifespan": 78.9, "Pop": 335},
    {"Country": "Brazil", "Continent": "Americas", "GDP": 16, "Lifespan": 75.7, "Pop": 216},
    {"Country": "Nigeria", "Continent": "Africa", "GDP": 5, "Lifespan": 54.6, "Pop": 224},
    {"Country": "South Africa", "Continent": "Africa", "GDP": 14, "Lifespan": 65.3, "Pop": 60},
]

SKILLS = [
    {"Skill": s, "Player": p, "Score": v}
    for p, scores in {
        "Veteran": {"Pace": 62, "Vision": 95, "Passing": 91, "Defense": 78, "Finishing": 84},
        "Rookie":  {"Pace": 94, "Vision": 61, "Passing": 70, "Defense": 55, "Finishing": 72},
    }.items()
    for s, v in scores.items()
]


def _f(headline, commentary, channels, geometry, coord="cartesian", **extra):
    config = {"channels": channels, "geometry": geometry, "coordSystem": coord, **extra}
    return {"headline": headline, "commentary": commentary, "config": config}


STORY = {
    "meta": {
        "title": "The Morph Space",
        "subtitle": "A dstory vizzu showcase",
        "deck": "Four geometries, two coordinate systems, seven channels. "
                "The animation isn't a chart type — it's the transition between any two. "
                "Scroll, and hold on to the colors.",
        "author": "dstory",
        "published": "2026",
        "theme": "data-fi",
        "description": "A live demonstration of dstory's declarative vizzu morphs: "
                       "bar to pie to bubble to treemap, and beyond.",
        "sources": [{"name": "Synthetic demo data — every number invented for legibility"}],
    },
    "scenes": [
        {
            "id": "scene-five-lenses", "kind": "vizzu", "dataset": "regions",
            "headline": "One dataset, five visual logics",
            "alt": "An animated sequence showing the same five regional sales values as a "
                   "column chart, radial bars, a pie, packed bubbles, and a treemap.",
            "source_line": "Synthetic data. Total sales by region, five ways.",
            "series": [
                {"name": "Region", "type": "dimension"},
                {"name": "Sales", "type": "measure"},
            ],
            "frames": [
                _f("Start flat: a column chart",
                   "Five regions, one measure. Height carries the value.",
                   {"x": "Region", "y": "Sales", "color": "Region", "label": "Sales"},
                   "rectangle"),
                _f("Wrap the axis: radial bars",
                   "Same channels, polar coordinates. The x-axis curls into a circle.",
                   {"x": "Region", "y": "Sales", "color": "Region", "label": None},
                   "rectangle", "polar"),
                # Pie wedges must STACK on x — [dimension, measure] — or the
                # five arcs all start at angle zero and overdraw each other.
                _f("Drop an axis: a pie",
                   "Move the measure onto x and the wedges become parts of a whole.",
                   {"x": {"set": ["Region", "Sales"]}, "y": None,
                    "color": "Region", "label": "Region"},
                   "rectangle", "polar"),
                _f("Change geometry: packed bubbles",
                   "No axes at all now — area carries the value, the layout packs itself.",
                   {"x": None, "y": None, "size": "Sales", "color": "Region", "label": "Region"},
                   "circle"),
                _f("Tile the plane: a treemap",
                   "Same areas, squared off. Five frames, zero re-orientation — the colors never moved.",
                   {"size": "Sales", "color": "Region", "label": "Region"},
                   "rectangle"),
            ],
        },
        {
            "id": "scene-time", "kind": "vizzu", "dataset": "timeline",
            "headline": "Three temporal logics",
            "alt": "An animated sequence showing six years of sales by category as a stacked "
                   "column chart, then a flowing streamgraph, then separated ribbon lines.",
            "source_line": "Synthetic data. Revenue by category, 2019–2024.",
            "series": [
                {"name": "Year", "type": "dimension"},
                {"name": "Category", "type": "dimension"},
                {"name": "Sales", "type": "measure"},
            ],
            "frames": [
                # Vizzu 0.18: align lives on the axis CHANNEL, and stacking is
                # explicit — y must carry [dimension, measure], it is not
                # implied by the color channel.
                _f("Stacked columns: the totals story",
                   "Each year is a tower; categories stack inside it.",
                   {"x": "Year", "y": {"set": ["Category", "Sales"], "align": "none"},
                    "color": "Category"},
                   "rectangle"),
                _f("Streamgraph: the flow story",
                   "Same stack, center-aligned and smoothed — composition over time as a current.",
                   {"x": "Year", "y": {"set": ["Category", "Sales"], "align": "center"},
                    "color": "Category"},
                   "area"),
                _f("Lines: the trajectory story",
                   "Unstack entirely. Now each category competes on its own terms — and software wins.",
                   {"x": "Year", "y": {"set": "Sales", "align": "none"}, "color": "Category"},
                   "line"),
            ],
        },
        {
            "id": "scene-encoding", "kind": "vizzu", "dataset": "countries",
            "headline": "Three encoding emphases",
            "alt": "An animated sequence showing ten countries as a GDP-versus-lifespan scatter, "
                   "then dots grouped by continent, then population-sized bubbles.",
            "source_line": "Synthetic data, loosely shaped like the classic development chart.",
            "series": [
                {"name": "Country", "type": "dimension"},
                {"name": "Continent", "type": "dimension"},
                {"name": "GDP", "type": "measure"},
                {"name": "Lifespan", "type": "measure"},
                {"name": "Pop", "type": "measure"},
            ],
            "frames": [
                _f("Scatter: the relationship",
                   "GDP per capita against life expectancy — each dot one country.",
                   {"x": "GDP", "y": "Lifespan", "color": "Continent", "noop": "Country",
                    "size": None, "label": None},
                   "circle"),
                _f("Dot plot: the comparison",
                   "Collapse x onto the continent. The within-group spread becomes the point.",
                   {"x": "Continent", "y": "Lifespan", "color": "Continent", "noop": "Country",
                    "size": None, "label": None},
                   "circle"),
                _f("Bubbles: the magnitude",
                   "Drop both axes; let population set the area. India was a small dot a moment ago.",
                   {"x": None, "y": None, "noop": None, "size": "Pop", "color": "Continent",
                    "label": "Country"},
                   "circle"),
            ],
        },
        {
            "id": "scene-radar", "kind": "vizzu", "dataset": "skills",
            "headline": "The polar wrap",
            "alt": "An animated sequence showing two player skill profiles as overlapping "
                   "lines, then wrapped into a radar chart.",
            "source_line": "Synthetic data. Two player profiles, five skills.",
            "series": [
                {"name": "Skill", "type": "dimension"},
                {"name": "Player", "type": "dimension"},
                {"name": "Score", "type": "measure"},
            ],
            "frames": [
                _f("Two profiles as lines",
                   "Five skills along x, one line per player.",
                   {"x": "Skill", "y": "Score", "color": "Player"},
                   "line"),
                _f("Wrap: a radar chart",
                   "Identical channels, polar coordinates. The endpoints join and the shapes become signatures.",
                   {"x": "Skill", "y": "Score", "color": "Player"},
                   "line", "polar"),
            ],
        },
        {
            "id": "scene-outro-note", "kind": "simple", "width": "narrow",
            "headline": "Thirteen frames. Zero JavaScript.",
            "commentary": "Everything above is declared in data.json — channels, geometry, "
                          "coordinate system per frame. The full configuration space is "
                          "documented in the chart reference, with a copy-paste snippet "
                          "for every shape.",
        },
    ],
    "datasets": {
        "regions": REGIONS,
        "timeline": TIMELINE,
        "countries": COUNTRIES,
        "skills": SKILLS,
    },
}


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="dstory-morphs-"))
    result = build(STORY, tmp / "morph-space", vet=True, browser=False)
    if not result.passed:
        for d in result.report.dimensions:
            for issue in d.issues:
                print(f"  VET ISSUE [{d.name}]: {issue}")
        return 1
    DOCS_MORPHS.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(result.html, DOCS_MORPHS / "index.html")
    print(f"  wrote {DOCS_MORPHS / 'index.html'} ({result.bundle.size_bytes / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
