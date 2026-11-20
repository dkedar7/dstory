"""Sweep 2026-11-20 hardening: the CLI prints text with square brackets as-is.
Rich read `[vet]` in 'pip install "dstory[vet]"' as markup and dropped it, so
a first-time user without Playwright was told to run `pip install "dstory"`."""
from __future__ import annotations

import io

from rich.console import Console

from dstory import cli
from dstory.vet import Dimension, Report


def test_report_keeps_brackets_in_issues_notes_and_skips(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=buf, width=240, color_system=None))
    rep = Report(html_path="s.html", data_path="d.json", dimensions=[
        Dimension(name="Visual quality", skipped=True,
                  notes=['Skipped (no browser available: Playwright not installed '
                         '(pip install "dstory[vet]")).']),
        Dimension(name="Data fidelity", passed=False,
                  issues=["Column sales[usd] has [red]odd[/red] values."]),
    ])
    assert cli._print_report(rep, "s.html") is False
    out = buf.getvalue()
    assert 'pip install "dstory[vet]"' in out
    assert "sales[usd]" in out and "[red]odd[/red]" in out
