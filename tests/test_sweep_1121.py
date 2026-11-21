"""Sweep 2026-11-21: #34, a mistyped scene or step key ("headine",
"alt_text", "source", a step's "text") is warned about with a did-you-mean
from build() and `dstory bundle`, instead of vanishing from the page."""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from dstory import build
from dstory.schema import unknown_key_hints

META = {"title": "T", "theme": "minimal-light", "published": "2026-11-16",
        "sources": [{"name": "S"}]}


def _story(**extra):
    scene = {"id": "s1", "kind": "vizzu", "dataset": "d",
             "series": [{"name": "y"}, {"name": "v", "type": "measure"}],
             "frames": [{"headline": "Sales doubled",
                         "config": {"channels": {"x": "y", "y": "v"}, "geometry": "rectangle"}}],
             **extra}
    return {"meta": META, "scenes": [scene],
            "datasets": {"d": [{"y": "2023", "v": 1}, {"y": "2024", "v": 2}]}}


TYPOS = {"headine": "Sales doubled in 2024", "source": "Sales ledger",
         "alt_text": "Bar chart: sales doubled.", "my_renderer_opt": 3}


def test_the_issue_repro_warns_three_times_from_build(tmp_path):
    with pytest.warns(UserWarning) as rec:
        build(_story(**TYPOS), tmp_path / "typo", vet=False)
    msgs = [str(w.message) for w in rec if "did you mean" in str(w.message)]
    assert sorted(msgs) == sorted([
        "Scene 's1': unknown key 'alt_text' (did you mean 'alt'?). It is not shown to readers.",
        "Scene 's1': unknown key 'headine' (did you mean 'headline'?). It is not shown to readers.",
        "Scene 's1': unknown key 'source' (did you mean 'source_line'?). It is not shown to "
        "readers.",
    ])
    assert not any("my_renderer_opt" in m for m in msgs)


def test_dstory_bundle_prints_the_hints(tmp_path):
    import warnings
    from dstory.cli import cli
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = build(_story(**TYPOS), tmp_path / "typo", vet=False)
    out = CliRunner().invoke(cli, ["bundle", str(res.project)]).output
    assert "unknown key 'headine' (did you mean 'headline'?)" in out, out
    assert "unknown key 'source' (did you mean 'source_line'?)" in out
    assert "my_renderer_opt" not in out


def test_step_keys_and_aliases():
    raw = {"scenes": [{"id": "s", "kind": "scrolly", "title": "Gas leads",
                       "steps": [{"headline": "Gas", "text": "Full tables."},
                                 {"hedline": "Coal", "commentary": "Last."}]}]}
    hints = unknown_key_hints(raw)
    assert "Scene 's': unknown key 'title' (did you mean 'headline'?)." in hints[0]
    assert any("step 1: unknown key 'text' (did you mean 'commentary'?)" in h for h in hints)
    assert any("step 2: unknown key 'hedline' (did you mean 'headline'?)" in h for h in hints)


def test_no_hint_when_the_real_field_is_set_or_the_key_is_custom():
    raw = {"scenes": [{"id": "s", "headline": "Real", "title": "Also set",
                       "source_line": "S", "source": "S", "highlight": ["A"], "palette": "x",
                       "steps": [{"headline": "H", "commentary": "C", "text": "extra"}]}]}
    assert unknown_key_hints(raw) == []


def test_a_drafted_story_has_no_hints():
    pd = pytest.importorskip("pandas")
    import io
    from dstory.draft import draft
    csv = "year,source,share_pct\n2014,Coal,40\n2014,Gas,30\n2014,Wind,30\n" \
          "2024,Coal,16\n2024,Gas,46\n2024,Wind,38\n"
    st = draft(pd.read_csv(io.StringIO(csv)), title="Mix").story
    assert unknown_key_hints(json.loads(json.dumps(st))) == []
