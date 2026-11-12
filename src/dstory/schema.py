"""Pydantic models for data.json — validate structure before bundle, surface
schema drift at author time rather than at vet time.
"""

from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


SceneKind = Literal["simple", "scrolly", "bleed", "pinned", "vizzu", "custom"]
Mode      = Literal["scroll", "slides"]
Audience  = Literal["executive", "general-public", "technical-peer", "student", "policymaker"]
Width     = Literal["narrow", "default", "wide", "full"]


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    url: Optional[str] = None
    accessed: Optional[str] = None


class A11yOptions(BaseModel):
    """The reader-facing data layer under each chart. Every option defaults to
    on; set one to false in meta.a11y (whole story) or scene.a11y (one scene)."""
    model_config = ConfigDict(extra="forbid")
    table: Optional[bool] = None      # a "Data" disclosure with an accessible <table>
    download: Optional[bool] = None   # a "Download CSV" link built from the inlined rows
    explorer: Optional[bool] = None   # keyboard chart explorer + aria-live readout
    sonify: Optional[bool] = None     # a "Listen" button that plays each series as tones


class Meta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    subtitle: Optional[str] = ""
    deck: Optional[str] = ""
    author: Optional[str] = ""
    published: Optional[str] = ""
    theme: str = "editorial-noir"
    audience: Audience = "general-public"
    mode: Mode = "scroll"
    sources: list[Source] = Field(default_factory=list)

    # Language / direction — set on <html lang dir> at bundle time and runtime.
    # lang reaches screen readers and hyphenation; dir="rtl" flips the layout.
    lang: str = "en"
    dir: Literal["ltr", "rtl", "auto"] = "ltr"

    # Sharing — emitted as <meta name="description"> + Open Graph / Twitter
    # card tags at bundle time. description falls back to deck, then subtitle.
    # share_image must be an absolute URL (data URIs don't work for og:image).
    description: Optional[str] = ""
    share_image: Optional[str] = None

    # Full-bleed hero background image. A project-relative path is inlined as
    # a data URI at bundle time; an absolute URL is left as-is. Decorative —
    # the hero text carries the content, so no alt is needed.
    hero_image: Optional[str] = None

    # The data panel under every chart (table + CSV download); all on by default.
    a11y: Optional[A11yOptions] = None


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str
    value: Optional[float] = None
    # What `value` measures: "ratio" (after/before, 2.0 == doubled) or "pct"
    # (signed percent change, +50.0 == up 50%) or "pp" (signed change in
    # percentage points, for shares and rates). Omit for legacy claims; the
    # vetter then guesses (0..1 is a share, otherwise percent points).
    unit: Optional[Literal["ratio", "pct", "pp"]] = None
    scene: Optional[str] = None


class Annotation(BaseModel):
    model_config = ConfigDict(extra="allow")
    text: Optional[str] = None
    target: Optional[dict[str, Any]] = None


class Step(BaseModel):
    model_config = ConfigDict(extra="allow")
    headline: str
    commentary: Optional[str] = ""
    state: Optional[str] = None  # custom step-state hint for the renderer


class VizzuChannelConfig(BaseModel):
    """A frame's chart configuration. Pass-through to Vizzu — `extra=allow`
    so future Vizzu options work without schema updates.
    """
    model_config = ConfigDict(extra="allow")
    channels: dict[str, Any]
    geometry: Optional[Literal["rectangle", "line", "area", "circle"]] = None
    title: Optional[str] = None


class VizzuFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    headline: str
    commentary: Optional[str] = ""
    config: VizzuChannelConfig


class SeriesSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    type: Literal["dimension", "measure"] = "dimension"


