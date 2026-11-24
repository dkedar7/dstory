"""Data-prep helpers: convert pandas DataFrames to dstory's record/long format,
and derive claims so the value automatically matches the chart.

The claim-derivation helpers eliminate a whole class of "the prose says 'tripled'
but the data is actually 2.7×" bugs. Use `compute_claim()` to compute and
store both the value and the textual claim atomically.

These helpers are optional — install dstory[prep] for the pandas dependency.
Without pandas, you can still write records by hand and use the schema.
"""

from __future__ import annotations

import math
import re
import warnings
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd  # type: ignore


def _date_only_columns(df: "pd.DataFrame") -> set:
    """Datetime columns whose every value is a timezone-free midnight: they are
    dates, so they serialize as "2024-01-01" (what the date recipes parse by
    default), not "2024-01-01T00:00:00" (#43)."""
    cols = set()
    for col in df.columns:
        s = df[col]
        if str(s.dtype).startswith("datetime64") and getattr(s.dt, "tz", None) is None:
            v = s.dropna()
            if (v.dt.normalize() == v).all():
                cols.add(col)
    return cols


def to_records(df: "pd.DataFrame") -> list[dict[str, Any]]:
    """Convert a pandas DataFrame to a list of dicts, sanitizing NaN/Inf to None.

    Datetimes become ISO 8601 strings; a column of dates (all midnight, no
    timezone) becomes "2024-01-01"."""
    import pandas as pd  # type: ignore   # a DataFrame came in, so pandas is here

    out: list[dict[str, Any]] = []
    dates = _date_only_columns(df)
    for _, row in df.iterrows():
        rec: dict[str, Any] = {}
        for col in df.columns:
            v = row[col]
            if hasattr(v, "item") and not hasattr(v, "isoformat"):   # numpy scalar
                v = v.item()
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                rec[col] = None
            elif v is None or (pd.api.types.is_scalar(v) and pd.isna(v)):
                # NaT, and pd.NA from nullable dtypes (Int64, Float64, string),
                # which JSON can't hold (#46).
                rec[col] = None
                rec[col] = None
            elif col in dates:
                rec[col] = v.date().isoformat()
            elif hasattr(v, "isoformat"):  # datetime-like
                rec[col] = v.isoformat()
            elif hasattr(v, "item"):  # numpy scalar
                rec[col] = v.item()
            else:
                rec[col] = v
        out.append(rec)
    return out


def to_long(df: "pd.DataFrame", *, id_vars: list[str] | str, value_vars: Optional[list[str]] = None,
            var_name: str = "variable", value_name: str = "value") -> list[dict[str, Any]]:
    """Pivot a wide DataFrame to long records (Vizzu-friendly).

    Wraps `df.melt(...)`. Returns records ready to drop into `data.datasets[X]`.
    """
    long_df = df.melt(id_vars=id_vars, value_vars=value_vars,
                       var_name=var_name, value_name=value_name)
    return to_records(long_df)


# ---------- claim derivation ----------

# The single source of truth for ratio phrases. The vetter builds its
# PHRASE_RULES from RATIO_WINDOWS, so prep can never label a value with a
# phrase the vetter would reject (or vice versa). Windows are inclusive and
# are expressed as after/before ratios.
RATIO_WINDOWS: dict[str, tuple[float, float]] = {
    "doubled":    (1.95, 2.10),
    "tripled":    (2.85, 3.15),
    "quadrupled": (3.85, 4.15),
    "quintupled": (4.85, 5.15),
    "halved":     (0.45, 0.55),
}

# Nominal targets, kept for backward compatibility.
RATIO_PHRASES = {
    "doubled":     2.0,
    "tripled":     3.0,
    "quadrupled":  4.0,
    "quintupled":  5.0,
    "halved":      0.5,
}

CLAIM_UNITS = ("ratio", "pct", "pp")

# Ratios at or above this read as "N-fold" ("rose 12-fold") rather than as a
# percent change ("rose 1100%"). The vetter accepts "N-fold" when the ratio
# rounds to N.
FOLD_MIN_RATIO = 5.5


class Ratio(float):
    """A float tagged as an after/before ratio (2.0 == doubled)."""
    unit = "ratio"


class PctChange(float):
    """A float tagged as a signed percent change (+50.0 == up 50%)."""
    unit = "pct"


