"""Browser e2e for #11 milestone 2: a story drafted by the `dstory draft` CLI
(points-based share prose + the new bump-chart scene) renders offline and
passes the full browser vet."""
import os
import subprocess
import sys

import pytest

pytest.importorskip("playwright.sync_api")
pd = pytest.importorskip("pandas")

from dstory import vet  # noqa: E402

ROWS = []
for _y, _coal, _gas, _ren, _nuc in [(2014, 39, 27, 15, 19), (2016, 34, 33, 15, 18),
                                    (2018, 28, 36, 18, 18), (2020, 22, 38, 21, 19),
                                    (2022, 18, 41, 22, 19), (2024, 15, 43, 23, 19)]:
    ROWS += [(_y, "Coal", _coal), (_y, "Gas", _gas), (_y, "Renewables", _ren), (_y, "Nuclear", _nuc)]


@pytest.fixture(scope="module")
def drafted(tmp_path_factory):
    d = tmp_path_factory.mktemp("cli")
    pd.DataFrame(ROWS, columns=["year", "source", "share_pct"]).to_csv(d / "grid_mix.csv", index=False)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, "-m", "dstory.cli", "draft", "grid_mix.csv", "--vendor",
                           "--no-vet", "--source", "Synthetic grid data"],
                          cwd=d, env=env, capture_output=True, timeout=300)
    if proc.returncode != 0:
        out = proc.stdout.decode("utf-8")
        if "vendor" in out.lower() and "network" in out.lower():
            pytest.skip("vendoring needs network at build time")
        raise AssertionError(out + proc.stderr.decode("utf-8"))
    return d / "grid_mix"


def test_cli_drafted_story_renders_offline(drafted):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:
            pytest.skip(f"Chromium unavailable: {e}")
        ctx = b.new_context(viewport={"width": 1280, "height": 900})
        ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith("file:") else r.abort())
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto((drafted / "dist" / "story.html").as_uri(), wait_until="load")
        race = page.locator("#scene-race")
        race.scroll_into_view_if_needed()
        page.wait_for_selector('[data-mount="scene-race"] svg path', timeout=8000)
        text = page.inner_text("body")
        assert "Gas overtook Coal to rank first by 2024" in text
        assert "Coal share fell 24 points between 2014 and 2024" in text
        assert "Renewables share, by contrast, rose 8 points." in text
        # The new leader is the one highlighted line in the bump chart.
        labels = page.eval_on_selector_all('[data-mount="scene-race"] svg text',
                                           "els => els.map(e => e.textContent)")
        assert any("Gas" in t for t in labels) and any("Coal" in t for t in labels)
        assert not errors, errors
        b.close()


def test_cli_drafted_story_passes_full_browser_vet(drafted):
    report = vet(drafted / "dist" / "story.html", data=drafted / "data.json", browser=True)
    assert report.complete, report.skipped
    assert report.passed, [i for d in report.dimensions for i in d.issues]
