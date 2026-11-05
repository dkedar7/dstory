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

Rules (milestone 1):
  * time x measure                 -> line-reveal
  * category x first/last period   -> slope-chart
  * shares summing to ~100 (or ~1) -> waffle
  * nothing matched                -> one bar-steps scene (always safe)

pandas is optional for dstory as a whole; this module imports it lazily and
raises an ImportError pointing at the [prep] extra when it is missing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .brand import list_presets
from .cookbook import recipe_js
from .prep import (
    compute_claim, compute_pct_change, fmt_compact, ratio_phrase, to_long, PctChange,
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
_DATE_STR = re.compile(r"^\d{4}-\d{2}(-\d{2})?([T ].*)?$")

MAX_SLOPE_CATEGORIES = 10
MAX_WAFFLE_CATEGORIES = 7     # the waffle palette has 7 categorical colors
MAX_BAR_ROWS = 12


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
        lines.append("Scenes:")
        lines += [f"  {r}" for r in self.reasons]
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
                    max_scenes=max_scenes, source=source).run()


def _is_dataframe(obj: Any) -> bool:
    t = type(obj)
    return t.__name__ == "DataFrame" and t.__module__.split(".")[0] == "pandas"


def _maybe_draft(story: Any, path: str | Path, *, brand: Any,
                 scenes: Optional[dict[str, str]]) -> tuple[Any, Optional[dict[str, str]]]:
    """build() hook: a DataFrame becomes draft().story + draft().scenes.

    Anything else is returned untouched, so dict / Story input is unchanged.
    Scenes passed explicitly to build() override the drafted ones.
    """
    if not _is_dataframe(story):
        return story, scenes
    theme = brand if isinstance(brand, str) and brand in list_presets() else None
    title = re.sub(r"[-_]+", " ", Path(path).name).strip() or "Untitled story"
    d = draft(story, title=_sentence_case(title), theme=theme)
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
    """A verb phrase for a percent change: 'doubled', 'rose 42%', 'fell 7.5%'."""
    word = ratio_phrase(1.0 + pct / 100.0)
    if word:
        return word
    if abs(pct) < 0.05:
        return "held steady, a 0% change"
    return f"{'rose' if pct > 0 else 'fell'} {_pct_str(pct)}%"


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
    """compute_pct_change, rounded, or None when the base can't carry one."""
    if before is None or after is None or before <= 0:
        return None
    return PctChange(round(compute_pct_change(after, before), 4))


# ---------- the drafter ----------

