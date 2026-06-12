"""Schema validation: catches author-time errors that the vetter would otherwise
hit at delivery time."""
import json
import pytest
from pydantic import ValidationError

from dstory.schema import Story, Scene, Meta, Claim


def _minimal_story() -> dict:
    return {
        "meta": {"title": "T", "theme": "editorial-noir", "audience": "general-public"},
        "claims": [],
        "scenes": [],
        "datasets": {},
    }


def test_minimal_story_validates():
    s = Story.model_validate(_minimal_story())
    assert s.meta.title == "T"
    assert s.meta.mode == "scroll"  # default
    assert s.scenes == []


def test_unknown_meta_field_rejected():
    raw = _minimal_story()
    raw["meta"]["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        Story.model_validate(raw)


def test_scene_id_must_be_slug():
    raw = _minimal_story()
    raw["scenes"] = [{"id": "bad id with spaces", "kind": "simple"}]
    with pytest.raises(ValidationError):
        Story.model_validate(raw)


def test_duplicate_scene_ids_rejected():
    raw = _minimal_story()
    raw["scenes"] = [
        {"id": "scene-a", "kind": "simple"},
        {"id": "scene-a", "kind": "bleed"},
    ]
    with pytest.raises(ValidationError):
        Story.model_validate(raw)


def test_dataset_ref_validation():
    raw = _minimal_story()
    raw["scenes"] = [{"id": "s1", "kind": "simple", "dataset": "missing"}]
    s = Story.model_validate(raw)
    issues = s.validate_dataset_refs()
    assert len(issues) == 1
    assert "missing" in issues[0]


def test_vizzu_frame_passthrough():
    raw = _minimal_story()
    raw["scenes"] = [{
        "id": "s-pivot",
        "kind": "vizzu",
        "dataset": "d1",
        "series": [{"name": "X", "type": "dimension"}, {"name": "Y", "type": "measure"}],
        "frames": [{
            "headline": "h",
            "config": {
                "channels": {"x": "X", "y": "Y"},
                "geometry": "rectangle",
                "title": "t",
            },
        }],
    }]
    raw["datasets"]["d1"] = [{"X": "a", "Y": 1}]
    s = Story.model_validate(raw)
    assert s.scenes[0].frames[0].config.geometry == "rectangle"


def test_audience_enum_enforced():
    raw = _minimal_story()
    raw["meta"]["audience"] = "totally-bogus"
    with pytest.raises(ValidationError):
        Story.model_validate(raw)


def test_mode_enum_enforced():
    raw = _minimal_story()
    raw["meta"]["mode"] = "click"
    with pytest.raises(ValidationError):
        Story.model_validate(raw)
