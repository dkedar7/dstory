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

# Same vocabulary the vetter uses for cross-checking. Keeping these lists in sync
# is intentional: if the prose says "tripled," the value must satisfy the predicate.
RATIO_PHRASES = {
    "doubled":     2.0,
    "tripled":     3.0,
    "quadrupled":  4.0,
    "quintupled":  5.0,
    "halved":      0.5,
}


def compute_ratio(after: float, before: float) -> float:
    """ratio = after / before, with sane error handling."""
    if before == 0:
        raise ValueError("Cannot compute ratio with before=0.")
    return after / before


def compute_pct_change(after: float, before: float) -> float:
    """Percentage change (signed). +50.0 means a 50% increase."""
    if before == 0:
        raise ValueError("Cannot compute pct change with before=0.")
    return (after - before) / before * 100.0


def derive_claim_text(value: float, *, kind: str = "auto") -> str:
    """Produce a claim phrase that's safe to feed into the vetter.

    - ratio:   "doubled"/"tripled"/.. or "Nx" / "N-fold"
    - pct:     "increased by N%" / "decreased by N%"
    - auto:    matches a known ratio phrase if value is near one (2.0, 3.0, 0.5, etc),
               otherwise treats value as a percentage change
    """
    if kind in ("ratio", "auto"):
        # Tolerance matches the vetter's predicate window (target ± 0.15) so
        # any value that derive_claim_text labels with a phrase will pass vet.
        for word, target in RATIO_PHRASES.items():
            if abs(value - target) <= 0.15:
                return word
        if kind == "ratio":
            # Forced ratio mode: produce a generic ratio phrase
            if value >= 2:
                return f"{value:.1f}× higher"
            if value <= 0.5:
                return f"{value:.2f}× as much (a {(1-value)*100:.0f}% drop)"
            return f"{value:.2f}× the prior level"
        # auto + no phrase match → fall through to pct
    if value >= 0:
        return f"increased by {value:.1f}%"
    return f"decreased by {abs(value):.1f}%"


def compute_claim(
    *,
    id: str,
    text_template: str,
    value: float,
    scene: Optional[str] = None,
) -> dict[str, Any]:
    """Build a `Claim` dict ready to drop into `data['claims']`.

    The value is computed by the caller (use compute_ratio/compute_pct_change),
    then formatted into the text via `text_template`. Vetter will cross-check
    the rendered prose against this value.

    Example:
        ratio = compute_ratio(after=4_200_000, before=1_380_000)   # ~3.04
        claim = compute_claim(
            id="c1",
            text_template="Monthly volume {phrase} between Jan and Mar 2024",
            value=ratio,
            scene="scene-trend",
        )
        # → {"id": "c1", "text": "Monthly volume tripled between ...", "value": 3.04, ...}
    """
    phrase = derive_claim_text(value)
    text = text_template.format(phrase=phrase, value=value)
    out: dict[str, Any] = {"id": id, "text": text, "value": float(value)}
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
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if x >= threshold:
            s = f"{x / threshold:.{digits}f}".rstrip("0").rstrip(".")
            return f"{sign}{s}{suffix}"
    s = f"{x:.{digits}f}".rstrip("0").rstrip(".")
    return f"{sign}{s}"


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
