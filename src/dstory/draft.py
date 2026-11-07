"""Zero-config drafting: a pandas DataFrame in, a vetted story draft out.

`draft(df, title=...)` profiles the columns, picks scenes from fixed rules,
maps each onto a cookbook recipe via `scene.config`, and writes headlines,
commentary and alt text from computed facts. Every number in the generated
headlines and commentary is part of a registered claim, built with
`compute_pct_change()` + `compute_claim()`, so the data-fidelity vetter checks
it against the value it came from.

Deterministic, offline, and keyless: no model calls, no network.

    import pandas as pd, dstory
    d = dstory.draft(pd.read_csv("energy.csv"), title="The grid turns")
    print(d.explain())
    dstory.build(d.story, "grid", scenes=d.scenes, vet=True)

Rules:
  * time x measure                    -> line-reveal
  * category x first/last period      -> slope-chart
  * the top-ranked category changed   -> bump-chart
  * shares summing to ~100 (or ~1)    -> waffle
  * nothing matched                   -> one bar-steps scene (always safe)

Shares and rates that sum to ~100 are compared in percentage points ("fell
24 points"), never as a relative change. Changes across zero are described
("turned negative in 2023"), never as a percent.

pandas is optional for dstory as a whole; this module imports it lazily and
raises an ImportError pointing at the [prep] extra when it is missing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

from .brand import list_presets
from .cookbook import recipe_js
from .prep import (
    compute_claim, compute_pct_change, compute_point_change, fmt_compact, fold_phrase,
    ratio_phrase, to_long, PctChange, PointChange,
)
from .schema import Story

_PREP_HINT = 'dstory.draft() needs pandas. Install it with: pip install "dstory[prep]"'

# Name tokens that mark a column as time-like (when its values are years).
_TIME_TOKENS = {"year", "years", "yr", "fy", "season", "period", "date", "month",
                "quarter", "time", "week", "day"}
# Name tokens that mark a measure as non-additive: summing it across
# categories would be meaningless (an average of rates, a sum of prices...).
_NON_ADDITIVE_TOKENS = {"rate", "rates", "pct", "percent", "percentage", "share", "avg",
                        "average", "mean", "median", "index", "price", "score", "ratio",
                        "per", "expectancy", "temperature", "temp", "age", "density", "yield"}
_ID_TOKENS = {"id", "uuid", "guid", "key"}
_YEAR_STR = re.compile(r"^\d{4}$")
_MONTH_STR = re.compile(r"^[A-Za-z]{3,9}\.? \d{4}$")            # "Jan 2024", "March 2024"
_QUARTER_STR = re.compile(r"^(?:(\d{4})\s*-?\s*Q([1-4])|Q([1-4])\s*-?\s*(\d{4}))$", re.I)
# Spreadsheet number formatting to strip before parsing: "$1,200", "12%", "(5)".
_NUM_JUNK = re.compile(r"[\s,$\u00a3\u20ac\u00a5%]")
# A text column becomes a measure when at least this share of its non-blank
# values parse as numbers; the rest are dropped and reported.
NUMERIC_COERCE_MIN = 0.8
_DATE_STR = re.compile(r"^\d{4}-\d{2}(-\d{2})?([T ].*)?$")

MAX_SLOPE_CATEGORIES = 10
MAX_WAFFLE_CATEGORIES = 7     # the waffle palette has 7 categorical colors
MAX_BAR_ROWS = 12
MAX_BUMP_CATEGORIES = 10
MAX_OPENER_CATEGORIES = 7
MAX_OPENER_PERIODS = 20
MAX_BUMP_PERIODS = 12


# ---------- public types ----------

@dataclass
class ColumnProfile:
    """What draft() concluded about one column."""
    name: str
    role: str            # "temporal" | "categorical" | "measure" | "id" | "constant" | "other"
    cardinality: int
    detail: str = ""     # e.g. "year", "datetime", "summed per period"

    def describe(self) -> str:
        extra = f", {self.detail}" if self.detail else ""
        return f"{self.name}: {self.role} ({self.cardinality} distinct{extra})"


@dataclass
class Draft:
    """A drafted story: edit `.story` like any data.json, then build it.

    Attributes:
        story:   a plain dict valid against the Story schema (data.json shape).
        scenes:  {scene_id: js_source} for each recipe-backed scene.
        reasons: one line per scene (chosen or skipped) explaining the rule.
        profile: the column profile the rules ran on.
        shape:   a one-line description of the table shape (long / wide).
    """
    story: dict[str, Any]
    scenes: dict[str, str]
    reasons: list[str] = field(default_factory=list)
    profile: list[ColumnProfile] = field(default_factory=list)
    shape: str = ""

    def explain(self) -> str:
        """Human-readable account of the profile and why each scene was chosen."""
        lines = [f"Profile: {self.shape}"]
        lines += [f"  {p.describe()}" for p in self.profile]
        cleaned = [r for r in self.reasons if r.startswith("(cleaned)")]
        lines += [f"  {r}" for r in cleaned]
        lines.append("Scenes:")
        lines += [f"  {r}" for r in self.reasons if r not in cleaned]
        claims = self.story.get("claims", [])
        if claims:
            lines.append(f"Claims ({len(claims)}), each checked by the vetter:")
            lines += [f"  {c['id']}: {c['text']}" for c in claims]
        return "\n".join(lines)

    def to_project(self, path: str | Path, *, overwrite: bool = False) -> Path:
        """Write a normal dstory project (data.json + scenes/*.js, wired).

        Bundle and vet it afterwards like any hand-written project:
        `dstory bundle <path>` then `dstory vet <path>/dist/story.html --data <path>/data.json`.
        """
        from .scaffold import init, write_scene

        meta = self.story["meta"]
        project = init(path, brand=meta.get("theme", "editorial-noir"),
                       audience=meta.get("audience", "general-public"),
                       mode=meta.get("mode", "scroll"), title=meta["title"],
                       overwrite=overwrite)
        (project / "data.json").write_text(
            json.dumps(self.story, indent=2, ensure_ascii=False), encoding="utf-8")
        for scene_id, js in self.scenes.items():
            write_scene(project, scene_id, js)
        return project

    def __repr__(self) -> str:
        ids = [s["id"] for s in self.story.get("scenes", [])]
        return f"Draft(title={self.story['meta']['title']!r}, scenes={ids})"


# ---------- entry points ----------

def draft(
    df: Any,
    *,
    title: str,
    theme: Optional[str] = None,
    audience: str = "general-public",
    mode: str = "scroll",
    max_scenes: int = 5,
    opener: bool = True,
    source: Optional[str] = None,
) -> Draft:
    """Draft a vetted story from a DataFrame, with no configuration.

    Args:
        df: a pandas DataFrame, long (one row per observation) or wide (one
            column per series, or one column per period).
        title: the story title (meta.title).
        theme: a bundled theme preset name (see dstory.list_presets()).
        audience, mode: written to meta, as in data.json.
        max_scenes: cap on the number of scenes (rules run in a fixed order).
        opener: open with an animated Vizzu scene when the measure is additive
                across categories over time (the total stacks, then splits
                into one line per category). False keeps the D3 line chart.
        source: citation for the data; written to meta.sources and each
                scene's source_line.

    Returns:
        A Draft with .story (dict), .scenes ({id: js}), .explain(), .to_project().
    """
    pd = _require_pandas()
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"draft() takes a pandas DataFrame, got {type(df).__name__}.")
    if df.empty:
        raise ValueError("draft() got an empty DataFrame.")
    if theme is not None and theme not in list_presets():
        raise ValueError(f"Unknown theme {theme!r}. Available: {', '.join(list_presets())}")
    if max_scenes < 1:
        raise ValueError("max_scenes must be at least 1.")
    return _Drafter(pd, df, title=title, theme=theme, audience=audience, mode=mode,
                    max_scenes=max_scenes, source=source, opener=opener).run()


def _is_dataframe(obj: Any) -> bool:
    t = type(obj)
    return t.__name__ == "DataFrame" and t.__module__.split(".")[0] == "pandas"


def _maybe_draft(story: Any, path: str | Path, *, brand: Any,
                 scenes: Optional[dict[str, str]],
                 vendor: bool = False) -> tuple[Any, Optional[dict[str, str]]]:
    """build() hook: a DataFrame becomes draft().story + draft().scenes.

    Anything else is returned untouched, so dict / Story input is unchanged.
    Scenes passed explicitly to build() override the drafted ones.
    """
    if not _is_dataframe(story):
        return story, scenes
    theme = brand if isinstance(brand, str) and brand in list_presets() else None
    title = re.sub(r"[-_]+", " ", Path(path).name).strip() or "Untitled story"
    # Vizzu can't be inlined (it streams WebAssembly), so an offline build
    # keeps the D3 line chart instead of the animated opener.
    d = draft(story, title=_sentence_case(title), theme=theme, opener=not vendor)
    return d.story, {**d.scenes, **(scenes or {})}


def _require_pandas():
    try:
        import pandas as pd  # type: ignore
    except ImportError as e:
        raise ImportError(_PREP_HINT) from e
    return pd


# ---------- prose helpers ----------

def _sentence_case(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _humanize(name: str) -> str:
    """Column name -> words: 'share_pct' -> 'share', 'net_twh' -> 'net twh'."""
    tokens = [t for t in re.split(r"[_\s]+", str(name).strip()) if t]
    kept = [t for t in tokens if t.lower() not in {"pct", "percent", "perc"}]
    return " ".join(kept or tokens) or str(name)


def _pct_str(p: float) -> str:
    """Magnitude of a percentage, rounded but always within the vetter's
    0.5pp tolerance of the true value."""
    mag = abs(p)
    if mag >= 10:
        s = f"{mag:.0f}"
        if abs(float(s) - mag) <= 0.45:
            return s
    return f"{mag:.1f}".removesuffix(".0")


def _change(pct: float) -> str:
    """A verb phrase for a percent change: 'doubled', 'rose 42%', 'fell 7.5%',
    'rose 12-fold'."""
    word = ratio_phrase(1.0 + pct / 100.0)
    if word:
        return word
    fold = fold_phrase(1.0 + pct / 100.0)
    if fold:
        return f"rose {fold}"
    if abs(pct) < 0.05:
        return "held steady, a 0% change"
    return f"{'rose' if pct > 0 else 'fell'} {_pct_str(pct)}%"


def _points(pp: float) -> str:
    """A verb phrase for a change in percentage points: 'fell 24 points'."""
    if abs(pp) < 0.05:
        return "held steady"
    mag = _pct_str(pp)
    return f"{'rose' if pp > 0 else 'fell'} {mag} {'point' if mag == '1' else 'points'}"


def _move(change: float) -> str:
    """_points for a PointChange, _change for a percent change."""
    return _points(change) if isinstance(change, PointChange) else _change(change)


def _fmt_value(v: float) -> str:
    """A data value for alt text."""
    mag = abs(v)
    if mag >= 10_000:
        return fmt_compact(v, digits=1)
    if float(v).is_integer() or mag >= 100:
        return f"{v:,.0f}"
    if mag >= 1:
        return f"{v:,.1f}"
    return f"{v:.2f}"


def _d3_format(values: list[float]) -> str:
    m = max((abs(v) for v in values), default=0.0)
    if m >= 100_000:
        return ",.3~s"
    if all(float(v).is_integer() for v in values) or m >= 100:
        return ",.0f"
    if m >= 1:
        return ",.1f"
    return ",.2f"


def _esc(text: str) -> str:
    """Make literal text safe to pass as compute_claim's text_template."""
    return text.replace("{", "{{").replace("}", "}}")


def _clean(v: Any) -> Any:
    """Round floats so data.json stays short and free of long digit runs
    (which the vetter's PII scan could mistake for phone numbers)."""
    if isinstance(v, float):
        r = round(v, 6)
        return int(r) if r.is_integer() and abs(r) < 1e15 else r
    if hasattr(v, "item"):
        return _clean(v.item())
    return v


def _pct(after: float, before: float) -> Optional[PctChange]:
    """compute_pct_change, rounded, or None when it would mislead: a base at
    or below zero, or an end below zero (a change across zero, where "fell
    200%" means nothing to a reader)."""
    if before is None or after is None or before <= 0 or after < 0:
        return None
    return PctChange(round(compute_pct_change(after, before), 4))


def _delta(after: float, before: float, share_scale: Optional[float]):
    """The change used in prose: percentage points for shares (always
    defined), else a percent change (None when it would mislead)."""
    if share_scale:
        return PointChange(round(compute_point_change(after, before, scale=share_scale), 4))
    return _pct(after, before)


def _drift(v0: float, v1: float) -> str:
    return "rose" if v1 > v0 else "fell" if v1 < v0 else "held level"


# ---------- the drafter ----------

class _Drafter:
    def __init__(self, pd, df, *, title, theme, audience, mode, max_scenes, source,
                 opener=True):
        self.opener = opener
        self.pd = pd
        self.raw = df
        self.title = title
        self.theme = theme
        self.audience = audience
        self.mode = mode
        self.max_scenes = max_scenes
        self.source = source.strip().rstrip(".") if source else None
        self.reasons: list[str] = []
        self.claims: list[dict[str, Any]] = []
        self.scene_list: list[dict[str, Any]] = []
        self.datasets: dict[str, list[dict[str, Any]]] = {}
        self.js: dict[str, str] = {}
        self.featured: set[str] = set()   # labels already headlined by a scene
        self.series_melt = False          # wide-by-series table melted to long
        self.cleaning: list[str] = []     # what _coerce_numeric_text changed
        self.daily = False                # time labels are calendar days

    # ----- profiling -----

    def _profile_column(self, s) -> ColumnProfile:
        pd = self.pd
        name = str(s.name)
        nonnull = s.dropna()
        card = int(nonnull.nunique())
        tokens = set(re.split(r"[^a-z0-9]+", name.lower())) - {""}
        n = len(s)

        if card <= 1:
            return ColumnProfile(name, "constant", card)
        if pd.api.types.is_datetime64_any_dtype(s):
            return ColumnProfile(name, "temporal", card, "datetime")
        if pd.api.types.is_bool_dtype(s):
            return ColumnProfile(name, "categorical", card)
        if pd.api.types.is_numeric_dtype(s):
            integral = bool((nonnull == nonnull.round()).all())
            if integral and tokens & _TIME_TOKENS and nonnull.between(1000, 2200).all():
                return ColumnProfile(name, "temporal", card, "year")
            if integral and card >= 3 and nonnull.between(1800, 2100).all() \
                    and not tokens & _ID_TOKENS:
                # No time-like name, but the values are evenly spaced years
                # (2015, 2016, ... or 2000, 2005, ...): a measure almost never is.
                gaps = set(pd.Series(sorted(nonnull.unique())).diff().dropna().astype(int))
                if len(gaps) == 1 and next(iter(gaps)) <= 10:
                    return ColumnProfile(name, "temporal", card, "year (from values)")
            if tokens & _ID_TOKENS:
                return ColumnProfile(name, "id", card)
            if integral and card == n and n > 12:
                ordered = sorted(nonnull.astype("int64").tolist())
                if ordered == list(range(ordered[0], ordered[0] + n)):
                    return ColumnProfile(name, "id", card, "row counter")
            return ColumnProfile(name, "measure", card)
        # strings / objects / categories
        as_str = nonnull.astype(str)
        if as_str.str.match(_YEAR_STR).all() and as_str.astype(int).between(1000, 2200).all():
            return ColumnProfile(name, "temporal", card, "year")
        if as_str.str.match(_DATE_STR).all():
            try:
                pd.to_datetime(as_str)
                return ColumnProfile(name, "temporal", card, "datetime")
            except (ValueError, TypeError):
                pass
        if as_str.str.strip().str.match(_QUARTER_STR).all():
            return ColumnProfile(name, "temporal", card, "quarter")
        if as_str.str.strip().str.match(_MONTH_STR).all():
            try:
                pd.to_datetime(as_str.str.strip(), format="mixed")
                return ColumnProfile(name, "temporal", card, "month")
            except (ValueError, TypeError):
                pass
        if tokens & _ID_TOKENS or (card == n and n > 50):
            return ColumnProfile(name, "id", card)
        return ColumnProfile(name, "categorical", card)

    def _profile(self, df) -> list[ColumnProfile]:
        return [self._profile_column(df[c]) for c in df.columns]

    def _normalize(self):
        """Profile, and melt wide tables to long via prep.to_long()."""
        pd = self.pd
        df = self.raw.copy()
        df.columns = [str(c) for c in df.columns]
        df = self._coerce_numeric_text(df)
        prof = self._profile(df)
        by_role = lambda role: [p.name for p in prof if p.role == role]  # noqa: E731
        measures, cats, times = by_role("measure"), by_role("categorical"), by_role("temporal")
        shape = f"{len(df)} rows x {len(df.columns)} columns"

        # Wide by period: one column per year ("label", "2019", "2024").
        year_cols = [m for m in measures if _YEAR_STR.match(m) and 1000 <= int(m) <= 2200]
        if len(year_cols) >= 2 and not times:
            ids = [c for c in df.columns if c not in year_cols and c in cats + by_role("id")]
            var = "year" if "year" not in df.columns else "period"
            long = pd.DataFrame.from_records(
                to_long(df, id_vars=ids, value_vars=year_cols, var_name=var, value_name="value"))
            return long, self._profile(long), (
                f"{shape}, wide by period (one column per year: {', '.join(year_cols)}); "
                f"melted to long with to_long() -> {var}, value")

        # Wide by series: one time column, several comparable measures, no category.
        if len(times) == 1 and not cats and len(measures) >= 2:
            medians = [float(df[m].abs().median()) for m in measures]
            lo, hi = min(medians), max(medians)
            if lo > 0 and hi / lo <= 1000:
                # Separate columns are separate series (Signups, Churn): never
                # sum them, follow the largest instead.
                self.series_melt = True
                long = pd.DataFrame.from_records(
                    to_long(df, id_vars=times, value_vars=measures,
                            var_name="series", value_name="value"))
                return long, self._profile(long), (
                    f"{shape}, wide by series (one column per series: {', '.join(measures)}); "
                    "melted to long with to_long() -> series, value")
            shape += " (several measures on different scales; using the first)"
        return df, prof, f"{shape}, long format"

    def _coerce_numeric_text(self, df):
        """Text columns that are really numbers ("$1,200", "12%", one typo in
        a spreadsheet export) become numeric. Unparseable cells are dropped
        and reported in explain(), never silently guessed."""
        pd = self.pd
        for c in df.columns:
            s = df[c]
            if not (pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)):
                continue
            text = s.dropna().astype(str).str.strip()
            text = text[text != ""]
            if len(text) < 2 or text.str.match(_YEAR_STR).all() \
                    or text.str.match(_DATE_STR).all() or text.str.match(_QUARTER_STR).all():
                continue
            neg = text.str.match(r"^\(.*\)$")            # accounting negatives: (5)
            cleaned = text.str.replace(r"^\((.*)\)$", r"\1", regex=True).str.replace(
                _NUM_JUNK, "", regex=True)
            nums = pd.to_numeric(cleaned, errors="coerce")
            nums[neg] = -nums[neg]
            ok = nums.notna()
            # One stray typo is tolerated even in a short column.
            if ok.sum() < 2 or (ok.mean() < NUMERIC_COERCE_MIN and (~ok).sum() > 1):
                continue
            bad = text[~ok]
            blanks = int(s.isna().sum() + (s.dropna().astype(str).str.strip() == "").sum())
            df[c] = nums.reindex(s.index)
            parts = []
            if len(bad):
                shown = ", ".join(repr(v) for v in bad.head(3))
                more = f" and {len(bad) - 3} more" if len(bad) > 3 else ""
                parts.append(f"{len(bad)} non-numeric value{'s' if len(bad) > 1 else ''} "
                             f"dropped ({shown}{more})")
            if blanks:
                parts.append(f"{blanks} blank{'s' if blanks > 1 else ''} skipped")
            note = f"read as numbers; {'; '.join(parts)}" if parts else "read as numbers"
            self.cleaning.append(f"(cleaned) {c}: {note}")
        return df

    # ----- time helpers -----

    def _time_keys(self, s, detail):
        """(keys, iso(key), label(key)) for a temporal column."""
        pd = self.pd
        if detail.startswith("year"):
            keys = s.astype(str).str.replace(r"\.0$", "", regex=True).astype(int)
            return keys, (lambda k: f"{int(k):04d}-01-01"), (lambda k: str(int(k)))
        if detail == "quarter":
            def qstart(v):
                m = _QUARTER_STR.match(str(v).strip())
                y, q = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
                return pd.Timestamp(int(y), 3 * (int(q) - 1) + 1, 1)
            keys = s.map(qstart)
            return (keys, (lambda k: k.strftime("%Y-%m-%d")),
                    (lambda k: f"Q{(k.month - 1) // 3 + 1} {k.year}"))
        keys = (pd.to_datetime(s.astype(str).str.strip(), format="mixed") if detail == "month"
                else pd.to_datetime(s))
        if getattr(keys.dt, "tz", None) is not None:
            keys = keys.dt.tz_localize(None)
        jan1 = bool(((keys.dt.month == 1) & (keys.dt.day == 1)).all())
        first = bool((keys.dt.day == 1).all())
        if jan1:
            label = lambda k: str(k.year)  # noqa: E731
        elif first:
            label = lambda k: k.strftime("%b %Y")  # noqa: E731
        else:
            self.daily = True
            label = lambda k: f"{k.strftime('%b')} {k.day}, {k.year}"  # noqa: E731
        return keys, (lambda k: k.strftime("%Y-%m-%d")), label

    def _at(self, label: str) -> str:
        """'in 2024', 'in Mar 2024', 'on Mar 2, 2024'."""
        return f"{'on' if self.daily else 'in'} {label}"

    # ----- claims -----

    def _claim(self, cid: str, text: str, value: float, scene: str, *,
               kind: str = "auto") -> str:
        c = compute_claim(id=cid, text_template=_esc(_sentence_case(text)), value=value,
                          scene=scene, kind=kind)
        self.claims.append(c)
        return c["text"]

    def _share_claim(self, cid: str, text: str, share: float, scene: str) -> str:
        # A share is not a change, so it carries no "ratio"/"pct" unit: the
        # vetter reads a unit-less 0..1 value as a share and checks "N%" against
        # value x 100. (compute_claim would warn on the untagged float.)
        text = _sentence_case(text)
        c = {"id": cid, "text": text, "value": round(float(share), 6), "scene": scene}
        self.claims.append(c)
        return text

    # ----- scene builders -----

    def _source_line(self) -> str:
        return f"Source: {self.source}." if self.source else ""

    def _add_scene(self, recipe: str, scene: dict[str, Any], rows: list[dict[str, Any]]) -> None:
        sid = scene["id"]
        key = sid.removeprefix("scene-")
        scene = {"kind": "simple", "dataset": key, "source_line": self._source_line(), **scene}
        scene = {k: v for k, v in scene.items() if v not in (None, "")}
        self.scene_list.append(scene)
        self.datasets[key] = [{k: _clean(v) for k, v in r.items()} for r in rows]
        self.js[sid] = recipe_js(recipe, sid)

    def _line_scene(self, T, M, series, iso, label, subject: str, why: str, *,
                    proper: bool = False, share_scale: Optional[float] = None) -> bool:
        """series: list of (key, value), sorted by key. `proper` means the
        subject starts with a data label, so it keeps its case mid-sentence.
        `share_scale` (1 or 100) marks the measure as a share, compared in
        percentage points."""
        sid = "scene-trend"
        in_text = subject if proper else subject[:1].lower() + subject[1:]
        pts = [(k, float(v)) for k, v in series if v == v]
        if len(pts) < 3:
            return False
        (k0, v0), (k1, v1) = pts[0], pts[-1]
        t0, t1 = label(k0), label(k1)
        values = [v for _, v in pts]
        headline, commentary, ipk, peak_drop = self._trend_text(pts, label, subject,
                                                               share_scale, sid)

        alt = (f"Line chart of {in_text} from {t0} to {t1}: "
               f"it goes from {_fmt_value(v0)} to {_fmt_value(v1)}")
        annotation = None
        if peak_drop:
            alt += f", peaking at {_fmt_value(values[ipk])} in {label(pts[ipk][0])}"
            annotation = {"x": iso(pts[ipk][0]), "y": _clean(values[ipk]),
                          "text": f"Peak: {_fmt_value(values[ipk])}"}
        self._add_scene("line-reveal", {
            "id": sid, "headline": headline, "commentary": commentary, "alt": alt + ".",
            "config": {"x": T, "y": M, "parse": "%Y-%m-%d", "format": _d3_format(values)},
            "annotation": annotation,
        }, [{T: iso(k), M: v} for k, v in pts])
        self.reasons.append(f"scene-trend: line-reveal over {T} x {M} -- {why}")
        return True

    def _trend_text(self, pts, label, subject: str, share_scale, sid: str):
        """Headline + commentary for a series of (key, value) points, with
        their claims registered against scene `sid`. Returns (headline,
        commentary, index of the peak, whether a drop from the peak is told)."""
        (k0, v0), (k1, v1) = pts[0], pts[-1]
        t0, t1 = label(k0), label(k1)
        values = [v for _, v in pts]
        change = _delta(v1, v0, share_scale)
        crossed = None   # the last period where the series crossed zero
        for i in range(1, len(values)):
            if (values[i - 1] >= 0 > values[i]) or (values[i - 1] <= 0 < values[i]):
                crossed = i
        if change is not None:
            headline = self._claim("c-trend", f"{subject} {_move(change)} between {t0} and {t1}",
                                   change, sid)
        elif crossed is not None and (v0 < 0) != (v1 < 0):
            sign = "negative" if v1 < 0 else "positive"
            headline = _sentence_case(f"{subject} turned {sign} {self._at(label(pts[crossed][0]))}")
        else:
            headline = _sentence_case(f"{subject} {_drift(v0, v1)} between {t0} and {t1}")

        ipk = max(range(len(values)), key=values.__getitem__)
        commentary = ""
        from_peak = _delta(v1, values[ipk], share_scale) if 0 < ipk < len(values) - 1 else None
        peak_drop = from_peak is not None and (
            from_peak <= -1 if share_scale else from_peak <= -3)
        if peak_drop:
            commentary = self._claim(
                "c-trend-peak",
                f"It peaked {self._at(label(pts[ipk][0]))}, then {_move(from_peak)} by {t1}.",
                from_peak, sid)
        else:
            steps = [(i, _delta(values[i], values[i - 1], share_scale))
                     for i in range(1, len(values))]
            # "Sharpest" only holds when every step could be measured.
            # ...and only when something actually moved.
            if all(p is not None for _, p in steps) and any(abs(p) >= 0.05 for _, p in steps):
                i, p = max(steps, key=lambda ip: abs(ip[1]))
                commentary = self._claim(
                    "c-trend-step",
                    f"The sharpest move came {self._at(label(pts[i][0]))}, when it {_move(p)} "
                    f"from {label(pts[i - 1][0])}.", p, sid)
        return headline, commentary, ipk, peak_drop

    def _opener_scene(self, T, C, M, wide, periods, label, why: str) -> bool:
        """An animated Vizzu opener: the total as stacked bars, which then
        morph into one line per category. Additive measures only (the stack
        must mean something). wide: index period, columns category."""
        sid = "scene-opener"
        gaps = [(str(c), label(p)) for c in wide.columns for p in periods
                if wide[c].isna().get(p, True)]
        if gaps:
            # A stacked "total" missing one category in one period undercounts
            # it; don't animate a number that isn't the total.
            c, t = gaps[0]
            self.reasons.append(f"(skipped) vizzu opener: {c} has no {M} in {t}"
                                + (f" (and {len(gaps) - 1} more gaps)" if len(gaps) > 1 else "")
                                + "; a stacked total would undercount.")
            return False
        full = wide
        ncat, nper = full.shape[1], len(periods)
        if not (2 <= ncat <= MAX_OPENER_CATEGORIES and 3 <= nper <= MAX_OPENER_PERIODS):
            self.reasons.append(
                f"(skipped) vizzu opener: needs 2-{MAX_OPENER_CATEGORIES} {C} values in every "
                f"{T} and 3-{MAX_OPENER_PERIODS} periods (found {ncat} and {nper}).")
            return False
        if bool((full < 0).any().any()):
            self.reasons.append("(skipped) vizzu opener: negative values can't stack.")
            return False
        totals = full.sum(axis=1)
        pts = [(k, float(totals.loc[k])) for k in periods]
        t0, t1 = label(periods[0]), label(periods[-1])
        subject = f"Total {_humanize(M)}"
        h1, c1, _, _ = self._trend_text(pts, label, subject, None, sid)
        last = full.loc[periods[-1]].sort_values(ascending=False)
        total1 = float(last.sum())
        frame2 = {"headline": "", "commentary": ""}
        if total1 > 0:
            (lead, vl), (second, vs) = (str(last.index[0]), float(last.iloc[0])), \
                                       (str(last.index[1]), float(last.iloc[1]))
            frame2["headline"] = self._share_claim(
                "c-opener-lead", f"In {t1}, {lead} made up {_pct_str(vl / total1 * 100)}% "
                                 f"of the total", vl / total1, sid)
            frame2["commentary"] = self._share_claim(
                "c-opener-next", f"{second} was next, at {_pct_str(vs / total1 * 100)}%.",
                vs / total1, sid)
            self.featured.add(lead)
        else:
            frame2["headline"] = _sentence_case(f"Each {_humanize(C)} on its own")
        stacked = {"channels": {"x": T, "y": [C, M], "color": C, "label": None},
                   "geometry": "rectangle"}
        split = {"channels": {"x": T, "y": M, "color": C, "label": None}, "geometry": "line"}
        rows = [{T: label(p), C: str(c), M: _clean(full.loc[p, c])}
                for p in periods for c in full.columns]
        cname = _humanize(C)
        alt = (f"Animated chart of {subject.lower()} by {T}, {t0} to {t1}, as bars stacked by "
               f"{cname} (from {_fmt_value(pts[0][1])} to {_fmt_value(pts[-1][1])}), which then "
               f"split into one line per {cname}"
               + (f"; in {t1} {lead} is the largest part" if total1 > 0 else "") + ".")
        scene = {
            "id": sid, "kind": "vizzu", "dataset": sid.removeprefix("scene-"),
            "source_line": self._source_line(), "alt": alt,
            "series": [{"name": T, "type": "dimension"}, {"name": C, "type": "dimension"},
                       {"name": M, "type": "measure"}],
            "frames": [{"headline": h1, "commentary": c1, "config": stacked},
                       {**frame2, "config": split}],
        }
        scene = {k: v for k, v in scene.items() if v not in (None, "")}
        scene["frames"] = [{k: v for k, v in f.items() if v not in (None, "")}
                           for f in scene["frames"]]
        self.scene_list.append(scene)
        self.datasets[scene["dataset"]] = rows
        self.reasons.append(f"scene-opener: vizzu opener, {M} stacked by {C} per {T}, then one "
                            f"line per {C} -- {why}")
        return True

    def _slope_scene(self, C, M, wide, periods, label, share_scale: Optional[float]) -> bool:
        sid = "scene-shift"
        p0, p1 = periods[0], periods[-1]
        t0, t1 = label(p0), label(p1)
        both = wide[[p0, p1]].dropna()
        if len(both) < 2:
            self.reasons.append(f"(skipped) slope-chart: fewer than 2 {C} values in both "
                                f"{t0} and {t1}.")
            return False
        trimmed = ""
        if len(both) > MAX_SLOPE_CATEGORIES:
            both = both.sort_values(p1, ascending=False).head(MAX_SLOPE_CATEGORIES)
            trimmed = f"; kept the {MAX_SLOPE_CATEGORIES} largest in {t1}"
        rows = [(str(lab), float(r[p0]), float(r[p1])) for lab, r in both.iterrows()]
        measured = [(lab, _delta(e, s, share_scale)) for lab, s, e in rows]
        movers = [(lab, p) for lab, p in measured if p is not None]
        # Superlatives ("biggest", "least") only hold when every category was measured.
        complete = len(movers) == len(rows)
        crossers = [(lab, "negative" if e < 0 else "positive") for lab, s, e in rows
                    if (s >= 0 > e) or (s <= 0 < e)]
        cname = _humanize(C)

        def subj(lab: str) -> str:
            return f"{lab} share" if share_scale else lab

        headline, commentary, highlight = "", "", []
        if movers:
            top, tp = max(movers, key=lambda lp: abs(lp[1]))
            if top in self.featured and complete:
                # The trend scene already stated this change; add the comparison only.
                headline = _sentence_case(f"No {cname} moved more than {top} "
                                          f"between {t0} and {t1}")
            else:
                biggest = f", the biggest shift of any {cname}" if complete else ""
                headline = self._claim(
                    "c-shift", f"{subj(top)} {_move(tp)} between {t0} and {t1}{biggest}", tp, sid)
            highlight.append(top)
            rest = [(lab, p) for lab, p in movers if lab != top]
            opposite = [(lab, p) for lab, p in rest if (p > 0) != (tp > 0) and abs(p) >= 0.05]
            # Don't restate the line scene's subject when another label can make the point.
            fresh = [(lab, p) for lab, p in opposite if lab not in self.featured]
            opposite = fresh or opposite
            if crossers:
                lab, sign = crossers[0]
                commentary = _sentence_case(f"{lab} turned {sign} by {t1}.")
                highlight.append(lab)
            elif opposite:
                lab, p = max(opposite, key=lambda lp: abs(lp[1]))
                commentary = self._claim("c-shift-contrast",
                                         f"{subj(lab)}, by contrast, {_move(p)}.", p, sid)
                highlight.append(lab)
            elif rest and complete:
                lab, p = min(rest, key=lambda lp: abs(lp[1]))
                commentary = self._claim("c-shift-least",
                                         f"{subj(lab)} changed least: it {_move(p)}.", p, sid)
                highlight.append(lab)
        elif crossers:
            lab, sign = crossers[0]
            headline = _sentence_case(f"{lab} turned {sign} between {t0} and {t1}")
            highlight.append(lab)
        else:
            headline = f"Where each {cname} stood in {t0} and {t1}"
        by_label = {lab: (s, e) for lab, s, e in rows}
        focus = highlight or [rows[0][0]]
        alt = (f"Slope chart of {_humanize(M)} by {cname}, {t0} versus {t1}: " + "; ".join(
            f"{lab} goes from {_fmt_value(by_label[lab][0])} to {_fmt_value(by_label[lab][1])}"
            for lab in focus) + ".")
        values = [v for _, s, e in rows for v in (s, e)]
        self._add_scene("slope-chart", {
            "id": sid, "headline": headline, "commentary": commentary, "alt": alt,
            "config": {"label": C, "start": "start", "end": "end", "start_label": t0,
                       "end_label": t1, "highlight": highlight, "format": _d3_format(values)},
        }, [{C: lab, "start": s, "end": e} for lab, s, e in rows])
        self.reasons.append(
            f"scene-shift: slope-chart of {C}, {t0} vs {t1} -- category x first/last period "
            f"({len(rows)} {C} values present in both{trimmed})")
        return True

    def _bump_scene(self, T, C, M, wide, periods, label) -> bool:
        """Bump chart when the top-ranked category changed between the first
        and last period. wide: index period, columns category."""
        sid = "scene-race"
        if not 3 <= len(periods) <= MAX_BUMP_PERIODS:
            self.reasons.append(f"(skipped) bump-chart: needs 3 to {MAX_BUMP_PERIODS} "
                                f"{T} periods, found {len(periods)}.")
            return False
        full = wide.dropna(axis=1)   # categories present in every period
        if full.shape[1] < 3:
            self.reasons.append(f"(skipped) bump-chart: fewer than 3 {C} values present in "
                                f"every {T}.")
            return False
        if full.shape[1] > MAX_BUMP_CATEGORIES:
            keep = full.loc[periods[-1]].sort_values(ascending=False).index[:MAX_BUMP_CATEGORIES]
            full = full[keep]
        first, last = full.loc[periods[0]], full.loc[periods[-1]]
        old, new = str(first.idxmax()), str(last.idxmax())
        # A tie at the top is not an overtake.
        if old == new or (first == first.max()).sum() > 1 or (last == last.max()).sum() > 1:
            self.reasons.append(f"(skipped) bump-chart: the top {C} did not change "
                                f"({new} leads in both {label(periods[0])} and "
                                f"{label(periods[-1])}).")
            return False
        t0, t1 = label(periods[0]), label(periods[-1])
        rank0 = {str(k): i + 1 for i, k in enumerate(first.sort_values(ascending=False).index)}
        rank1 = {str(k): i + 1 for i, k in enumerate(last.sort_values(ascending=False).index)}
        took = next(label(p) for p in periods if str(full.loc[p].idxmax()) == new
                    and all(str(full.loc[q].idxmax()) == new for q in periods[periods.index(p):]))
        headline = _sentence_case(f"{new} overtook {old} to rank first by {t1}")
        commentary = _sentence_case(
            f"{old} led {self._at(t0)}; {new} has held the top spot since {took}."
            if took != t1 else f"{old} led {self._at(t0)}; {new} took the top spot {self._at(t1)}.")
        alt = (f"Bump chart ranking each {_humanize(C)} by {_humanize(M)} from {t0} to {t1}: "
               f"{new} climbs from rank {rank0[new]} to rank 1, and {old} slips from rank 1 "
               f"to rank {rank1[old]}.")
        rows = [{T: label(p), C: str(c), M: full.loc[p, c]} for p in periods for c in full.columns]
        self._add_scene("bump-chart", {
            "id": sid, "headline": headline, "commentary": commentary, "alt": alt,
            "config": {"x": T, "series": C, "y": M, "highlight": [new]},
        }, rows)
        self.reasons.append(f"scene-race: bump-chart of {C} rank by {M} -- the top {C} changed "
                            f"({old} in {t0}, {new} in {t1})")
        return True

    def _waffle_scene(self, C, M, values: list[tuple[str, float]], period: Optional[str],
                      why: str) -> bool:
        sid = "scene-mix"
        vals = [(lab, v) for lab, v in values if v > 0]
        if len(vals) < 2:
            return False
        if len(vals) > MAX_WAFFLE_CATEGORIES:
            self.reasons.append(f"(skipped) waffle: {len(vals)} {C} values; the waffle reads "
                                f"well with at most {MAX_WAFFLE_CATEGORIES}.")
            return False
        vals.sort(key=lambda lv: -lv[1])
        total = sum(v for _, v in vals)
        shares = [(lab, v / total) for lab, v in vals]
        (lead, s1), (second, s2) = shares[0], shares[1]
        when = f"In {period}, " if period else ""
        headline = self._share_claim(
            "c-mix-lead", f"{when}{lead} holds the largest share: {_pct_str(s1 * 100)}%",
            s1, sid)
        commentary = self._share_claim("c-mix-next",
                                       f"{second} is next, at {_pct_str(s2 * 100)}%.", s2, sid)
        alt = (f"Waffle chart of {_humanize(M)} by {_humanize(C)}"
               + (f" in {period}" if period else "") + ": "
               + ", ".join(f"{lab} {_pct_str(s * 100)}%" for lab, s in shares) + ".")
        self._add_scene("waffle", {
            "id": sid, "headline": headline, "commentary": commentary, "alt": alt,
            "config": {"label": C, "value": M},
        }, [{C: lab, M: v} for lab, v in vals])
        self.reasons.append(f"scene-mix: waffle of {C} by {M}" +
                            (f" in {period}" if period else "") + f" -- {why}")
        return True

    def _bar_scene(self, L, M, rows: list[tuple[str, float]], why: str) -> None:
        sid = "scene-rank"
        rows = sorted(rows, key=lambda lv: -lv[1])[:MAX_BAR_ROWS]
        (top, vt), (bottom, vb) = rows[0], rows[-1]
        mname = _humanize(M)
        p = _pct(vt, vb)
        lead_note = (self._claim("c-rank", f"{top} is {_pct_str(p)}% higher than {bottom}.",
                                 p, sid) if p is not None and len(rows) > 1 else
                     f"{top} has the highest {mname}.")
        steps = [{"headline": _sentence_case(f"{top} ranks first"), "commentary": lead_note, "state": top}]
        if len(rows) > 1:
            steps.append({"headline": _sentence_case(f"{bottom} ranks last"),
                          "commentary": _sentence_case(f"{bottom} has the lowest {mname}."), "state": bottom})
        alt = (f"Bar chart of {mname} by {_humanize(L)}: {top} is highest at {_fmt_value(vt)}"
               + (f", {bottom} lowest at {_fmt_value(vb)}" if len(rows) > 1 else "") + ".")
        self._add_scene("bar-steps", {
            "id": sid, "kind": "scrolly", "headline": _sentence_case(f"{top} leads on {mname}"),
            "alt": alt, "steps": steps,
            "config": {"label": L, "y": M, "format": _d3_format([v for _, v in rows])},
        }, [{L: lab, M: v} for lab, v in rows])
        self.reasons.append(f"scene-rank: bar-steps of {M} by {L} -- {why}")

    # ----- rules -----

    def _plan(self, df, prof) -> None:
        pd = self.pd
        role = {p.name: p for p in prof}
        times = [p for p in prof if p.role == "temporal"]
        measures = [p.name for p in prof if p.role == "measure"]
        cats = [p for p in prof if p.role == "categorical"]
        if not measures:
            raise ValueError("draft() found no numeric measure column to chart. "
                             f"Columns: {', '.join(p.describe() for p in prof)}")
        M = "value" if "value" in measures else measures[0]
        if len(measures) > 1:
            self.reasons.append(f"(note) using measure {M!r}; also numeric: "
                                f"{', '.join(m for m in measures if m != M)}")
        # Prefer a category with a chartable number of levels.
        cats.sort(key=lambda p: (not 2 <= p.cardinality <= 12, p.cardinality))
        C = cats[0].name if cats else None
        T = times[0] if times else None

        tokens = set(re.split(r"[^a-z0-9]+", M.lower()))
        additive = not (tokens & _NON_ADDITIVE_TOKENS) and not self.series_melt
        work = df.dropna(subset=[M]).copy()
        work[M] = pd.to_numeric(work[M], errors="coerce")
        work = work.dropna(subset=[M])
        agg = "sum" if additive else "mean"
        if T is not None or C is not None:
            role[M].detail = f"{'summed' if additive else 'averaged'} when rows repeat"
        planned = 0

        def room() -> bool:
            return planned < self.max_scenes

        if T is not None:
            keys, iso, label = self._time_keys(work[T.name], T.detail)
            work["__t"] = keys
            periods = sorted(work["__t"].unique())
            if C is not None:
                grouped = work.groupby(["__t", C])[M].agg(agg)
                wide = grouped.unstack(C)          # index: period, columns: category
                sums = grouped.groupby(level=0).sum()
                nonneg = bool((work[M] >= 0).all())
                share_scale = (1.0 if nonneg and bool(sums.between(97, 103).all()) else
                               100.0 if nonneg and bool(sums.between(0.97, 1.03).all()) else None)
                shares = share_scale is not None
                last_vals = wide.loc[periods[-1]].dropna()
                # 1. time x measure
                if room():
                    ok = False
                    if additive and not shares and self.opener:
                        ok = self._opener_scene(
                            T.name, C, M, wide, periods, label,
                            f"time series detected; {M} is additive, so the total stacks by {C}")
                    if ok:
                        pass
                    elif additive and not shares:
                        total = work.groupby("__t")[M].sum()
                        ok = self._line_scene(
                            T.name, M, list(total.items()), iso, label, f"Total {_humanize(M)}",
                            f"time series detected; {M} summed across {C} per {T.name}")
                    else:
                        leader = str(last_vals.idxmax())
                        self.featured.add(leader)
                        subject = (f"{leader} share" if shares else leader if self.series_melt
                                   else f"{leader} {_humanize(M)}")
                        kind = ("a share, compared in percentage points" if shares else
                                "one column per series (not summed)" if self.series_melt else
                                "not additive")
                        ok = self._line_scene(
                            T.name, M, list(wide[last_vals.idxmax()].items()), iso, label,
                            subject, f"time series detected; {M} is {kind}, so it follows the "
                            f"largest {C} in {label(periods[-1])} ({leader})", proper=True,
                            share_scale=share_scale)
                    planned += ok
                    if not ok:
                        self.reasons.append(f"(skipped) line-reveal: fewer than 3 {T.name} "
                                            "periods.")
                # 2. category x first/last period
                if room() and len(periods) >= 2:
                    planned += self._slope_scene(C, M, wide.T, periods, label, share_scale)
                # 3. a change at the top of the ranking
                if room() and not self.series_melt:
                    planned += self._bump_scene(T.name, C, M, wide, periods, label)
                # 4. shares
                if shares and room():
                    planned += self._waffle_scene(
                        C, M, [(str(k), float(v)) for k, v in last_vals.items()],
                        label(periods[-1]),
                        f"{M} sums to ~{'100' if sums.iloc[-1] > 2 else '1'} per {T.name}")
                elif not shares:
                    self.reasons.append(f"(skipped) waffle: {M} is not a share (per-{T.name} "
                                        "totals are not ~100 or ~1).")
            else:
                series = work.groupby("__t")[M].agg(agg)
                if room():
                    ok = self._line_scene(T.name, M, list(series.items()), iso, label,
                                          _sentence_case(_humanize(M)), "time series detected")
                    planned += ok
                    if not ok:
                        self.reasons.append(f"(skipped) line-reveal: fewer than 3 {T.name} "
                                            "periods.")
                self.reasons.append("(skipped) slope-chart, waffle: no category column.")
        elif C is not None:
            vals = work.groupby(C)[M].agg(agg)
            total = float(vals.sum())
            if bool((vals >= 0).all()) and (97 <= total <= 103 or 0.97 <= total <= 1.03):
                planned += self._waffle_scene(
                    C, M, [(str(k), float(v)) for k, v in vals.items()], None,
                    f"{M} sums to ~{'100' if total > 2 else '1'} across {C}")
            else:
                self.reasons.append(f"(skipped) waffle: {M} across {C} sums to "
                                    f"{_fmt_value(total)}, not ~100 or ~1.")
            if not times:
                self.reasons.append("(skipped) line-reveal, slope-chart: no time column.")

        if planned == 0:
            self._fallback(work, prof, M, C, T, agg)

    def _fallback(self, work, prof, M, C, T, agg) -> None:
        if C is not None:
            vals = work.groupby(C)[M].agg(agg)
            rows, L = [(str(k), float(v)) for k, v in vals.items()], C
        else:
            ids = [p.name for p in prof if p.role in ("id", "categorical")]
            if T is not None:
                L = T.name
                keys, _, label = self._time_keys(work[T.name], T.detail)
                rows = [(label(k), float(v)) for k, v in zip(keys, work[M])]
            elif ids:
                L = ids[0]
                rows = [(str(k), float(v)) for k, v in zip(work[L], work[M])]
            else:
                L = "row"
                rows = [(f"#{i + 1}", float(v)) for i, v in enumerate(work[M])]
        if not rows:
            raise ValueError(f"draft() found no numeric values in {M!r}.")
        self._bar_scene(L, M, rows, "no rule matched; one safe bar chart of the measure")

    # ----- assemble -----

    def run(self) -> Draft:
        df, prof, shape = self._normalize()
        self._plan(df, prof)
        self.reasons = self.cleaning + self.reasons
        meta: dict[str, Any] = {
            "title": self.title, "theme": self.theme or "editorial-noir",
            "audience": self.audience, "mode": self.mode,
            "published": date.today().isoformat(),
        }
        if self.source:
            meta["sources"] = [{"name": self.source}]
        used = {s["dataset"] for s in self.scene_list}
        story = {
            "meta": meta,
            "claims": self.claims,
            "scenes": self.scene_list,
            "datasets": {k: v for k, v in self.datasets.items() if k in used},
        }
        story = self._self_vet(story)
        Story.model_validate(story)
        numbered = []
        n = 0
        for r in self.reasons:
            if r.startswith("scene-"):
                n += 1
                numbered.append(f"{n}. {r}")
            else:
                numbered.append(r)
        return Draft(story=story, scenes={k: v for k, v in self.js.items()
                                          if k in {s['id'] for s in story['scenes']}},
                     reasons=numbered, profile=prof, shape=shape)

    def _self_vet(self, story: dict[str, Any]) -> dict[str, Any]:
        """Run the static fidelity check per claim; drop any scene whose claim
        fails (a drafting bug, but never ship it). Also enforce max_scenes."""
        from .vet import check_data_fidelity

        bad_scenes = set()
        for c in story["claims"]:
            if not check_data_fidelity("", {"claims": [c]}).passed:
                bad_scenes.add(c.get("scene"))
        scenes = [s for s in story["scenes"] if s["id"] not in bad_scenes]
        for sid in sorted(s for s in bad_scenes if s):
            self.reasons.append(f"(dropped) {sid}: a generated claim failed the static vet.")
        dropped_cap = scenes[self.max_scenes:]
        scenes = scenes[: self.max_scenes]
        for s in dropped_cap:
            self.reasons.append(f"(dropped) {s['id']}: over max_scenes={self.max_scenes}.")
        keep = {s["id"] for s in scenes}
        story["scenes"] = scenes
        story["claims"] = [c for c in story["claims"] if c.get("scene") in keep]
        story["datasets"] = {k: v for k, v in story["datasets"].items()
                             if k in {s["dataset"] for s in scenes}}
        return story
