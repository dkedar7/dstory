"""End-to-end Python API smoke test.

Builds a tiny one-scene story using only dstory's Python API:
- Brand.from_preset
- prep helpers (compute_ratio, compute_claim, to_records)
- init() to scaffold
- write data.json directly via the schema
- bundle()
- vet() with browser=False

This is what a Python user would do without ever touching the CLI.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

from dstory import Brand, Story, init, bundle, vet
from dstory.prep import compute_ratio, compute_claim, to_records


def main() -> int:
    out = Path("/tmp/dstory-api-smoke")
    if out.exists():
        shutil.rmtree(out)

    # 1. Pick a brand.
    brand = Brand.from_preset("scientific-bright")

    # 2. Scaffold a project.
    init(out, brand=brand, audience="technical-peer", mode="scroll", title="API Smoke")

    # 3. Build data with pandas + prep helpers.
    df = pd.DataFrame({
        "month": ["2024-01", "2024-02", "2024-03", "2024-04"],
        "users": [1000, 1500, 2900, 3050],
    })

    ratio = compute_ratio(after=df["users"].iloc[-2], before=df["users"].iloc[0])
    claim = compute_claim(
        id="c1",
        text_template="Active users {phrase} between January and March",
        value=ratio,
        scene="scene-growth",
    )
    print(f"  derived claim: {claim['text']!r} (value={claim['value']:.3f})")

    records = to_records(df)

    # 4. Write data.json (via schema for validation).
    story = Story.model_validate({
        "meta": {
            "title": "API Smoke",
            "subtitle": "End-to-end Python API test",
            "author": "dstory test",
            "published": "2026-05-02",
            "theme": "scientific-bright",
            "audience": "technical-peer",
            "mode": "scroll",
            "sources": [{"name": "Synthetic", "url": "https://example.com"}],
        },
        "claims": [claim],
        "scenes": [{
            "id": "scene-growth",
            "kind": "simple",
            "headline": "Active users tripled in Q1",
            "commentary": claim["text"],
            "source_line": "Source: Synthetic, 2024.",
            "dataset": "users",
        }],
        "datasets": {"users": records},
    })
    (out / "data.json").write_text(story.model_dump_json(indent=2), encoding="utf-8")

    # 5. Bundle.
    result = bundle(out)
    print(f"  bundled: {result.out} ({result.size_bytes/1024:.1f} KB)")

    # 6. Vet (skip browser for speed; the static checks are what matters here).
    report = vet(result.out, data=out / "data.json", browser=False)
    for d in report.dimensions:
        marker = "✓" if d.passed else "✗"
        print(f"  {marker} {d.name}")
        for i in d.issues:
            print(f"      issue: {i}")
    print(f"  OVERALL: {'PASS' if report.passed else 'BLOCKED'}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
