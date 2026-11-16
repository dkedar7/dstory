"""Sweep 2026-11-16: #33, the PII check must not block ordinary numbers
(an 11-digit budget, a computed mean) and must catch phones as people write
them ("555-123-4567", "(555) 123-4567")."""
from __future__ import annotations

import shutil

import pytest

from dstory.vet import PII_PATTERNS, check_static_a11y

PHONE = PII_PATTERNS[2][0]


@pytest.mark.parametrize("s", [
    "555-123-4567", "(555) 123-4567", "555.123.4567", "+1 555 123 4567",
    "1-555-123-4567", "+44 207 123 4567", "Call 555 123 4567 today",
])
def test_phones_as_people_write_them_are_flagged(s):
    assert PHONE.search(s)


@pytest.mark.parametrize("s", [
    "12500000000", "14285.714285714286", "100000000000", "12,500,000,000",
    "2024-11-16", "2024-11-16T10:30:00Z", "192.168.100.200", "97062-1234",
    "ISBN 978-3-16-148410-0", "id-555-123-45678",
])
def test_amounts_dates_and_ids_are_not_phones(s):
    assert not PHONE.search(s)


def _data(rows, **meta):
    return {"meta": {"title": "t", **meta}, "scenes": [], "datasets": {"d": rows}}


def test_numbers_in_datasets_never_count_as_pii():
    rows = [{"year": 2020, "budget_usd": 12500000000},
            {"year": 2021, "avg_order": 100000 / 7},          # 14285.714285714286
            {"year": 2022, "id": 100000000000}]
    r = check_static_a11y("<html lang='en'></html>", _data(rows))
    assert not any("PII" in i for i in r.issues), r.issues


@pytest.mark.parametrize("value,label", [
    ("555-123-4567", "phone-shaped number"),
    ("(555) 123-4567", "phone-shaped number"),
    ("jane@example.com", "email address"),
    ("123-45-6789", "SSN-shaped number"),
])
def test_pii_in_a_string_fails_and_says_where(value, label):
    rows = [{"name": "A", "contact": "n/a"}, {"name": "B", "contact": value}]
    r = check_static_a11y("<html lang='en'></html>", _data(rows))
    msg = next(i for i in r.issues if label in i)
    assert repr(value) in msg and "datasets.d[1].contact" in msg


def test_build_with_a_computed_mean_passes():
    """Repro 2 from the issue: a notebook story with a computed mean."""
    pd = pytest.importorskip("pandas")
    from dstory import build

    df = pd.DataFrame({"region": ["North", "South", "East"],
                       "revenue": [100000, 150000, 120000], "orders": [7, 11, 9]})
    df["avg_order"] = df["revenue"] / df["orders"]
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        cwd = os.getcwd()
        os.chdir(d)
        try:
            r = build({
                "meta": {"title": "North leads on order value", "theme": "minimal-light",
                         "published": "2026-11-16", "sources": [{"name": "Sales ledger"}]},
                "scenes": [{"id": "s-aov", "kind": "vizzu", "dataset": "aov",
                            "source_line": "Sales ledger",
                            "alt": "Bar chart of average order value by region: North is highest.",
                            "series": [{"name": "region"}, {"name": "avg_order", "type": "measure"}],
                            "frames": [{"headline": "North has the biggest orders",
                                        "config": {"channels": {"x": "region", "y": "avg_order"},
                                                   "geometry": "rectangle"}}]}],
                "datasets": {"aov": df[["region", "avg_order"]].to_dict("records")},
            }, "aov", vet=True, browser=False)
        finally:
            os.chdir(cwd)
    static = next(x for x in r.report.dimensions if x.name.startswith("Accessibility"))
    assert not any("PII" in i for i in static.issues), static.issues


def test_draft_of_a_city_budget_is_not_blocked(tmp_path):
    """Repro 1 from the issue: the README's zero-config path."""
    pytest.importorskip("pandas")
    from dstory import agent

    (tmp_path / "budget.csv").write_text(
        "year,budget_usd\n2020,12500000000\n2021,13100000000\n2022,14200000000\n"
        "2023,15800000000\n2024,16400000000\n", encoding="utf-8")
    out = agent.draft_story("budget.csv", root=tmp_path, browser=False)
    assert not any("PII" in f["message"] for f in out["vet"]["failures"]), out["vet"]["failures"]
    assert out["vet"]["passed"] is True
