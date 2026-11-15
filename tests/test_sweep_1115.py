"""Sweep 2026-11-15: #31, a thousands separator must not split a number.

"fell 1,200%" against a +1200% claim must fail (it passed), and a correct
"a 1,200% increase" must pass (it was blocked as "200%")."""
from __future__ import annotations

import json

import pytest

from dstory.prep import compute_claim, compute_pct_change, compute_point_change, compute_ratio
from dstory.vet import check_data_fidelity

PCT = compute_claim(id="c1", text_template="Revenue {phrase} since 2010",
                    value=compute_pct_change(after=13000, before=1000), scene="s")   # +1200%
RATIO = compute_claim(id="c2", text_template="Users {phrase}",
                      value=compute_ratio(after=1_000_000, before=1000), scene="r")   # 1000x
PP = compute_claim(id="c3", text_template="Score {phrase}",
                   value=compute_point_change(after=1300, before=100), scene="p")     # +1200 points


def _story(s: str = "Revenue rose 1,200% since 2010", r: str = "Users grew 1,000x",
           p: str = "Score rose 1,200 points") -> dict:
    return {"meta": {"title": "t"}, "claims": [PCT, RATIO, PP],
            "scenes": [{"id": "s", "kind": "simple", "headline": s},
                       {"id": "r", "kind": "simple", "headline": r},
                       {"id": "p", "kind": "simple", "headline": p}]}


@pytest.mark.parametrize("kw", [
    {"s": "Revenue rose 1,900% since 2010"},
    {"s": "Revenue fell 1,200% since 2010"},     # the direction is reversed
    {"s": "A 1,200% drop since 2010"},
    {"s": "Revenue rose 1,2000% since 2010"},    # misgrouped: read as 12000, not skipped
    {"r": "Users grew 2,000x"},
    {"r": "Users grew 1,500 times over"},
    {"p": "Score fell 1,200 points"},
    {"p": "Score up 2,400 points"},
])
def test_drift_with_a_thousands_separator_fails(kw):
    r = check_data_fidelity("", _story(**kw))
    assert not r.passed
    assert any("drifted" in i for i in r.issues)


@pytest.mark.parametrize("kw", [
    {},
    {"s": "A 1,200% increase since 2010"},
    {"s": "Revenue up about 1,190% since 2010; costs were $13,000"},
    {"s": "Revenue increased by 1,200.0% since 2010"},
    {"r": "Users grew 1,000x, to 1,000,000"},
    {"p": "A 1,200-point gain"},
])
def test_correct_prose_with_a_thousands_separator_passes(kw):
    r = check_data_fidelity("", _story(**kw))
    assert r.passed, r.issues


def test_a_number_is_never_read_from_its_middle():
    # "1,200%" used to be read as "200%"; a 200% claim must not match it.
    claim = compute_claim(id="c", text_template="X {phrase}",
                          value=compute_pct_change(after=300, before=100), scene="s")  # +200%
    d = {"meta": {}, "claims": [claim],
         "scenes": [{"id": "s", "kind": "simple", "headline": "X rose 1,200%"}]}
    assert not check_data_fidelity("", d).passed


@pytest.mark.parametrize("text,value,unit,ok", [
    ("Revenue rose 1,200% since 2010", 1200.0, "pct", True),
    ("Revenue rose 1,900% since 2010", 1200.0, "pct", False),
    ("Revenue fell 1,200% since 2010", 1200.0, "pct", False),
    ("Score rose 1,200 points", 1200.0, "pp", True),
    ("Score rose 1,500 points", 1200.0, "pp", False),
    ("Users grew 1,000-fold", 1000.0, "ratio", True),
    ("Users grew 2,000-fold", 1000.0, "ratio", False),
])
def test_hand_written_claim_text_reads_the_whole_number(text, value, unit, ok):
    d = {"meta": {}, "scenes": [{"id": "s", "headline": "Revenue"}],
         "claims": [{"id": "c1", "text": text, "value": value, "unit": unit}]}
    r = check_data_fidelity("", d)
    assert r.passed is ok, r.issues


def test_bundle_stops_on_drift_with_a_thousands_separator(tmp_path, monkeypatch):
    """The issue's repro: `dstory bundle` raises instead of writing the page,
    and the correct headline bundles."""
    from dstory.bundle import ClaimDriftError, bundle
    from dstory.scaffold import init

    monkeypatch.chdir(tmp_path)
    init("rs", brand="minimal-light")
    p = tmp_path / "rs" / "data.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["meta"].update(title="Revenue", published="2026-11-15", sources=[{"name": "Internal ledger"}])
    claim = dict(PCT, scene="scene-trend")
    d["claims"] = [claim]
    d["datasets"] = {"rev": [{"date": f"{y}-01-01", "value": v}
                             for y, v in [(2010, 1000), (2015, 5000), (2020, 13000)]]}
    d["scenes"] = [{"id": "scene-trend", "kind": "simple", "dataset": "rev",
                    "headline": "Revenue fell 1,200% since 2010",
                    "commentary": claim["text"] + ".",
                    "alt": "Line chart of revenue, 2010 to 2020."}]
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ClaimDriftError, match="fell 1,200%"):
        bundle("rs")
    assert not (tmp_path / "rs" / "dist" / "story.html").exists()

    d["scenes"][0]["headline"] = "A 1,200% increase since 2010"
    p.write_text(json.dumps(d), encoding="utf-8")
    assert bundle("rs").out.exists()



# ---------- the CLI prints install hints and errors as written ----------

def test_draft_without_pandas_names_the_extra(tmp_path, monkeypatch):
    """`[prep]` was read as Rich markup and dropped, so the hint said
    `pip install "dstory"`, which installs nothing new."""
    import builtins

    from click.testing import CliRunner

    from dstory.cli import cli

    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "pandas" or name.startswith("pandas."):
            raise ImportError(name)
        return real(name, *a, **k)

    (tmp_path / "x.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(builtins, "__import__", fake)
    r = CliRunner().invoke(cli, ["draft", "x.csv", "--no-browser"])
    assert r.exit_code == 1
    assert 'pip install "dstory[prep]"' in r.output


def test_cli_errors_keep_their_brackets(tmp_path, monkeypatch):
    """An error message with brackets in it ("[prep]", a list of ids) is
    printed as is, not swallowed as markup."""
    from click.testing import CliRunner

    import dstory.cli as cli_mod

    def boom(*a, **k):
        raise ValueError("claims ['c1', 'c2'] drifted; see [docs] and pip install \"dstory[vet]\"")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli_mod, "bundle_story", boom)
    from dstory.scaffold import init
    init("p", brand="minimal-light")
    r = CliRunner().invoke(cli_mod.cli, ["bundle", "p"])
    assert r.exit_code != 0
    assert "['c1', 'c2']" in r.output and "[docs]" in r.output and 'dstory[vet]' in r.output