class PointChange(float):
    """A float tagged as a signed change in percentage points (+16.0 == up
    16 points, e.g. a share going from 27% to 43%)."""
    unit = "pp"


def ratio_phrase(ratio: float) -> Optional[str]:
    """The phrase whose vetter window contains `ratio`, or None."""
    for word, (lo, hi) in RATIO_WINDOWS.items():
        if lo <= ratio <= hi:
            return word
    return None


def _negative_base_message(what: str, before: float) -> str:
    # #42: dividing by a negative base flips the sign, so a loss that tripled
    # (-100 -> -300) would read "tripled" and a loss that shrank would read
    # "decreased". draft() already refuses a non-positive base (#17).
    return (f"A {what} from a negative base ({before:g}) is ambiguous: dividing by it "
            "flips the direction, so a loss that grew would read as a rise. Describe the "
            "change in units instead (e.g. fmt_compact(after - before)), or use "
            "compute_point_change for rates.")


def compute_ratio(after: float, before: float) -> Ratio:
    """ratio = after / before, with sane error handling.

    Returns a `Ratio` (a float subclass) so `compute_claim` knows the unit and
    can never print a 3.4x ratio as "3.4%".
    """
    if before == 0:
        raise ValueError("Cannot compute ratio with before=0.")
    if before < 0:
        raise ValueError(_negative_base_message("ratio", before))
    return Ratio(after / before)


def compute_pct_change(after: float, before: float) -> PctChange:
    """Percentage change (signed). +50.0 means a 50% increase.

    Returns a `PctChange` (a float subclass) so `compute_claim` knows the unit
    and can never print a +2% change as "doubled".
    """
    if before == 0:
        raise ValueError("Cannot compute pct change with before=0.")
    if before < 0:
        raise ValueError(_negative_base_message("percent change", before))
    return PctChange((after - before) / before * 100.0)


def compute_point_change(after: float, before: float, *, scale: float = 1.0) -> PointChange:
    """Change between two shares or rates, in percentage points (signed).

    Pass shares as percentages (27.0, 43.0), or as fractions with scale=100
    (0.27, 0.43 -> +16.0). Use this rather than compute_pct_change for shares:
    a share going from 39% to 15% "fell 24 points", not "fell 61.5%".
    """
    return PointChange((after - before) * scale)


def fold_phrase(ratio: float) -> Optional[str]:
    """'12-fold' for a ratio of ~12 (at or above FOLD_MIN_RATIO), else None."""
    if ratio != ratio or ratio < FOLD_MIN_RATIO:
        return None
    return f"{round(ratio):d}-fold"


def _resolve_unit(value: float, kind: str) -> Optional[str]:
    if kind in CLAIM_UNITS:
        return kind
    if kind != "auto":
        raise ValueError(f"kind must be 'auto', 'ratio', 'pct' or 'pp', got {kind!r}.")
    return getattr(value, "unit", None)


def _pct_phrase(pct: float) -> str:
    if pct >= 0:
        return f"increased by {pct:.1f}%"
    return f"decreased by {abs(pct):.1f}%"


def _change_phrase(pct: float, style: str, ratio: Optional[float] = None) -> str:
    """A percent change in words. style="auto" follows draft()'s newsroom
    rules: 12x reads "rose 12-fold" and a change that rounds to 0.0% reads
    "held steady" (#39). style="percent" is the pre-0.15 wording."""
    ratio = 1.0 + pct / 100.0 if ratio is None else ratio
    word = ratio_phrase(ratio)
    if word:
        return word
    if style == "auto":
        fold = fold_phrase(ratio)
        if fold:
            return f"rose {fold}"
        if abs(pct) < 0.05:
            return "held steady, a 0% change"
    return _pct_phrase(pct)


