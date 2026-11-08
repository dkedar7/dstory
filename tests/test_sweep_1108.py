"""#19: a missing or dropped cell must not turn a summed total into a false
decline. The total keeps only complete periods, or follows the largest
category, and explain() names the gap."""
import io

import pytest

pd = pytest.importorskip("pandas")

from dstory import draft  # noqa: E402
from dstory.vet import check_data_fidelity  # noqa: E402


def _csv(text):
    return pd.read_csv(io.StringIO(text))


def test_trailing_gap_follows_the_leader_not_a_false_decline():
    d = draft(_csv("year,region,sales\n2022,North,100\n2022,South,100\n2023,North,110\n"
                   "2023,South,105\n2024,North,120\n2024,South,\n"), title="x")
    s = d.story["scenes"][0]
    assert s["headline"] == "North sales rose 20% between 2022 and 2024"
    assert "fell" not in s["headline"] and "Total" not in s["headline"]
    assert "(gap) South has no sales in 2024" in d.explain()
    assert check_data_fidelity("", d.story).passed


def test_dropped_typo_cell_does_not_halve_the_total():
    rows = ["Quarter,Region,Revenue"]
    for q, n, s in [("2023 Q1", "$1,200", "$800"), ("2023 Q2", "$1,250", "$850"),
                    ("2023 Q3", "$1,300", "$900"), ("2023 Q4", "$1,350", "$950"),
                    ("2024 Q1", "abc", "$1,000")]:
        rows += [f'{q},North,"{n}"', f'{q},South,"{s}"']
    d = draft(_csv("\n".join(rows) + "\n"), title="x")
    head = d.story["scenes"][0]["headline"]
    assert "halved" not in head and "fell" not in head, head
    assert head == "Total Revenue rose 15% between Q1 2023 and Q4 2023"
    text = d.explain()
    assert "('abc')" in text and "(gap) North has no Revenue in Q1 2024" in text
    assert "left out: Q1 2024" in text


def test_complete_data_still_sums_the_total():
    d = draft(_csv("year,region,sales\n2022,North,100\n2022,South,100\n2023,North,110\n"
                   "2023,South,105\n2024,North,120\n2024,South,110\n"), title="x", opener=False)
    assert d.story["scenes"][0]["headline"] == "Total sales rose 15% between 2022 and 2024"
    assert "(gap)" not in d.explain()


def test_interior_gap_keeps_the_complete_periods():
    lines = ["year,region,sales"]
    for y in range(2018, 2024):
        lines.append(f"{y},North,{100 + 10 * (y - 2018)}")
        if y != 2020:
            lines.append(f"{y},South,{50 + 5 * (y - 2018)}")
    d = draft(_csv("\n".join(lines) + "\n"), title="x")
    s = d.story["scenes"][0]
    assert s["id"] == "scene-trend"
    years = [r["year"][:4] for r in d.story["datasets"]["trend"]]
    assert "2020" not in years and years[0] == "2018" and years[-1] == "2023"
    assert s["headline"] == "Total sales rose 50% between 2018 and 2023"


# ---------- #11 final milestone: small multiples and range-dots ----------

YEARS = list(range(2018, 2024))


def _cities(scale_big=1.0):
    vals = {"Austin": [300, 320, 350, 390, 420, 460], "Boise": [200, 215, 230, 260, 280, 300],
            "Tulsa": [150, 152, 151, 149, 148, 146], "Reno": [250, 262, 280, 300, 330, 350]}
    vals["Austin"] = [v * scale_big for v in vals["Austin"]]
    return pd.DataFrame([{"year": y, "city": c, "price": v} for c, vs in vals.items()
                         for y, v in zip(YEARS, vs)])


def _panels(d):
    return next(s for s in d.story["scenes"] if s["id"] == "scene-panels")


def test_small_multiples_share_one_scale_by_default():
    d = draft(_cities(), title="x")
    p = _panels(d)
    assert p["config"]["scale"] == "shared" and p["config"]["series"] == "city"
    assert p["headline"] == "Every city but Tulsa rose between 2018 and 2023"
    assert p["config"]["highlight"] == ["Tulsa"]
    assert "share one scale" in p["commentary"]
    assert "scene-panels" in d.scenes and "small-multiples" in d.scenes["scene-panels"]
    assert len(d.story["datasets"]["panels"]) == 24
    assert check_data_fidelity("", d.story).passed


def test_small_multiples_get_independent_scales_when_sizes_differ():
    d = draft(_cities(scale_big=40), title="x")
    p = _panels(d)
    assert p["config"]["scale"] == "independent"
    assert "own scale" in p["commentary"] and "own scale" in p["alt"]
    assert "10x or more" in d.explain()


def test_no_panels_when_the_opener_already_splits_the_lines():
    df = _cities().rename(columns={"price": "units"})
    ids = [s["id"] for s in draft(df, title="x").story["scenes"]]
    assert ids[0] == "scene-opener" and "scene-panels" not in ids
    ids = [s["id"] for s in draft(df, title="x", opener=False).story["scenes"]]
    assert "scene-panels" in ids


def test_many_categories_get_range_dots_instead_of_a_slope_chart():
    names = ["Chile", "Peru", "Japan", "Kenya", "Spain", "Italy", "Ghana", "Nepal", "Oman",
             "Laos"]
    df = pd.DataFrame([{"year": y, "country": c, "life_expectancy": 60 + i + (k * (i % 4 + 1))}
                       for i, c in enumerate(names) for k, y in enumerate((1990, 2020))])
    d = draft(df, title="x")
    s = next(s for s in d.story["scenes"] if s["id"] == "scene-shift")
    assert "range-dots" in d.scenes["scene-shift"]
    assert s["config"]["start_label"] == "1990" and s["alt"].startswith("Dot chart")
    assert "range-dots past 7" in d.explain()
    assert check_data_fidelity("", d.story).passed
    few = df[df.country.isin(names[:5])]
    assert "slope-chart" in draft(few, title="x").scenes["scene-shift"]


def test_shared_turning_point_is_the_panel_headline():
    df = pd.read_csv("docs/drafted/metros.csv")
    d = draft(df, title="x")
    p = _panels(d)
    assert p["headline"] == "Every metro peaked in 2021"
    assert p["config"]["scale"] == "independent"
    tulsa_late = df.copy()
    tulsa_late.loc[(tulsa_late.metro == "Tulsa") & (tulsa_late.year == 2023), "homes_sold"] = 14
    p = _panels(draft(tulsa_late, title="x"))
    assert p["headline"] == "Every metro but Tulsa peaked in 2021"
    assert p["config"]["highlight"] == ["Tulsa"]
