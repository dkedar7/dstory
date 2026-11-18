"""Sweep 2026-11-18: #37, the template-text check must not block real prose
("Super Bowl XXX", "2025 figures TBD", "goes here", "table {A1}"), and
`to_json()` must name the scene behind an editorial failure."""
from __future__ import annotations

import pytest

from dstory.schema import Story
from dstory.vet import Dimension, Report, check_editorial

HTML = "<html lang='en'><head><title>t</title></head><body></body></html>"


def _story(**scene) -> dict:
    base = {"id": "s1", "kind": "simple", "dataset": "d",
            "headline": "Solar output tripled since 2014",
            "commentary": "Most of the growth came after 2019.",
            "source_line": "Source: EIA",
            "alt": "Bars of solar output by year: it tripled from 20 to 62."}
    base.update(scene)
    return {"meta": {"title": "Solar's rise", "published": "2026-11-18",
                     "sources": [{"name": "EIA"}]},
            "datasets": {"d": [{"year": "2014", "v": 20}]},
            "scenes": [base]}


@pytest.mark.parametrize("field,text", [
    ("headline", "Super Bowl XXX to today: solar's rise"),
    ("source_line", "Source: EIA; 2025 figures TBD"),
    ("commentary", "Most new capacity goes here: rooftops in the sunbelt."),
    ("source_line", "Source: EIA table {A1}"),
    ("commentary", "Where the money goes here matters less than how much."),
    ("headline", "Your money goes further here"),
])
def test_the_issue_prose_passes(field, text):
    r = check_editorial(HTML, _story(**{field: text}))
    assert r.passed, r.issues


def test_the_issue_title_passes():
    d = _story()
    d["meta"]["title"] = "Super Bowl XXX drew 95 million viewers"
    assert check_editorial(HTML, d).passed


@pytest.mark.parametrize("text,needle", [
    ("Source: EIA; 2025 figures TBD", "'TBD'"),
    ("Source: EIA table {A1}", "'{A1}'"),
])
def test_ambiguous_markers_leave_a_note(text, needle):
    r = check_editorial(HTML, _story(source_line=text))
    assert r.passed
    assert any("scene 's1' source_line" in n and needle in n for n in r.notes), r.notes


@pytest.mark.parametrize("field,text", [
    ("headline", "{{headline}}"),
    ("headline", "[Insert headline here]"),
    ("commentary", "Your commentary goes here."),
    ("commentary", "Commentary goes here"),
    ("headline", "Solar output {phrase} since 2014"),
    ("headline", "Up {value} in a decade"),
    ("headline", "TBD"),
    ("headline", "XXX"),
    ("commentary", "TBD: the June number"),
    ("source_line", "Source: EIA (TBD)"),
    ("commentary", "TKTK"),
    ("commentary", "Check this FIXME"),
])
def test_unambiguous_template_text_still_fails(field, text):
    r = check_editorial(HTML, _story(**{field: text}))
    assert not r.passed
    assert any(f"scene 's1' {field} still has template text" in i for i in r.issues), r.issues


def test_allow_text_lets_real_copy_through():
    d = _story(headline="XXX", source_line="Source: EIA (TBD)")
    d["meta"]["vet"] = {"allow_text": ["xxx", "(TBD)"]}
    r = check_editorial(HTML, d)
    assert r.passed, r.issues


def test_allow_text_does_not_hide_other_template_text():
    d = _story(headline="Super Bowl XXX: {{headline}}")
    d["meta"]["vet"] = {"allow_text": ["Super Bowl XXX"]}
    r = check_editorial(HTML, d)
    assert not r.passed and any("{{headline}}" in i for i in r.issues), r.issues


def test_allow_text_can_keep_a_title_named_untitled():
    d = _story()
    d["meta"]["title"] = "Untitled"
    d["meta"]["vet"] = {"allow_text": ["Untitled"]}
    assert check_editorial(HTML, d).passed


def test_meta_vet_is_valid_schema():
    d = _story()
    d["meta"]["vet"] = {"allow_text": ["XXX"]}
    Story.model_validate(d)


def test_to_json_names_the_scene_of_an_editorial_failure():
    ed = Dimension("Editorial integrity")
    check = check_editorial(HTML, _story(source_line="Source: {{source}}"))
    ed.issues, ed.passed = check.issues, check.passed
    f = Report("x.html", "data.json", [ed]).to_json()["failures"]
    assert f and f[0]["scene"] == "s1", f