def derive_claim_text(value: float, *, kind: str = "auto", style: str = "auto") -> str:
    """Produce a claim phrase that's safe to feed into the vetter.

    - ratio: "doubled"/"tripled"/... when the ratio is inside the vetter's
             window, otherwise the equivalent percent change (3.4 -> "increased
             by 240.0%").
    - pct:   "doubled"/... when 1 + pct/100 is inside a window, otherwise
             "increased by N%" / "decreased by N%".
    - pp:    "rose N percentage points" / "fell N percentage points".
    - style: "auto" (default) writes 5.5x or more as "rose 12-fold" and a
             change under 0.05% as "held steady, a 0% change", matching
             draft(); "percent" always writes "increased/decreased by N%".
    - auto:  uses the unit tagged by compute_ratio / compute_pct_change. An
             untagged float is ambiguous: it gets a phrase if it falls in a
             ratio window, otherwise it is treated as a percent change. Pass
             kind= explicitly for plain floats.
    """
    if style not in ("auto", "percent"):
        raise ValueError(f"style must be 'auto' or 'percent', got {style!r}.")
    unit = _resolve_unit(value, kind)
    if unit == "pp":
        pts = f"{abs(value):.1f}".removesuffix(".0")
        noun = "point" if pts == "1" else "points"
        return f"{'rose' if value >= 0 else 'fell'} {pts} percentage {noun}"
    if unit in ("ratio", "pct"):
        pct = (value - 1.0) * 100.0 if unit == "ratio" else value
        if pct < -100:
            # The value crossed zero (100 -> -50 is -150%): no percent phrase is
            # honest, and the vetter blocks one, so don't write it (#42).
            raise ValueError(
                f"A {pct:.0f}% change means the value changed sign; a percent change "
                "across zero misleads readers. Write the text yourself and describe the "
                "swing (e.g. 'turned negative'), with the change in units.")
        if unit == "ratio":
            return _change_phrase(pct, style, ratio=value)
        return _change_phrase(value, style)
    return ratio_phrase(value) or _pct_phrase(value)


def compute_claim(
    *,
    id: str,
    text_template: str,
    value: float,
    scene: Optional[str] = None,
    kind: str = "auto",
    from_: Optional[dict[str, Any]] = None,
    style: str = "auto",
) -> dict[str, Any]:
    """Build a `Claim` dict ready to drop into `data['claims']`.

    The value is computed by the caller (use compute_ratio/compute_pct_change),
    then formatted into the text via `text_template`. The claim records the
    value's unit ("ratio" or "pct") so the vetter checks the text against the
    right interpretation. With a plain float, pass kind="ratio" or kind="pct";
    otherwise a warning is raised because the unit is ambiguous.

    Example:
        ratio = compute_ratio(after=4_200_000, before=1_380_000)   # ~3.04
        claim = compute_claim(
            id="c1",
            text_template="Monthly volume {phrase} between Jan and Mar 2024",
            value=ratio,
            scene="scene-trend",
        )
        # -> {"id": "c1", "text": "Monthly volume tripled between ...",
        #     "value": 3.04, "unit": "ratio", ...}

    Pass `from_` (built with `claim_from`) to record how the value follows
    from the scene's dataset. The bundler and vetter then recompute it, so
    editing the data without updating the claim fails instead of shipping a
    stale number (#38).

    `style` picks the wording of {phrase}: "auto" writes big multiples as
    "rose 12-fold" and no change as "held steady"; "percent" keeps
    "increased by 1100.0%" (#39).
    """
    unit = _resolve_unit(value, kind)
    if unit is None:
        warnings.warn(
            "compute_claim got a plain float with kind='auto', so it can't tell a "
            "ratio from a percent change. Use compute_ratio()/compute_pct_change() "
            "or pass kind='ratio' / kind='pct'.",
            UserWarning, stacklevel=2,
        )
    phrase = derive_claim_text(value, kind=unit or "auto", style=style)
    text = text_template.format(phrase=phrase, value=float(value))
    out: dict[str, Any] = {"id": id, "text": text, "value": float(value)}
    if unit is not None:
        out["unit"] = unit
    if scene is not None:
        out["scene"] = scene
    if from_ is not None:
        out["from"] = from_
    return out


# ---------- claim provenance (#38) ----------
#
# A claim's `from` says how its value follows from a dataset, so the value can
# be recomputed whenever the data changes:
#
#   {"op": "pct",   "after": <operand>, "before": <operand>}   percent change
#   {"op": "ratio", "after": <operand>, "before": <operand>}   after / before
#   {"op": "pp",    "after": <operand>, "before": <operand>, "scale": 100}
#                   point change, (after - before) x scale
#   {"op": "share", "part": <operand>, "whole": <operand>}     part / whole (0..1)
#   {"op": "value", "of": <operand>}                           a level
#
# An operand is {"sum": "<column>", "where": {"<column>": <value>, ...}}: the
# sum of a column over the rows that match (one row, or a total). Optional:
# "dataset" (defaults to the claim's scene dataset) and "rank": {"by":
# "<column>", "is": 1}, which says the claim is a superlative ("the biggest
# shift of any source"): recomputed for every value of that column, this one
# must rank `is` (1 = largest, 2 = second, -1 = smallest; by size of change
# for pct / pp / ratio, by value for share / value).

