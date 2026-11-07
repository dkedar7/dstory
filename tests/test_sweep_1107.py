"""#11 milestone 3: the animated Vizzu opener, messy spreadsheet numbers,
and time columns recognised from their values (years, months, quarters)."""
import io
import os
import subprocess
import sys

import pytest

pd = pytest.importorskip("pandas")

from dstory import build, draft  # noqa: E402
from dstory.vet import check_data_fidelity, check_vizzu_overdraw  # noqa: E402

YEARS = list(range(2015, 2025))
SERIES = {"Coal": [410, 400, 380, 350, 330, 300, 280, 250, 230, 210],
          "Gas": [300, 310, 330, 340, 360, 370, 380, 390, 395, 400],
          "Solar": [20, 28, 40, 55, 75, 100, 130, 165, 200, 240]}


def _grid():
    return pd.DataFrame([{"year": y, "source": s, "twh": v}
                         for s, vals in SERIES.items() for y, v in zip(YEARS, vals)])


def _csv(text):
    return pd.read_csv(io.StringIO(text))


# ---------- Vizzu opener ----------

def test_opener_stacks_then_splits():
    d = draft(_grid(), title="Grid")
    op = d.story["scenes"][0]
    assert op["id"] == "scene-opener" and op["kind"] == "vizzu"
    f1, f2 = op["frames"]
    assert f1["config"] == {"channels": {"x": "year", "y": ["source", "twh"], "color": "source",
                                         "label": None}, "geometry": "rectangle"}
    assert f2["config"]["geometry"] == "line" and f2["config"]["channels"]["y"] == "twh"
    assert f1["headline"] == "Total twh rose 16% between 2015 and 2024"
    assert f2["headline"] == "In 2024, Gas made up 47% of the total"
    assert f2["commentary"] == "Solar was next, at 28%."
    assert "scene-opener" not in d.scenes            # declarative: no JS
    assert len(d.story["datasets"]["opener"]) == 30
    assert check_vizzu_overdraw(d.story) == []        # stacked or lines, never overdrawn
    assert check_data_fidelity("", d.story).passed


def test_opener_can_be_turned_off_and_is_off_for_vendored_builds(tmp_path):
    assert draft(_grid(), title="g", opener=False).story["scenes"][0]["id"] == "scene-trend"
    r = build(_grid(), tmp_path / "offline-grid", vendor=False)
    assert '"scene-opener"' in r.html.read_text(encoding="utf-8")
    from dstory.draft import _maybe_draft
    story, _ = _maybe_draft(_grid(), tmp_path / "x", brand=None, scenes=None, vendor=True)
    assert story["scenes"][0]["id"] == "scene-trend"


def test_no_opener_when_a_category_has_a_gap():
    df = _grid()
    df = df[~((df.source == "Solar") & (df.year == 2017))]
    d = draft(df, title="x")
    assert d.story["scenes"][0]["id"] == "scene-trend"
    assert any("(skipped) vizzu opener: Solar has no twh in 2017" in r for r in d.reasons)


@pytest.mark.parametrize("why,df", [
    ("shares", pd.DataFrame([(y, s, v) for y in (2020, 2021, 2022) for s, v in
                             (("A", 60), ("B", 40))], columns=["year", "src", "share_pct"])),
    ("non-additive", pd.DataFrame([(y, s, v) for y in (2020, 2021, 2022) for s, v in
                                   (("A", 3.1), ("B", 4.2))], columns=["year", "team", "avg_score"])),
    ("negative", pd.DataFrame([(y, s, v) for y in (2020, 2021, 2022) for s, v in
                               (("A", -3), ("B", 4))], columns=["year", "unit", "profit"])),
])
def test_no_opener_when_stacking_is_meaningless(why, df):
    ids = [s["id"] for s in draft(df, title="x").story["scenes"]]
    assert "scene-opener" not in ids, why


# ---------- messy spreadsheet numbers ----------

def test_one_typo_and_a_blank_no_longer_abort_the_draft():
    d = draft(_csv("region,sales\nNorth,100\nSouth,\nEast,abc\nWest,50\n"), title="x")
    text = d.explain()
    assert "(cleaned) sales: read as numbers; 1 non-numeric value dropped ('abc'); " \
           "1 blank skipped" in text
    assert text.index("(cleaned)") < text.index("Scenes:")
    rows = d.story["datasets"]["rank"]
    assert {r["region"] for r in rows} == {"North", "West"}


def test_currency_thousands_and_accounting_negatives():
    d = draft(_csv('item,amount\nA,"$1,200"\nB,"(300)"\nC,"$2,050.50"\n'), title="x")
    vals = {r["item"]: r["amount"] for r in d.story["datasets"]["rank"]}
    assert vals == {"A": 1200, "B": -300, "C": 2050.5}


def test_mostly_text_column_stays_categorical():
    with pytest.raises(ValueError, match="no numeric measure"):
        draft(_csv("name,code\nA,x1\nB,x2\nC,7\nD,y\n"), title="x")


# ---------- time from values ----------

def test_month_names_and_quarters_are_time():
    d = draft(_csv('month,revenue\nJan 2024,10\nFeb 2024,12\nMar 2024,11\nApr 2024,20\n'), title="x")
    assert d.story["scenes"][0]["id"] == "scene-trend"
    assert "between Jan 2024 and Apr 2024" in d.story["scenes"][0]["headline"]
    d = draft(_csv("qtr,units\n2023 Q1,10\n2023 Q2,12\nQ3 2023,15\n2023-Q4,11\n2024 Q1,20\n"),
              title="x")
    assert d.story["scenes"][0]["headline"] == "Units doubled between Q1 2023 and Q1 2024"
    assert [r["qtr"] for r in d.story["datasets"]["trend"]][:2] == ["2023-01-01", "2023-04-01"]


def test_evenly_spaced_years_without_a_time_name():
    df = pd.DataFrame({"cohort": [2016, 2018, 2020, 2022], "sales": [5, 7, 9, 12]})
    d = draft(df, title="x")
    assert any("year (from values)" in p.describe() for p in d.profile)
    assert d.story["scenes"][0]["id"] == "scene-trend"
    # Irregular numbers in the year range stay measures.
    df = pd.DataFrame({"region": list("ABCD"), "units": [1904, 2011, 1958, 2077]})
    assert draft(df, title="x").story["scenes"][0]["id"] == "scene-rank"


def test_flat_series_has_no_sharpest_move():
    df = pd.DataFrame({"year": [2020, 2020, 2021, 2021, 2022, 2022], "users": [5, 6, 6, 5, 5, 6]})
    s = draft(df, title="x").story["scenes"][0]
    assert "sharpest" not in s.get("commentary", "")


# ---------- CLI ----------

def test_cli_draft_messy_csv(tmp_path):
    (tmp_path / "dirty.csv").write_text("region,sales\nNorth,100\nSouth,\nEast,abc\nWest,50\n",
                                        encoding="utf-8")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, "-m", "dstory.cli", "draft", "dirty.csv", "--no-browser"],
                          cwd=tmp_path, env=env, capture_output=True, timeout=300)
    out = proc.stdout.decode("utf-8")
    assert proc.returncode == 0, out
    assert "1 non-numeric value dropped ('abc')" in out and "OVERALL: PASS" in out
