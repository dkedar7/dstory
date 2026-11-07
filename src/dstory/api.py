"""One-call build: Story → bundled HTML, notebook-friendly.

`build()` collapses the project-directory ritual (init → write data.json →
write scenes → bundle → vet) into a single call, so a data scientist can go
from DataFrames to a shippable story.html in one notebook cell:

    from dstory import Story, build
    from dstory.prep import to_records

    story = Story.model_validate({
        "meta": {"title": "Q1 Growth", "theme": "scientific-bright"},
        "scenes": [{"id": "scene-growth", "kind": "vizzu", "dataset": "users",
                    "series": [...], "frames": [...]}],
        "datasets": {"users": to_records(df)},
    })
    result = build(story, "q1-growth")
    result.html  # → q1-growth/dist/story.html

Vizzu scenes need no JavaScript at all; for bespoke D3 scenes pass their
source via `scenes={"scene-id": js_source}` (or start from a cookbook recipe).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

from .brand import Brand, list_presets
from .bundle import bundle as bundle_project, BundleResult
from .scaffold import init, write_scene
from .schema import Story
from .vet import vet as vet_html, Report


@dataclass
class BuildResult:
    project: Path
    html: Path
    bundle: BundleResult
    report: Optional[Report] = None

    @property
    def passed(self) -> Optional[bool]:
        """Vet verdict — True/False when vetted, None when vet wasn't run."""
        return self.report.passed if self.report else None

    def __repr__(self) -> str:
        verdict = {True: "PASS", False: "BLOCKED", None: "not vetted"}[self.passed]
        return (f"BuildResult(html={str(self.html)!r}, "
                f"{self.bundle.size_bytes / 1024:.1f} KB, vet={verdict})")


def build(
    story: Union[Story, dict[str, Any]],
    path: str | Path,
    *,
    brand: Union[Brand, str, None] = None,
    scenes: Optional[dict[str, str]] = None,
    vendor: bool = False,
    vet: bool = False,
    browser: Optional[bool] = None,
    overwrite: bool = True,
    check_claims: bool = True,
) -> BuildResult:
    """Scaffold + write + bundle (+ vet) a story in one call.

    Args:
        story: a validated Story or a plain dict matching the data.json schema.
        path: project directory to create (re-running overwrites framework
              files; your data/scenes come from the arguments each time).
        brand: Brand instance or preset name. Defaults to meta.theme, which
               must name a bundled preset (an unknown name raises ValueError
               listing the presets). Pass brand= to use a custom Brand.
        scenes: optional {scene_id: js_source} of custom renderers to write
                and wire. Vizzu scenes don't need one.
        vendor: inline the CDN runtime libs for a fully offline bundle
                (needs network at build time; see bundle()).
        vet: run the vetter on the result and attach the Report.
        browser: browser-driven vet checks (renders, charts paint, visual).
                 None (default) runs them whenever Playwright + Chromium are
                 available and warns when they can't run; True requires them;
                 False skips them (static checks only).
        overwrite: allow writing into an existing directory (default True —
                   notebook cells re-run).
        check_claims: refuse to bundle when a claim's text contradicts its
                      value (e.g. "tripled" for 1.2). Default True.

    Returns:
        BuildResult with .html (the bundled file), .bundle stats, and
        .report / .passed when vet=True.
    """
    from .draft import _maybe_draft  # a pandas DataFrame → dstory.draft() first
    story, scenes = _maybe_draft(story, path, brand=brand, scenes=scenes, vendor=vendor)
    story_obj = story if isinstance(story, Story) else Story.model_validate(story)
    meta = story_obj.meta

    if brand is None:
        presets = list_presets()
        if meta.theme not in presets:
            raise ValueError(
                f"Unknown theme preset {meta.theme!r} in meta.theme. "
                f"Available: {', '.join(presets)}. "
                "(To use a custom brand, pass brand=Brand(...).)"
            )
        brand = meta.theme

    project = init(
        path, brand=brand, audience=meta.audience, mode=meta.mode,
        title=meta.title, overwrite=overwrite,
    )
    (project / "data.json").write_text(
        story_obj.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
    )
    for scene_id, js in (scenes or {}).items():
        write_scene(project, scene_id, js)

    bundle_result = bundle_project(project, validate=True, vendor=vendor,
                                   check_claims=check_claims)

    report: Optional[Report] = None
    if vet:
        report = vet_html(bundle_result.out, data=project / "data.json", browser=browser)
        if report.skipped and browser is not False:  # explicit False = caller's choice
            reason = next((n for d in report.dimensions if d.skipped for n in d.notes), "")
            warnings.warn(
                f"Vetting was partial: {', '.join(report.skipped)} did not run. {reason} "
                "result.passed only covers the static checks.",
                UserWarning, stacklevel=2,
            )

    return BuildResult(
        project=project, html=bundle_result.out,
        bundle=bundle_result, report=report,
    )
