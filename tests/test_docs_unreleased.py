"""#32: docs that run ahead of the PyPI release must say so."""
from __future__ import annotations


def test_docs_say_mcp_is_unreleased_until_it_ships():
    """#32: the README and docs site describe `dstory mcp` before PyPI has it.
    The "Coming in 0.14" note must stay until 0.14, and go when 0.14 ships."""
    from pathlib import Path

    import dstory

    root = Path(__file__).resolve().parents[1]
    released = tuple(int(x) for x in dstory.__version__.split(".")[:2]) >= (0, 14)
    for name in ("README.md", "docs/index.html"):
        text = (root / name).read_text(encoding="utf-8")
        assert "dstory mcp" in text
        has_note = "Coming in 0.14" in text
        assert has_note is not released, (
            f"{name}: remove the 'Coming in 0.14' note now that 0.14 is out" if released
            else f"{name}: documents `dstory mcp` without saying it is not on PyPI yet")