class Scene(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    kind: SceneKind = "simple"
    headline: Optional[str] = ""
    commentary: Optional[str] = ""
    source_line: Optional[str] = ""
    dataset: Optional[str] = None

    # alt: text alternative for the chart, set as role="img" + aria-label on
    # the mount. One sentence stating what the chart shows AND the takeaway,
    # e.g. "Line chart: monthly users tripled from 1,000 to 2,900 over Q1."
    alt: Optional[str] = None

    # Layout controls
    # width: per-scene column width override.
    #   "narrow" = ~36rem (intimate text), "default" = ~56rem, "wide" = ~78rem, "full" = 100vw
    width:  Width = "default"
    # chrome: when False, the scene is rendered without h2/p/source elements;
    #   the renderer owns the entire mount. Use for kinetic typography, custom
    #   layouts, or any scene where the package's defaults get in the way.
    chrome: bool = True

    # scrolly: list of step text panels (chart code is in scenes/<id>.js)
    steps: Optional[list[Step]] = None

    # vizzu: declarative frame sequence
    series: Optional[list[SeriesSpec]] = None
    frames: Optional[list[VizzuFrame]] = None
    style:  Optional[dict[str, Any]] = None
    duration: Optional[float] = None  # seconds

    # arbitrary scene-specific config
    annotation: Optional[Annotation] = None
    config: Optional[dict[str, Any]] = None

    # The data panel: per-scene overrides of meta.a11y, and which dataset
    # columns its table and CSV show (default: every column, in row order).
    a11y: Optional[A11yOptions] = None
    table_columns: Optional[list[str]] = None
    # How the table shows a numeric column: "raw" (no thousands separator, for
    # years, IDs and codes) or "number". Default: integer columns named like
    # year/id/code/fips/zip, or holding only values 1000-2999, are raw.
    table_format: Optional[dict[str, Literal["raw", "number"]]] = None

    @field_validator("id")
    @classmethod
    def _id_is_slug(cls, v: str) -> str:
        if not v or not all(c.isalnum() or c in "-_" for c in v):
            raise ValueError(f"Scene id {v!r} must be a slug (alphanumeric, hyphens, underscores).")
        return v


class Story(BaseModel):
    """The full data.json contract. Use Story.parse_file('data.json') to load
    and validate; .dict() / .model_dump_json() to serialize back."""
    model_config = ConfigDict(extra="forbid")
    meta: Meta
    claims: list[Claim] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)
    datasets: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)

    # Optional: additional CSS appended to story.css at bundle time.
    # Use for layout overrides that the package's defaults don't cover —
    # e.g. ".scene--my-custom { display: grid; ... }". Avoids the workflow
    # of writing to story.css after init() runs (which is fragile).
    extra_css: Optional[str] = None

    @field_validator("scenes")
    @classmethod
    def _unique_ids(cls, v: list[Scene]) -> list[Scene]:
        ids = [s.id for s in v]
        dups = {x for x in ids if ids.count(x) > 1}
        if dups:
            raise ValueError(f"Duplicate scene ids: {sorted(dups)}")
        return v

    def dataset_keys_in_use(self) -> set[str]:
        keys = set()
        for s in self.scenes:
            if s.dataset:
                keys.add(s.dataset)
        return keys

    def validate_dataset_refs(self) -> list[str]:
        """Return a list of issues: scenes referencing missing datasets."""
        issues = []
        for s in self.scenes:
            if s.dataset and s.dataset not in self.datasets:
                issues.append(f"Scene {s.id!r} references dataset {s.dataset!r} which is not in data.datasets.")
            elif s.dataset and (s.table_columns or s.table_format):
                rows = self.datasets.get(s.dataset) or []
                present = {k for r in rows if isinstance(r, dict) for k in r}
                for field, named in (("table_columns", s.table_columns or []),
                                     ("table_format", list(s.table_format or {}))):
                    missing = [c for c in named if c not in present]
                    if rows and missing:
                        issues.append(f"Scene {s.id!r} {field} {missing} are not columns of "
                                      f"dataset {s.dataset!r} (it has {sorted(present)}).")
            issues.extend(_vizzu_channel_issues(s))
        return issues


def vizzu_channel_series(value: Any) -> list[str]:
    """Series names referenced by one Vizzu channel value.

    Accepts the forms Vizzu does: "name", ["a", "b"], {"set": ...}, None.
    Aggregator expressions such as "count()" are not series names and are skipped.
    """
    if value is None:
        return []
    if isinstance(value, dict):
        return vizzu_channel_series(value.get("set"))
    if isinstance(value, str):
        return [] if "(" in value else [value]
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for v in value:
            out.extend(vizzu_channel_series(v))
        return out
    return []


def _vizzu_channel_issues(scene: "Scene") -> list[str]:
    """A frame channel naming a series the scene doesn't declare fails in the
    browser ("series not found"); catch it at build time instead."""
    if scene.kind != "vizzu" or not scene.series or not scene.frames:
        return []
    declared = {sp.name for sp in scene.series}
    issues = []
    for i, frame in enumerate(scene.frames):
        for channel, value in (frame.config.channels or {}).items():
            for name in vizzu_channel_series(value):
                if name not in declared:
                    issues.append(
                        f"Scene {scene.id!r} frame {i + 1}: channel {channel!r} uses series "
                        f"{name!r}, which is not in the scene's series "
                        f"({', '.join(sorted(declared))})."
                    )
    return issues