_FROM_OPS = {"pct": ("after", "before"), "ratio": ("after", "before"),
             "pp": ("after", "before"), "share": ("part", "whole"), "value": ("of",)}


def claim_from(op: str, *, dataset: Optional[str] = None, rank: Optional[dict] = None,
               scale: Optional[float] = None, **operands: dict[str, Any]) -> dict[str, Any]:
    """Build a claim's `from` spec, for `compute_claim(..., from_=...)`.

    Example: Coal's share fell 24 points, the biggest shift of any source:
        claim_from("pp", after=operand("end", source="Coal"),
                   before=operand("start", source="Coal"),
                   rank={"by": "source", "is": 1})
    """
    if op not in _FROM_OPS:
        raise ValueError(f"op must be one of {', '.join(_FROM_OPS)}, got {op!r}.")
    missing = [k for k in _FROM_OPS[op] if k not in operands]
    if missing:
        raise ValueError(f"op {op!r} needs operand(s) {', '.join(missing)}.")
    spec: dict[str, Any] = {"op": op, **{k: operands[k] for k in _FROM_OPS[op]}}
    if dataset is not None:
        spec["dataset"] = dataset
    if scale is not None:
        spec["scale"] = scale
    if rank is not None:
        spec["rank"] = rank
    return spec


def operand(column: str, **where: Any) -> dict[str, Any]:
    """One operand of `claim_from`: the sum of `column` over matching rows."""
    return {"sum": column, "where": where} if where else {"sum": column}


def _same(a: Any, b: Any) -> bool:
    if a == b:
        return True
    if isinstance(a, bool) or isinstance(b, bool):
        return False
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)


def _operand_value(o: Any, rows: list[dict[str, Any]]) -> Optional[float]:
    if not isinstance(o, dict) or not isinstance(o.get("sum"), str):
        raise ValueError(f"an operand must be {{'sum': column, 'where': {{...}}}}, got {o!r}")
    col, where = o["sum"], o.get("where") or {}
    total, hit = 0.0, False
    for r in rows:
        if not isinstance(r, dict):
            continue
        if all(_same(r.get(k), v) for k, v in where.items()):
            v = r.get(col)
            if v is None or isinstance(v, bool):
                continue
            try:
                total += float(v)
            except (TypeError, ValueError):
                continue
            hit = True
    return total if hit else None


def _evaluate(spec: dict[str, Any], rows: list[dict[str, Any]]) -> Optional[float]:
    op = spec.get("op")
    if op not in _FROM_OPS:
        raise ValueError(f"unknown op {op!r} (use {', '.join(_FROM_OPS)})")
    vals = [_operand_value(spec.get(k), rows) for k in _FROM_OPS[op]]
    if any(v is None for v in vals):
        return None
    if op == "value":
        return vals[0]
    a, b = vals
    if op == "pp":
        return (a - b) * float(spec.get("scale", 1) or 1)
    if b == 0:
        return None
    if op == "pct":
        return (a - b) / b * 100.0
    return a / b   # ratio, share


def _magnitude(op: str, v: float) -> float:
    if op in ("pct", "pp"):
        return abs(v)
    if op == "ratio":
        return abs(math.log(v)) if v > 0 else float("inf")
    return v


def _with_key(o: Any, by: str, key: Any) -> Any:
    if isinstance(o, dict) and by in (o.get("where") or {}):
        return {**o, "where": {**o["where"], by: key}}
    return o


