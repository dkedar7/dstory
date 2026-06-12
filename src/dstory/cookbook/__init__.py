"""Cookbook — complete, themed, copy-paste scene renderers.

Recipes bridge the gap between "I can't write D3" and "I want the bespoke
look": each is a finished `scenes/*.js` file (responsive, theme-token driven,
reduced-motion aware) that you copy into YOUR project and then own. There is
still no chart component API — a recipe is source code, not an abstraction.

Use via CLI:    dstory scene my-story scene-growth --from line-reveal
or Python:      write_scene(slug, "scene-growth", recipe_js("line-reveal", "scene-growth"))

Each recipe documents its dataset contract and `scene.config` options in its
header. `recipe_demo()` returns a ready-to-run scene + dataset pair for each —
used by the gallery, the tests, and as living documentation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from typing import Any

PACKAGE_COOKBOOK = "dstory.cookbook"

_SCENE_ID_TOKEN = "__SCENE_ID__"
_HEADER_RE = re.compile(r"^//\s*(recipe|kind|summary):\s*(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Recipe:
    name: str
    kind: str
    summary: str


def _read_recipe_source(name: str) -> str:
    try:
        return (
            resources.files(PACKAGE_COOKBOOK)
            .joinpath(f"{name}.js")
            .read_text(encoding="utf-8")
        )
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Recipe {name!r} not found. Available: {[r.name for r in list_recipes()]}"
        ) from e


def _parse_header(src: str, fallback_name: str) -> Recipe:
    fields = {m.group(1): m.group(2).strip() for m in _HEADER_RE.finditer(src)}
    return Recipe(
        name=fields.get("recipe", fallback_name),
        kind=fields.get("kind", "simple"),
        summary=fields.get("summary", ""),
    )


def list_recipes() -> list[Recipe]:
    """All bundled recipes, with their scene kind and one-line summary."""
    out: list[Recipe] = []
    for p in resources.files(PACKAGE_COOKBOOK).iterdir():
        if p.name.endswith(".js"):
            src = p.read_text(encoding="utf-8")
            out.append(_parse_header(src, p.name.removesuffix(".js")))
    return sorted(out, key=lambda r: r.name)


def recipe_kind(name: str) -> str:
    """The scene kind a recipe is written for (simple, scrolly, ...)."""
    return _parse_header(_read_recipe_source(name), name).kind


def recipe_js(name: str, scene_id: str) -> str:
    """Recipe source with the registration id filled in, ready for write_scene()."""
    return _read_recipe_source(name).replace(_SCENE_ID_TOKEN, scene_id)


# ---------- demo scene + dataset per recipe ----------
# One runnable example each: the gallery renders them, the e2e test asserts
# they paint, and they double as copy-paste documentation of the data contract.

RECIPE_DEMOS: dict[str, dict[str, Any]] = {
    "line-reveal": {
        "scene": {
            "kind": "simple",
            "headline": "Monthly volume tripled in a single quarter",
            "commentary": "After two flat years, the spring spike rewrote the baseline.",
            "source_line": "Source: synthetic demo data.",
            "alt": "Line chart: monthly volume rises from about 1.2M to 4.2M between January and June 2024.",
            "config": {"x": "date", "y": "value", "format": ",.2s"},
            "annotation": {"x": "2024-05-01", "y": 4100000, "text": "The spike: 4.1M"},
        },
        "dataset": [
            {"date": "2024-01-01", "value": 1200000},
            {"date": "2024-02-01", "value": 1350000},
            {"date": "2024-03-01", "value": 1900000},
            {"date": "2024-04-01", "value": 3100000},
            {"date": "2024-05-01", "value": 4100000},
            {"date": "2024-06-01", "value": 3900000},
        ],
    },
    "slope-chart": {
        "scene": {
            "kind": "simple",
            "headline": "Remote roles flipped the salary ladder",
            "commentary": "Four of five categories converged; infrastructure pulled away.",
            "source_line": "Source: synthetic demo data.",
            "alt": "Slope chart: infrastructure salaries rose from 118 to 162 thousand, while support fell from 74 to 69.",
            "config": {"start_label": "2020", "end_label": "2024",
                       "highlight": ["Infrastructure"], "format": ",.0f"},
        },
        "dataset": [
            {"label": "Infrastructure", "start": 118, "end": 162},
            {"label": "Data science", "start": 121, "end": 138},
            {"label": "Frontend", "start": 102, "end": 111},
            {"label": "QA", "start": 88, "end": 92},
            {"label": "Support", "start": 74, "end": 69},
        ],
    },
    "beeswarm": {
        "scene": {
            "kind": "simple",
            "headline": "Most counties cluster — a handful run away",
            "commentary": "The distribution is tight around the median, with a visible right tail.",
            "source_line": "Source: synthetic demo data.",
            "alt": "Beeswarm: about forty counties cluster between 45 and 65, with three outliers above 85.",
            "config": {"axis_label": "Index score", "annotate": ["Fairview", "Lakemont"]},
        },
        "dataset": (
            [{"label": f"County {i}", "value": v, "group": "Rural"} for i, v in enumerate(
                [44, 47, 49, 50, 51, 52, 53, 54, 55, 55, 56, 57, 58, 59, 61, 62, 64])]
            + [{"label": f"Metro {i}", "value": v, "group": "Urban"} for i, v in enumerate(
                [48, 52, 55, 57, 58, 60, 61, 63, 65, 66, 68, 70, 72])]
            + [{"label": "Fairview", "value": 88, "group": "Urban"},
               {"label": "Lakemont", "value": 91, "group": "Rural"}]
        ),
    },
    "bump-chart": {
        "scene": {
            "kind": "simple",
            "headline": "Python overtook everything by 2022",
            "commentary": "Steady gains every period while the incumbents traded places below.",
            "source_line": "Source: synthetic demo data.",
            "alt": "Bump chart: Python climbs from rank 4 in 2019 to rank 1 by 2022 and holds it.",
            "config": {"x": "period", "series": "name", "y": "value", "highlight": ["Python"]},
        },
        "dataset": [
            {"period": p, "name": n, "value": v}
            for p, scores in {
                "2019": {"Java": 30, "JavaScript": 28, "C++": 22, "Python": 20},
                "2020": {"Java": 27, "JavaScript": 29, "C++": 21, "Python": 26},
                "2021": {"Java": 25, "JavaScript": 30, "C++": 20, "Python": 31},
                "2022": {"Java": 23, "JavaScript": 29, "C++": 19, "Python": 36},
                "2023": {"Java": 22, "JavaScript": 28, "C++": 19, "Python": 41},
            }.items()
            for n, v in scores.items()
        ],
    },
    "annotated-scatter": {
        "scene": {
            "kind": "simple",
            "headline": "Spending doesn't buy outcomes",
            "commentary": "The two best performers spend less than the median system.",
            "source_line": "Source: synthetic demo data.",
            "alt": "Scatter plot of spending versus outcomes for 20 systems; Northfield and Easton score highest while spending below average.",
            "config": {"x": "spend", "y": "score", "label": "name",
                       "annotate": ["Northfield", "Easton"],
                       "x_label": "Spend per capita ($)", "y_label": "Outcome index"},
        },
        "dataset": [
            {"name": "Northfield", "spend": 410, "score": 86},
            {"name": "Easton", "spend": 455, "score": 84},
            {"name": "A", "spend": 520, "score": 71}, {"name": "B", "spend": 610, "score": 75},
            {"name": "C", "spend": 480, "score": 64}, {"name": "D", "spend": 700, "score": 77},
            {"name": "E", "spend": 560, "score": 69}, {"name": "F", "spend": 640, "score": 72},
            {"name": "G", "spend": 530, "score": 66}, {"name": "H", "spend": 720, "score": 74},
            {"name": "I", "spend": 590, "score": 70}, {"name": "J", "spend": 470, "score": 62},
            {"name": "K", "spend": 680, "score": 73}, {"name": "L", "spend": 540, "score": 68},
            {"name": "M", "spend": 620, "score": 71}, {"name": "N", "spend": 500, "score": 65},
            {"name": "O", "spend": 660, "score": 70}, {"name": "P", "spend": 580, "score": 67},
        ],
    },
    "waffle": {
        "scene": {
            "kind": "simple",
            "headline": "Renewables are a third of the mix — and growing",
            "commentary": "Each square is one percent of total generation.",
            "source_line": "Source: synthetic demo data.",
            "alt": "Waffle chart: renewables 34 percent, gas 38 percent, coal 18 percent, nuclear 10 percent.",
        },
        "dataset": [
            {"label": "Gas", "value": 38},
            {"label": "Renewables", "value": 34},
            {"label": "Coal", "value": 18},
            {"label": "Nuclear", "value": 10},
        ],
    },
    "dot-timeline": {
        "scene": {
            "kind": "simple",
            "headline": "A decade of releases, two that mattered",
            "commentary": "The cadence was steady; the inflection points were not.",
            "source_line": "Source: synthetic demo data.",
            "alt": "Timeline of seven product releases from 2015 to 2024, highlighting the 2018 platform launch and the 2023 AI release.",
            "config": {"highlight": ["Platform launch", "AI release"]},
        },
        "dataset": [
            {"date": "2015-03-01", "label": "v1.0 ships"},
            {"date": "2016-09-01", "label": "Mobile app"},
            {"date": "2018-06-01", "label": "Platform launch"},
            {"date": "2020-01-01", "label": "Enterprise tier"},
            {"date": "2021-08-01", "label": "v3 rewrite"},
            {"date": "2023-04-01", "label": "AI release"},
            {"date": "2024-07-01", "label": "On-prem GA"},
        ],
    },
    "small-multiples": {
        "scene": {
            "kind": "simple",
            "headline": "Growth was a coastal story",
            "commentary": "Same axes in every panel — only two regions actually bent upward.",
            "source_line": "Source: synthetic demo data.",
            "alt": "Six small line charts of regional growth 2019 to 2024; West and Northeast rise steeply, the rest stay flat.",
            "config": {"x": "year", "series": "region", "y": "index",
                       "highlight": ["West", "Northeast"]},
        },
        "dataset": [
            {"year": y, "region": r, "index": v}
            for r, series in {
                "West": [100, 108, 121, 138, 152, 171],
                "Northeast": [100, 105, 114, 127, 141, 158],
                "Midwest": [100, 101, 103, 104, 106, 109],
                "South": [100, 103, 105, 108, 110, 114],
                "Mountain": [100, 102, 101, 104, 107, 111],
                "Plains": [100, 99, 101, 102, 101, 103],
            }.items()
            for y, v in zip(range(2019, 2025), series)
        ],
    },
    "bar-steps": {
        "scene": {
            "kind": "scrolly",
            "headline": "Where the cuts landed",
            "source_line": "Source: synthetic demo data.",
            "alt": "Bar chart of headcount change by department; product fell 38 percent, engineering 4 percent, sales rose 12 percent.",
            "config": {"format": "+"},
            "steps": [
                {"headline": "Product took the hardest hit",
                 "commentary": "Product roles fell 38% in the first quarter.", "state": "Product"},
                {"headline": "Engineering held steady",
                 "commentary": "Down only 4% — the smallest drop.", "state": "Engineering"},
                {"headline": "Sales reversed the trend",
                 "commentary": "After a dip, sales finished 12% above the start.", "state": "Sales"},
            ],
        },
        "dataset": [
            {"label": "Product", "value": -38},
            {"label": "Design", "value": -21},
            {"label": "Engineering", "value": -4},
            {"label": "Sales", "value": 12},
        ],
    },
    "range-dots": {
        "scene": {
            "kind": "simple",
            "headline": "Everyone gained — nobody gained alike",
            "commentary": "Thirty years of progress, sorted by how far each moved.",
            "source_line": "Source: synthetic demo data.",
            "alt": "Dumbbell chart: life expectancy gains 1990 to 2020 across seven countries, from 4 to 17 years.",
            "config": {"start_label": "1990", "end_label": "2020",
                       "highlight": ["South Korea"], "format": ".1f"},
        },
        "dataset": [
            {"label": "South Korea", "start": 71.4, "end": 83.2},
            {"label": "Turkey", "start": 64.3, "end": 77.5},
            {"label": "Brazil", "start": 66.3, "end": 75.7},
            {"label": "Poland", "start": 70.9, "end": 77.9},
            {"label": "United States", "start": 75.2, "end": 78.9},
            {"label": "Japan", "start": 78.8, "end": 84.7},
            {"label": "Germany", "start": 75.2, "end": 81.1},
        ],
    },
}


def recipe_demo(name: str) -> dict[str, Any]:
    """A runnable {scene, dataset} demo for a recipe (raises on unknown name)."""
    if name not in RECIPE_DEMOS:
        raise KeyError(f"No demo for recipe {name!r}. Available: {sorted(RECIPE_DEMOS)}")
    return RECIPE_DEMOS[name]