class _Drafter:
    def __init__(self, pd, df, *, title, theme, audience, mode, max_scenes, source):
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
                long = pd.DataFrame.from_records(
                    to_long(df, id_vars=times, value_vars=measures,
                            var_name="series", value_name="value"))
                return long, self._profile(long), (
                    f"{shape}, wide by series (one column per series: {', '.join(measures)}); "
                    "melted to long with to_long() -> series, value")
            shape += " (several measures on different scales; using the first)"
        return df, prof, f"{shape}, long format"

    # ----- time helpers -----

    def _time_keys(self, s, detail):
        """(keys, iso(key), label(key)) for a temporal column."""
        pd = self.pd
        if detail == "year":
            keys = s.astype(str).astype(int)
            return keys, (lambda k: f"{int(k):04d}-01-01"), (lambda k: str(int(k)))
        keys = pd.to_datetime(s)
        if getattr(keys.dt, "tz", None) is not None:
            keys = keys.dt.tz_localize(None)
        jan1 = bool(((keys.dt.month == 1) & (keys.dt.day == 1)).all())
        first = bool((keys.dt.day == 1).all())
        if jan1:
            label = lambda k: str(k.year)  # noqa: E731
        elif first:
            label = lambda k: k.strftime("%b %Y")  # noqa: E731
        else:
            label = lambda k: k.strftime("%Y-%m-%d")  # noqa: E731
        return keys, (lambda k: k.strftime("%Y-%m-%d")), label

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
                    proper: bool = False) -> bool:
        """series: list of (key, value), sorted by key. `proper` means the
        subject starts with a data label, so it keeps its case mid-sentence."""
        sid = "scene-trend"
        in_text = subject if proper else subject[:1].lower() + subject[1:]
        pts = [(k, float(v)) for k, v in series if v == v]
        if len(pts) < 3:
            return False
        (k0, v0), (k1, v1) = pts[0], pts[-1]
        t0, t1 = label(k0), label(k1)
        pct = _pct(v1, v0)
        if pct is not None:
            headline = self._claim("c-trend", f"{subject} {_change(pct)} between {t0} and {t1}",
                                   pct, sid)
        else:
            headline = f"How {in_text} has moved"

        values = [v for _, v in pts]
        ipk = max(range(len(values)), key=values.__getitem__)
        commentary = ""
        from_peak = _pct(v1, values[ipk]) if 0 < ipk < len(values) - 1 else None
        if from_peak is not None and from_peak <= -3:
            commentary = self._claim(
                "c-trend-peak",
                f"It peaked in {label(pts[ipk][0])}, then {_change(from_peak)} by {t1}.",
                from_peak, sid)
        else:
            steps = [(i, _pct(values[i], values[i - 1])) for i in range(1, len(values))]
            steps = [(i, p) for i, p in steps if p is not None]
            if steps:
                i, p = max(steps, key=lambda ip: abs(ip[1]))
                commentary = self._claim(
                    "c-trend-step",
                    f"The sharpest move came in {label(pts[i][0])}, when it {_change(p)} "
                    f"from {label(pts[i - 1][0])}.", p, sid)

        alt = (f"Line chart of {in_text} from {t0} to {t1}: "
               f"it goes from {_fmt_value(v0)} to {_fmt_value(v1)}")
        annotation = None
        if from_peak is not None and from_peak <= -3:
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

    def _slope_scene(self, C, M, wide, periods, label, shares: bool) -> bool:
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
        movers = [(lab, _pct(e, s)) for lab, s, e in rows]
        movers = [(lab, p) for lab, p in movers if p is not None]
        cname = _humanize(C)

        def subj(lab: str) -> str:
            return f"{lab} share" if shares else lab

        headline, commentary, highlight = "", "", []
        if movers:
            top, tp = max(movers, key=lambda lp: abs(lp[1]))
            headline = self._claim(
                "c-shift", f"{subj(top)} {_change(tp)} between {t0} and {t1}, "
                           f"the biggest shift of any {cname}", tp, sid)
            highlight.append(top)
            rest = [(lab, p) for lab, p in movers if lab != top]
            opposite = [(lab, p) for lab, p in rest if (p > 0) != (tp > 0) and abs(p) >= 0.05]
            # Don't restate the line scene's subject when another label can make the point.
            fresh = [(lab, p) for lab, p in opposite if lab not in self.featured]
            opposite = fresh or opposite
            if opposite:
                lab, p = max(opposite, key=lambda lp: abs(lp[1]))
                commentary = self._claim("c-shift-contrast",
                                         f"{subj(lab)}, by contrast, {_change(p)}.", p, sid)
                highlight.append(lab)
            elif rest:
                lab, p = min(rest, key=lambda lp: abs(lp[1]))
                commentary = self._claim("c-shift-least",
                                         f"{subj(lab)} changed least: it {_change(p)}.", p, sid)
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
        additive = not (tokens & _NON_ADDITIVE_TOKENS)
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
                shares = bool((work[M] >= 0).all()) and (
                    bool(sums.between(97, 103).all()) or bool(sums.between(0.97, 1.03).all()))
                last_vals = wide.loc[periods[-1]].dropna()
                # 1. time x measure
                if room():
                    if additive and not shares:
                        total = work.groupby("__t")[M].sum()
                        ok = self._line_scene(
                            T.name, M, list(total.items()), iso, label, f"Total {_humanize(M)}",
                            f"time series detected; {M} summed across {C} per {T.name}")
                    else:
                        leader = str(last_vals.idxmax())
                        self.featured.add(leader)
                        subject = f"{leader} share" if shares else f"{leader} {_humanize(M)}"
                        ok = self._line_scene(
                            T.name, M, list(wide[last_vals.idxmax()].items()), iso, label,
                            subject, f"time series detected; {M} is "
                            f"{'a share' if shares else 'not additive'}, so it follows the "
                            f"largest {C} in {label(periods[-1])} ({leader})", proper=True)
                    planned += ok
                    if not ok:
                        self.reasons.append(f"(skipped) line-reveal: fewer than 3 {T.name} "
                                            "periods.")
                # 2. category x first/last period
                if room() and len(periods) >= 2:
                    planned += self._slope_scene(C, M, wide.T, periods, label, shares)
                # 3. shares
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
        meta: dict[str, Any] = {
            "title": self.title, "theme": self.theme or "editorial-noir",
            "audience": self.audience, "mode": self.mode,
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
