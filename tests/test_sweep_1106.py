"""#17 (no percent change across zero) and #11 milestone 2 (points for shares,
N-fold for big ratios, bump-chart rule, no summing of separate series, day
labels, `dstory draft` CLI)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from dstory.prep import (
    compute_claim, compute_pct_change, compute_point_change, derive_claim_text, fold_phrase,
)
from dstory.vet import check_data_fidelity

pd = pytest.importorskip("pandas")
from dstory import build, draft  # noqa: E402


def _fid(*claims):
    return check_data_fidelity("", {"claims": list(claims)})


def _claims(d):
    return {c["id"]: c for c in d.story["claims"]}


def _prose(d):
    return " | ".join(f"{s.get('headline', '')} {s.get('commentary', '')}" for s in d.story["scenes"])


# ---------- #17: changes across zero ----------

def test_series_ending_negative_gets_no_percent_claim():
    d = draft(pd.DataFrame({"year": [2020, 2021, 2022, 2023], "net_income": [5, 10, 20, -5]}),
              title="x")
    text = _prose(d)
    assert "%" not in text and "200" not in text and "125" not in text
    assert d.story["scenes"][0]["headline"] == "Net income turned negative in 2023"
    assert all(c["value"] >= -100 for c in d.story["claims"])


def test_negative_series_gets_a_real_headline_not_how_x_has_moved():
    d = draft(pd.DataFrame({"year": [2020, 2021, 2022, 2023], "net_income": [-10, -15, -20, -30]}),
              title="x")
    assert d.story["scenes"][0]["headline"] == "Net income fell between 2020 and 2023"
    d = draft(pd.DataFrame({"year": [2020, 2021, 2022, 2023], "users": [-40, -30, 10, 20]}),
              title="x")
    assert d.story["scenes"][0]["headline"] == "Users turned positive in 2022"


def test_slope_drops_superlative_when_a_category_cannot_be_measured(tmp_path):
    df = pd.DataFrame({"region": ["N", "S", "E"] * 2, "year": [2020] * 3 + [2024] * 3,
                       "margin": [-10, 5, 8, -30, 6, -2]})
    d = draft(df, title="y")
    shift = next(s for s in d.story["scenes"] if s["id"] == "scene-shift")
    assert "biggest" not in shift["headline"]
    assert "125%" not in _prose(d)
    assert shift["commentary"] == "E turned negative by 2024."
    assert build(d.story, tmp_path / "neg", scenes=d.scenes, vet=True, browser=False).passed


def test_vetter_rejects_percent_fall_beyond_100():
    r = _fid({"id": "c", "text": "Net income fell 200% between 2020 and 2023", "value": -200.0,
              "unit": "pct"})
    assert not r.passed and "changed sign" in r.issues[0]
    assert _fid({"id": "c", "text": "Sales fell 100% to zero", "value": -100.0, "unit": "pct"}).passed


def test_vetter_checks_direction_verbs():
    assert not _fid({"id": "c", "text": "Sales rose 12%", "value": -12.0, "unit": "pct"}).passed
    assert not _fid({"id": "c", "text": "Sales fell 12%", "value": 12.0, "unit": "pct"}).passed
    assert _fid({"id": "c", "text": "Sales fell 12%", "value": -12.0, "unit": "pct"}).passed
    assert _fid({"id": "c", "text": "Sales grew 12%", "value": 12.0, "unit": "pct"}).passed


# ---------- percentage points ----------

def test_point_change_claims():
    pp = compute_point_change(15, 39)
    assert pp == -24 and pp.unit == "pp"
    assert compute_point_change(0.43, 0.27, scale=100) == pytest.approx(16)
    c = compute_claim(id="c", text_template="Coal share {phrase}", value=pp)
    assert c["unit"] == "pp" and c["text"] == "Coal share fell 24 percentage points"
    assert derive_claim_text(1.0, kind="pp") == "rose 1 percentage point"
    assert _fid(c).passed


@pytest.mark.parametrize("text,value,ok", [
    ("Coal share fell 24 points", -24.0, True),
    ("Coal share fell 24 points", 24.0, False),
    ("Coal share fell 20 points", -24.0, False),
    ("Gas share rose 16 percentage points", 16.0, True),
    ("Gas share up 16pp", 16.0, True),
    ("Gas share doubled", 16.0, False),
])
def test_vetter_checks_points_claims(text, value, ok):
    assert _fid({"id": "c", "text": text, "value": value, "unit": "pp"}).passed is ok


def test_shares_are_compared_in_points():
    rows = []
    for y, coal, gas, ren in [(2014, 39, 27, 34), (2017, 30, 33, 37), (2020, 22, 38, 40),
                              (2024, 15, 43, 42)]:
        rows += [(y, "Coal", coal), (y, "Gas", gas), (y, "Renewables", ren)]
    d = draft(pd.DataFrame(rows, columns=["year", "source", "share_pct"]), title="x")
    c = _claims(d)
    assert c["c-trend"]["text"] == "Gas share rose 16 points between 2014 and 2024"
    assert c["c-shift"]["unit"] == "pp" and c["c-shift"]["value"] == -24
    assert "Coal share fell 24 points" in c["c-shift"]["text"]
    assert "%" not in c["c-trend"]["text"] + c["c-shift"]["text"]
    # Fractions (summing to ~1) are scaled to points too.
    frac = pd.DataFrame([(y, s, v / 100) for y, s, v in rows], columns=["year", "source", "share"])
    assert _claims(draft(frac, title="x"))["c-shift"]["value"] == pytest.approx(-24)


# ---------- N-fold ----------

def test_fold_phrase_and_vetter():
    assert fold_phrase(12.0) == "12-fold" and fold_phrase(3.0) is None
    d = draft(pd.DataFrame({"date": pd.date_range("2024-01-01", periods=10, freq="D"),
                            "value": [1, 2, 5, 9, 14, 20, 30, 40, 50, 59]}), title="x")
    c = _claims(d)["c-trend"]
    assert c["text"] == "Value rose 59-fold between Jan 1, 2024 and Jan 10, 2024"
    assert _fid(c).passed
    assert not _fid(dict(c, value=compute_pct_change(30, 1))).passed  # 30-fold, says 59


def test_daily_labels_read_as_dates():
    d = draft(pd.DataFrame({"date": pd.date_range("2024-01-01", periods=6, freq="D"),
                            "value": [10, 11, 12, 30, 31, 32]}), title="x")
    assert "came on Jan 4, 2024" in _claims(d)["c-trend-step"]["text"]
    assert "2024-01" not in _prose(d)


# ---------- separate series are not summed ----------

def test_wide_series_are_followed_not_summed():
    df = pd.DataFrame({"month": pd.date_range("2024-01-01", periods=6, freq="MS"),
                       "Signups": [1, 2, 3, 4, 5, 6], "Churn": [3, 3, 3, 2, 2, 1]})
    d = draft(df, title="x")
    head = d.story["scenes"][0]["headline"]
    assert head.startswith("Signups ") and "Total" not in head
    trend = d.story["datasets"]["trend"]
    assert [r["value"] for r in trend] == [1, 2, 3, 4, 5, 6]


def test_slope_does_not_repeat_the_trend_headline():
    df = pd.DataFrame({"month": pd.date_range("2024-01-01", periods=6, freq="MS"),
                       "Signups": [1, 2, 3, 4, 5, 6], "Churn": [3, 3, 3, 2, 2, 1]})
    d = draft(df, title="x")
    heads = [s["headline"] for s in d.story["scenes"]]
    assert len(set(heads)) == len(heads)
    assert heads[1] == "No series moved more than Signups between Jan 2024 and Jun 2024"


# ---------- bump-chart rule ----------

def _langs():
    rows = []
    for y, vals in [(2019, [30, 28, 22, 18]), (2020, [29, 30, 20, 24]),
                    (2021, [27, 31, 19, 33]), (2022, [25, 32, 18, 40])]:
        rows += [(y, n, v) for n, v in zip(["Java", "JS", "C++", "Python"], vals)]
    return pd.DataFrame(rows, columns=["year", "lang", "score"])


def test_bump_chart_when_the_leader_changes():
    d = draft(_langs(), title="x")
    race = next(s for s in d.story["scenes"] if s["id"] == "scene-race")
    assert race["headline"] == "Python overtook Java to rank first by 2022"
    assert race["commentary"] == "Java led in 2019; Python has held the top spot since 2021."
    assert race["config"] == {"x": "year", "series": "lang", "y": "score", "highlight": ["Python"]}
    assert "scene-race" in d.scenes and "rank 4 to rank 1" in race["alt"]


def test_no_bump_chart_when_the_leader_holds():
    df = _langs()
    df.loc[df.lang == "Java", "score"] = 99
    d = draft(df, title="x")
    assert "scene-race" not in [s["id"] for s in d.story["scenes"]]
    assert any("(skipped) bump-chart: the top lang did not change" in r for r in d.reasons)


def test_draft_sets_a_publish_date():
    from datetime import date
    assert draft(_langs(), title="x").story["meta"]["published"] == date.today().isoformat()


# ---------- CLI: dstory draft ----------

def _cli(*args, cwd):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-m", "dstory.cli", *args], capture_output=True,
                          env=env, cwd=cwd, timeout=300)


def test_cli_draft_writes_a_vetted_project(tmp_path):
    _langs().to_csv(tmp_path / "language_scores.csv", index=False)
    proc = _cli("draft", "language_scores.csv", "--no-browser", "--source", "Survey", cwd=tmp_path)
    out = proc.stdout.decode("utf-8")
    assert proc.returncode == 0, out + proc.stderr.decode("utf-8")
    assert "scene-race: bump-chart" in out and "OVERALL: PASS" in out
    html = tmp_path / "language_scores" / "dist" / "story.html"
    assert html.exists()
    data = json.loads((tmp_path / "language_scores" / "data.json").read_text(encoding="utf-8"))
    assert data["meta"]["title"] == "Language scores"
    assert data["meta"]["sources"] == [{"name": "Survey"}]
    # A second run refuses to clobber without --overwrite.
    again = _cli("draft", "language_scores.csv", "--no-vet", cwd=tmp_path)
    assert again.returncode == 1 and b"--overwrite" in again.stdout
    assert _cli("draft", "language_scores.csv", "--no-vet", "--overwrite", "--mode", "slides",
                "--theme", "warm-print", cwd=tmp_path).returncode == 0
    assert 'data-theme="warm-print"' in html.read_text(encoding="utf-8")


def test_cli_draft_reads_tsv_and_json(tmp_path):
    _langs().to_csv(tmp_path / "a.tsv", sep="\t", index=False)
    _langs().to_json(tmp_path / "b.json", orient="records")
    for f in ("a.tsv", "b.json"):
        proc = _cli("draft", f, "--no-vet", cwd=tmp_path)
        assert proc.returncode == 0, proc.stdout.decode("utf-8")


def test_cli_draft_rejects_unknown_file_type(tmp_path):
    (tmp_path / "x.dat").write_text("1", encoding="utf-8")
    proc = _cli("draft", "x.dat", cwd=tmp_path)
    assert proc.returncode == 1 and b"Unsupported file type" in proc.stdout