def recompute_claim(spec: dict[str, Any], rows: list[dict[str, Any]]
                    ) -> tuple[Optional[float], Optional[str]]:
    """Recompute a claim's value from its `from` spec over a dataset's rows.

    Returns (value, problem). value is None when the rows the spec names are
    gone. problem says what no longer holds: the rows are missing, or the
    claim's superlative now belongs to someone else. Raises ValueError on a
    malformed spec."""
    value = _evaluate(spec, rows)
    if value is None:
        return None, "the rows it was computed from are gone or have no numbers"
    if spec.get("op") in ("pct", "ratio"):
        base = _operand_value(spec.get("before"), rows)
        if base is not None and base < 0:
            # #42: a change from a negative base reads backwards ("tripled"
            # for a loss that tripled), so it can't be stated as pct or ratio.
            after = _operand_value(spec.get("after"), rows)
            return value, (f"its base (before) is negative ({base:g} -> {after:g}), so a "
                           f"{'percent change' if spec['op'] == 'pct' else 'ratio'} reads "
                           "backwards; describe the change in units instead")
    rank = spec.get("rank")
    if not isinstance(rank, dict) or not isinstance(rank.get("by"), str):
        return value, None
    by, pos = rank["by"], int(rank.get("is", 1))
    ops = _FROM_OPS[spec["op"]]
    me = next((spec[k]["where"][by] for k in ops
               if isinstance(spec.get(k), dict) and by in (spec[k].get("where") or {})), None)
    if me is None:
        return value, None
    keys: list[Any] = []
    for r in rows:
        k = r.get(by) if isinstance(r, dict) else None
        if k is not None and not any(_same(k, x) for x in keys):
            keys.append(k)
    scored = []
    for k in keys:
        sub = {**spec, **{n: _with_key(spec.get(n), by, k) for n in ops}}
        v = _evaluate(sub, rows)
        if v is not None:
            scored.append((k, _magnitude(spec["op"], v)))
    order = sorted(scored, key=lambda kv: -kv[1])
    idx = pos - 1 if pos > 0 else len(order) + pos
    word = {1: "first", 2: "second", -1: "last"}.get(pos, f"at position {pos}")
    if not 0 <= idx < len(order):
        return value, f"it says {me} ranks {word} by {by}, but only {len(order)} can be ranked"
    target = order[idx][1]
    mine = next((m for k, m in scored if _same(k, me)), None)
    if mine is None or abs(mine - target) > 1e-9 * max(1.0, abs(target)):
        return value, f"it says {me} ranks {word} by {by}, but {order[idx][0]} now does"
    return value, None


# ---------- number formatting (no pandas needed) ----------

def fmt_compact(n: float, *, digits: int = 1) -> str:
    """Format a number compactly for prose/annotations: 1234567 → '1.2M'.

    Uses K/M/B/T suffixes; trims trailing '.0' so 2000 → '2K', not '2.0K'.
    """
    sign = "-" if n < 0 else ""
    x = abs(float(n))
    scales = ((1.0, ""), (1e3, "K"), (1e6, "M"), (1e9, "B"), (1e12, "T"))
    # Start at the largest suffix the raw value reaches, then pick the suffix
    # *after* rounding: 999_999 rounds to "1000K", which must read "1M".
    i = max(k for k, (threshold, _) in enumerate(scales) if k == 0 or x >= threshold)
    while True:
        threshold, suffix = scales[i]
        rounded = round(x / threshold, digits)
        if rounded >= 1000 and i + 1 < len(scales):
            i += 1
            continue
        s = f"{rounded:.{digits}f}".rstrip("0").rstrip(".") if digits > 0 else f"{rounded:.0f}"
        return f"{sign}{s}{suffix}"


def fmt_pct(value: float, *, digits: int = 1, signed: bool = False) -> str:
    """Format a percentage for prose: 42.0 → '42%', 7.25 → '7.3%'.

    `value` is in percent units (use compute_pct_change's output directly).
    signed=True keeps the leading '+' on increases.
    """
    s = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    if signed and value > 0:
        s = f"+{s}"
    return f"{s}%"


# ---------- convenience: time-series prep ----------

def add_deltas(df: "pd.DataFrame", *, value_col: str, date_col: str = "date",
               yoy_period: int = 12) -> "pd.DataFrame":
    """Add MoM delta + pct-change columns and a YoY pct-change column.

    Returns a new DataFrame; doesn't mutate the original.
    """
    out = df.sort_values(date_col).copy()
    out[f"{value_col}_delta"]      = out[value_col].diff()
    out[f"{value_col}_pct_change"] = out[value_col].pct_change() * 100
    out[f"{value_col}_yoy_pct"]    = out[value_col].pct_change(periods=yoy_period) * 100
    return out
