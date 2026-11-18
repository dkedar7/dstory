"""Sweep 2026-11-17: #35, leftover template text must fail editorial
integrity, naming the field, and never pass as "safe to deliver"."""
from __future__ import annotations

import json

import pytest

from dstory.vet import check_editorial

HTML = "<html lang='en'><head><title>t</title></head><body></body></html>"


def _story(**scene) -> dict:
    base = {"id": "scene-trend", "kind": "simple", "dataset": "d",
            "headline": "Signups tripled in 2024",
            "commentary": "Most of the growth came after the summer launch.",
            "source_line": "Source: Internal analytics",
            "alt": "Line chart of monthly signups in 2024, rising from 1,000 to 3,000."}
    base.update(scene)
    return {"meta": {"title": "Signups tripled", "published": "2026-11-17",
                     "sources": [{"name": "Internal analytics"}]},
            "datasets": {"d": [{"date": "2024-01-01", "value": 1000}]},
            "scenes": [base]}


def test_a_finished_story_passes():
    r = check_editorial(HTML, _story())
    assert r.passed, r.issues


@pytest.mark.parametrize("title", ["Untitled Story", "untitled story", "Untitled", "  Untitled Story "])
def test_scaffold_title_fails_and_names_the_field(title):
    d = _story()
    d["meta"]["title"] = title
    r = check_editorial(HTML, d)
    assert not r.passed
    assert any(i.startswith("meta.title is still the scaffold default") for i in r.issues), r.issues


@pytest.mark.parametrize("field,text", [
    ("headline", "[Insert headline here]"),
    ("headline", "[Insert headline]"),
    ("headline", "Headline goes here"),
    ("headline", "XXX: fix me"),
    ("headline", "{{headline}}"),
    ("headline", "Signups rose {pct} in 2024"),
    ("headline", "TBD"),
    ("headline", "Results [TBD]"),
    ("commentary", "Your commentary goes here."),
    ("commentary", "Your text here"),
    ("commentary", "FIXME: check the June number"),
    ("source_line", "Source: {{source}}"),
    ("alt", "[Add alt text]"),
])
def test_template_text_fails_and_names_the_field(field, text):
    r = check_editorial(HTML, _story(**{field: text}))
    assert not r.passed
    assert any(f"scene 'scene-trend' {field} still has template text" in i for i in r.issues), r.issues


@pytest.mark.parametrize("where,text", [
    (("meta", "subtitle"), "{{subtitle}}"),
    (("meta", "deck"), "Deck goes here"),
])
def test_template_text_in_meta_fails(where, text):
    d = _story()
    d[where[0]][where[1]] = text
    r = check_editorial(HTML, d)
    assert any(i.startswith(f"meta.{where[1]} still has template text") for i in r.issues), r.issues


def test_steps_frames_and_sources_are_checked():
    d = _story(kind="scrolly", steps=[{"headline": "Fine"}, {"commentary": "Step text goes here"}])
    d["meta"]["sources"] = [{"name": "[Insert source]"}]
    r = check_editorial(HTML, d)
    assert any("steps[1].commentary" in i for i in r.issues)
    assert any("meta.sources[0].name" in i for i in r.issues)


@pytest.mark.parametrize("text", [
    "Signups rose 30% here in Oregon",            # "here" alone is fine
    "Where the money goes: here is the split",
    "Sales of the XXL size doubled",              # not a bare XXX
    "A set {x | x > 0} in a math story",          # not an identifier slot
    "Prices (in $) rose [see note 2]",
    "The tbd-ward route",                         # lower case, part of a word
    "Untitled no more: the 2024 relaunch",
])
def test_ordinary_prose_is_not_template_text(text):
    r = check_editorial(HTML, _story(headline=text))
    assert r.passed, r.issues


def test_hidden_scene_text_is_not_checked():
    """`chrome: false` hides a simple scene's headline and commentary."""
    r = check_editorial(HTML, _story(chrome=False, headline="{{headline}}"))
    assert r.passed, r.issues


def test_bundle_warns_and_vet_fails_on_the_issue_repro(tmp_path, monkeypatch):
    """The issue's repro: init, scene, forget meta.title, bundle, vet."""
    from dstory.bundle import bundle
    from dstory.scaffold import init
    from dstory.vet import vet

    monkeypatch.chdir(tmp_path)
    init("my-story", brand="editorial-noir")
    p = tmp_path / "my-story" / "data.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["meta"].update(published="2026-11-17",
                     sources=[{"name": "Internal analytics", "url": "https://example.com"}])
    d["datasets"]["signups"] = [{"date": f"2024-{m:02d}-01", "value": v} for m, v in
                                zip(range(1, 13), [1000, 1100, 1250, 1400, 1500, 1700,
                                                   1900, 2100, 2300, 2500, 2800, 3000])]
    d["scenes"] = [{"id": "scene-trend", "kind": "simple", "dataset": "signups",
                    "headline": "[Insert headline here]",
                    "commentary": "Your commentary goes here.",
                    "source_line": "Source: {{source}}",
                    "alt": "Line chart of monthly signups in 2024, rising from 1,000 to 3,000."}]
    p.write_text(json.dumps(d), encoding="utf-8")
    res = bundle("my-story")
    assert any("meta.title" in w and "Untitled Story" in w for w in res.warnings), res.warnings

    rep = vet(res.out, data=p, browser=False)
    assert not rep.passed
    ed = next(x for x in rep.dimensions if x.name == "Editorial integrity")
    msgs = "\n".join(ed.issues)
    for needle in ("meta.title is still the scaffold default 'Untitled Story'",
                   "headline still has template text", "commentary still has template text",
                   "source_line still has template text"):
        assert needle in msgs, msgs
