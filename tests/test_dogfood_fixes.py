"""Regression tests for the nightly dogfood issues #1-#5.

#1 "</script>" in data.json broke out of the inline data script.
#2 compute_claim produced claims that failed vetting, and false claims that passed.
#3 the browser vetter passed stories whose charts painted nothing.
#4 the CLI crashed with UnicodeEncodeError on cp1252 consoles.
#5 `--vendor` bundles got a false dual-axis note from the inlined d3 source.
"""
import json
import os
import re
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from dstory import build
from dstory.bundle import _json_for_script
from dstory.prep import (
    RATIO_WINDOWS, PctChange, Ratio, compute_claim, compute_pct_change,
    compute_ratio, derive_claim_text,
)
from dstory.vet import check_data_fidelity, check_static_a11y

PAYLOAD = "</script><script>window.__pwn=1</script><!--"


# ---------- #1: inert data embed ----------

def test_json_for_script_has_no_raw_angle_brackets():
    s = _json_for_script({"t": PAYLOAD, "ls": "a b"})
    assert "<" not in s
    assert " " not in s
    assert json.loads(s) == {"t": PAYLOAD, "ls": "a b"}


def test_bundled_story_keeps_script_payload_inside_the_data(tmp_path: Path):
    res = build(
        {"meta": {"title": f"Q1 {PAYLOAD}"},
         "scenes": [{"id": "s1", "kind": "simple", "headline": "Hello", "dataset": "d"}],
         "datasets": {"d": [{"label": PAYLOAD, "value": 1}]}},
        tmp_path / "inj",
    )
    html = res.html.read_text(encoding="utf-8")
    m = re.search(r"<script>window\.__STORY_DATA__ = (.*?);</script>", html, re.S)
    assert m, "data script missing"
    data = json.loads(m.group(1))
    assert data["meta"]["title"] == f"Q1 {PAYLOAD}"
    assert data["datasets"]["d"][0]["label"] == PAYLOAD
    assert "window.__pwn=1</script>" not in html


# ---------- #2: compute_claim is unit-aware and always vets ----------

def _fidelity(claim: dict) -> bool:
    return check_data_fidelity("", {"claims": [claim]}).passed


@pytest.mark.parametrize("after", [370, 500, 800, 1000, 1020, 1500, 1860, 1950, 2000,
                                   2130, 2900, 3000, 3400, 4000, 5000, 7000])
def test_compute_claim_always_passes_vet(after: int):
    for value in (compute_ratio(after=after, before=1000),
                  compute_pct_change(after=after, before=1000)):
        claim = compute_claim(id="c", text_template="Signups {phrase} in Q1", value=value)
        assert claim["unit"] in ("ratio", "pct")
        assert _fidelity(claim), claim


def test_ratio_never_printed_as_percent_of_itself():
    claim = compute_claim(id="c", text_template="{phrase}", value=compute_ratio(after=3400, before=1000))
    assert claim["text"] == "increased by 240.0%"
    assert claim["unit"] == "ratio"


def test_small_pct_change_never_called_doubled():
    claim = compute_claim(id="c", text_template="{phrase}", value=compute_pct_change(after=102, before=100))
    assert claim["text"] == "increased by 2.0%"
    assert derive_claim_text(2.0, kind="pct") == "increased by 2.0%"
    assert derive_claim_text(100.0, kind="pct") == "doubled"


def test_phrases_only_inside_vetter_windows():
    assert derive_claim_text(1.86, kind="ratio") == "increased by 86.0%"
    assert derive_claim_text(2.13, kind="ratio") == "increased by 113.0%"
    assert derive_claim_text(0.37, kind="ratio") == "decreased by 63.0%"
    for word, (lo, hi) in RATIO_WINDOWS.items():
        assert derive_claim_text(lo, kind="ratio") == word
        assert derive_claim_text(hi, kind="ratio") == word


