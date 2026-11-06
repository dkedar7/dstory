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


def to_records(df: "pd.DataFrame") -> list[dict[str, Any]]:
    """Convert a pandas DataFrame to a list of dicts, sanitizing NaN/Inf to None."""
    out: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        rec: dict[str, Any] = {}
        for col in df.columns:
            v = row[col]
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                rec[col] = None
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


def compute_ratio(after: float, before: float) -> Ratio:
    """ratio = after / before, with sane error handling.

    Returns a `Ratio` (a float subclass) so `compute_claim` knows the unit and
    can never print a 3.4x ratio as "3.4%".
    """
    if before == 0:
        raise ValueError("Cannot compute ratio with before=0.")
    return Ratio(after / before)


def compute_pct_change(after: float, before: float) -> PctChange:
    """Percentage change (signed). +50.0 means a 50% increase.

    Returns a `PctChange` (a float subclass) so `compute_claim` knows the unit
    and can never print a +2% change as "doubled".
    """
    if before == 0:
        raise ValueError("Cannot compute pct change with before=0.")
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


def derive_claim_text(value: float, *, kind: str = "auto") -> str:
    """Produce a claim phrase that's safe to feed into the vetter.

    - ratio: "doubled"/"tripled"/... when the ratio is inside the vetter's
             window, otherwise the equivalent percent change (3.4 -> "increased
             by 240.0%").
    - pct:   "doubled"/... when 1 + pct/100 is inside a window, otherwise
             "increased by N%" / "decreased by N%".
    - pp:    "rose N percentage points" / "fell N percentage points".
    - auto:  uses the unit tagged by compute_ratio / compute_pct_change. An
             untagged float is ambiguous: it gets a phrase if it falls in a
             ratio window, otherwise it is treated as a percent change. Pass
             kind= explicitly for plain floats.
    """
    unit = _resolve_unit(value, kind)
    if unit == "pp":
        pts = f"{abs(value):.1f}".removesuffix(".0")
        noun = "point" if pts == "1" else "points"
        return f"{'rose' if value >= 0 else 'fell'} {pts} percentage {noun}"
    if unit == "ratio":
        return ratio_phrase(value) or _pct_phrase((value - 1.0) * 100.0)
    if unit == "pct":
        return ratio_phrase(1.0 + value / 100.0) or _pct_phrase(value)
    return ratio_phrase(value) or _pct_phrase(value)


def compute_claim(
    *,
    id: str,
    text_template: str,
    value: float,
    scene: Optional[str] = None,
    kind: str = "auto",
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
    """
    unit = _resolve_unit(value, kind)
    if unit is None:
        warnings.warn(
            "compute_claim got a plain float with kind='auto', so it can't tell a "
            "ratio from a percent change. Use compute_ratio()/compute_pct_change() "
            "or pass kind='ratio' / kind='pct'.",
            UserWarning, stacklevel=2,
        )
    phrase = derive_claim_text(value, kind=unit or "auto")
    text = text_template.format(phrase=phrase, value=float(value))
    out: dict[str, Any] = {"id": id, "text": text, "value": float(value)}
    if unit is not None:
        out["unit"] = unit
    if scene is not None:
        out["scene"] = scene
    return out


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
