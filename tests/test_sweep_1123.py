"""Sweep 2026-11-23: #44, story data must never become script in the
reader's browser. meta.lang is attribute-escaped, extra_css cannot close its
<style>, a javascript: source is shown without a link, and the vetter fails
all three instead of saying "safe to deliver"."""
from __future__ import annotations

import pytest

from dstory import build
from dstory.bundle import safe_url
from dstory.vet import check_static_a11y

EVIL_LANG = 'en"><script>document.title="PWNED"</script><x y="'
EVIL_CSS = "body{color:red}</style><script>document.title='PWNED-css'</script><style>"
META = {"title": "Lang test", "published": "2026-11-23", "sources": [{"name": "S"}]}


def _build(tmp_path, name, **story):
    story = {"meta": dict(META), "scenes": [], "datasets": {}, **story}
    return build(story, tmp_path / name, vet=False)


def _static(res):
    import json
    html = res.html.read_text(encoding="utf-8")
    data = json.loads((res.project / "data.json").read_text(encoding="utf-8"))
    return html, check_static_a11y(html, data)


def test_lang_is_escaped_and_vet_fails_it(tmp_path):
    res = _build(tmp_path, "lang", meta=dict(META, lang=EVIL_LANG))
    html, dim = _static(res)
    head = html[:html.index("<head")]
    assert "<script" not in head and "&lt;script&gt;" in head, head
    assert not dim.passed
    assert any("meta.lang" in i and "markup" in i for i in dim.issues), dim.issues
    assert any("not a language tag" in w for w in res.bundle.warnings), res.bundle.warnings


def test_extra_css_cannot_close_its_style_block(tmp_path):
    res = _build(tmp_path, "css", extra_css=EVIL_CSS)
    html, dim = _static(res)
    block = html[html.index('data-src="story.extra_css"'):]
    block = block[:block.index("</style>")]
    assert "PWNED-css" in block and "<\\/style>" in block      # still inside the style
    assert "<script>document.title='PWNED-css'" not in html.replace(block, "")
    assert not dim.passed and any("extra_css" in i for i in dim.issues), dim.issues
    assert any("extra_css" in w for w in res.bundle.warnings)


@pytest.mark.parametrize("url,ok", [
    ("https://eia.gov/x", True), ("http://a.org", True), ("mailto:a@b.org", True),
    ("docs/a.pdf", True), ("#notes", True), ("www.eia.gov/x", True),
    ("javascript:alert(1)", False), (" JavaScript:alert(1)", False),
    ("java\tscript:alert(1)", False), ("\x01javascript:x", False),
    ("data:text/html,<b>x</b>", False), ("vbscript:x", False),
])
def test_safe_url(url, ok):
    assert safe_url(url) is ok


def test_vet_fails_a_javascript_source(tmp_path):
    res = _build(tmp_path, "src", meta=dict(META, sources=[
        {"name": "Ledger", "url": "javascript:alert(1)"}, {"name": "EIA", "url": "https://eia.gov"}]))
    _, dim = _static(res)
    assert any("sources[0].url" in i for i in dim.issues), dim.issues
    assert not any("sources[1]" in i for i in dim.issues)


def test_a_clean_story_has_no_injection_failures(tmp_path):
    res = _build(tmp_path, "ok", meta=dict(META, lang="pt-BR"), extra_css="h1{color:red}")
    html, dim = _static(res)
    assert 'lang="pt-BR"' in html
    assert not any(k in i for i in dim.issues for k in ("meta.lang", "extra_css", "before <head>"))
    assert not any("language tag" in w or "extra_css" in w for w in res.bundle.warnings)


def test_nothing_runs_in_the_browser(tmp_path):
    """The issue's check: open each bundle and read document.title."""
    pytest.importorskip("playwright.sync_api")
    from dstory.vet import browser_available
    ok, why = browser_available()
    if not ok:
        pytest.skip(why)
    from playwright.sync_api import sync_playwright
    pages = {
        "lang": _build(tmp_path, "lang", meta=dict(META, lang=EVIL_LANG)).html,
        "css": _build(tmp_path, "css", extra_css=EVIL_CSS).html,
        "src": _build(tmp_path, "src", meta=dict(META, sources=[
            {"name": "Ledger", "url": "java\tscript:alert(1)"},
            {"name": "EIA", "url": "https://eia.gov"}])).html,
    }
    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, html in pages.items():
            page = b.new_page()
            page.route("**/*", lambda r: r.continue_() if r.request.url.startswith("file:")
                       else r.abort())
            page.goto(html.as_uri(), wait_until="load")
            page.wait_for_function("document.querySelectorAll('#sources li').length > 0",
                                   timeout=15000)
            assert "PWNED" not in page.title(), name
            if name == "src":
                hrefs = page.eval_on_selector_all("#sources a", "as => as.map(a => a.href)")
                assert hrefs == ["https://eia.gov/"], hrefs
                assert "Ledger" in page.inner_text("#sources")
            page.close()
        b.close()