def test_tagged_values_are_floats():
    r = compute_ratio(after=3, before=1)
    p = compute_pct_change(after=3, before=1)
    assert isinstance(r, Ratio) and isinstance(r, float) and r == 3.0
    assert isinstance(p, PctChange) and p == 200.0
    assert json.loads(json.dumps({"v": r})) == {"v": 3.0}


def test_plain_float_with_auto_warns_and_explicit_kind_does_not():
    with pytest.warns(UserWarning, match="ambiguous|can't tell"):
        claim = compute_claim(id="c", text_template="{phrase}", value=2.0)
    assert "unit" not in claim
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        claim = compute_claim(id="c", text_template="{phrase}", value=2.0, kind="pct")
    assert claim["unit"] == "pct" and claim["text"] == "increased by 2.0%"


@pytest.mark.parametrize("claim", [
    {"id": "c", "text": "Signups doubled", "value": 1.02, "unit": "ratio"},
    {"id": "c", "text": "Signups doubled", "value": 2.0, "unit": "pct"},
    {"id": "c", "text": "Signups increased by 3.4%", "value": 3.4, "unit": "ratio"},
    {"id": "c", "text": "Signups decreased by 20%", "value": 20, "unit": "pct"},
    {"id": "c", "text": "Signups increased by 20%", "value": -20},
])
def test_false_claims_fail_vet(claim):
    assert not _fidelity(claim)


@pytest.mark.parametrize("claim", [
    {"id": "c", "text": "Signups decreased by 20%", "value": -20},
    {"id": "c", "text": "Signups decreased by 20%", "value": 0.8, "unit": "ratio"},
    {"id": "c", "text": "Most users (62%) said yes", "value": 0.62},
    {"id": "c", "text": "A majority said yes", "value": 0.62},
])
def test_true_claims_pass_vet(claim):
    assert _fidelity(claim)


def test_claim_unit_accepted_by_schema():
    from dstory.schema import Claim
    assert Claim(id="c", text="t", value=2.0, unit="ratio").unit == "ratio"
    with pytest.raises(Exception):
        Claim(id="c", text="t", value=2.0, unit="fold")


# ---------- #4: CLI survives a cp1252 console ----------

def test_cli_recipes_on_cp1252_console():
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    proc = subprocess.run([sys.executable, "-m", "dstory.cli", "recipes"],
                          capture_output=True, env=env, timeout=120)
    assert proc.returncode == 0, proc.stderr.decode("cp1252", "replace")
    assert b"UnicodeEncodeError" not in proc.stderr


def test_cli_vet_with_arrow_on_cp1252_console(tmp_path: Path):
    res = build({"meta": {"title": "T"},
                 "scenes": [{"id": "s1", "kind": "simple", "headline": "Signups grew. Learn more →"}]},
                tmp_path / "slop")
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    proc = subprocess.run([sys.executable, "-m", "dstory.cli", "vet", str(res.html),
                           "--data", str(tmp_path / "slop" / "data.json"), "--no-browser"],
                          capture_output=True, env=env, timeout=120)
    assert b"UnicodeEncodeError" not in proc.stderr
    assert b"OVERALL" in proc.stdout


# ---------- #5: vendored library code doesn't trip static notes ----------

def test_vendored_d3_does_not_trigger_dual_axis_note():
    html = ('<html lang="en"><script data-vendored="https://cdn.jsdelivr.net/npm/d3@7">'
            "function axisLeft(){} function axisRight(){} var webgl=1;</script></html>")
    notes = " ".join(check_static_a11y(html, {}).notes)
    assert "axisRight" not in notes
    assert "3D" not in notes


def test_author_dual_axis_still_noted():
    html = ('<html lang="en"><script>svg.call(d3.axisLeft(y)); svg.call(d3.axisRight(y2));</script></html>')
    notes = " ".join(check_static_a11y(html, {}).notes)
    assert "axisRight" in notes
