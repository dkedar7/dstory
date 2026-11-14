"""Vet a bundled story HTML against five dimensions:
  1. Renders correctly (headless browser, 3 viewports, no console errors)
  2. Data fidelity (claims cross-checked against data.json)
  3. Editorial integrity (no slop phrases, sources present, no placeholders)
  4. Visual quality (screenshots for manual review)
  5. Accessibility & ethics (contrast, PII, dual-axis warnings)

Browser checks (1, 4, parts of 5) require Playwright. Static checks (2, 3, parts of 5)
work without it. CLI/Python-API: pass `browser=False` to skip browser checks.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .prep import RATIO_WINDOWS


# ---------- result types ----------

@dataclass
class Dimension:
    name: str
    passed: bool = True
    issues: list[str] = field(default_factory=list)
    notes:  list[str] = field(default_factory=list)
    # True when the dimension's checks did not run (e.g. browser=False). A
    # skipped dimension never fails, so callers should not read its `passed`
    # as "checked and clean"; see Report.skipped.
    skipped: bool = False

    def fail(self, msg: str) -> None:
        self.passed = False
        self.issues.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)


@dataclass
class Report:
    html_path: str
    data_path: str
    dimensions: list[Dimension] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(d.passed for d in self.dimensions)

    @property
    def skipped(self) -> list[str]:
        """Names of dimensions whose checks did not run."""
        return [d.name for d in self.dimensions if d.skipped]

    @property
    def complete(self) -> bool:
        """True when every dimension actually ran."""
        return not self.skipped

    def to_json(self) -> dict[str, Any]:
        return {
            "html_path": self.html_path,
            "data_path": self.data_path,
            "passed": self.passed,
            "complete": self.complete,
            "dimensions": [
                {"name": d.name, "passed": d.passed, "skipped": d.skipped,
                 "issues": d.issues, "notes": d.notes}
                for d in self.dimensions
            ],
        }


# ---------- color / contrast ----------

def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    def chan(c: float) -> float:
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(rgb1, rgb2) -> float:
    l1, l2 = _relative_luminance(rgb1), _relative_luminance(rgb2)
    lo, hi = min(l1, l2), max(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _parse_color(s: str) -> Optional[tuple[float, float, float]]:
    s = s.strip()
    m = re.match(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b", s)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    m = re.match(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)", s)
    if m:
        return (float(m.group(1)), float(m.group(2)), float(m.group(3)))
    return None


# ---------- static checks (no browser) ----------

def _window(lo: float, hi: float):
    return lambda v: lo <= v <= hi


# Ratio phrases share their windows with dstory.prep (RATIO_WINDOWS), so a
# claim built with compute_claim() always satisfies these predicates. Each
# predicate takes an after/before ratio.
PHRASE_RULES: list[tuple[re.Pattern, callable]] = [
    (re.compile(rf"\b{word}\b", re.I), _window(lo, hi))
    for word, (lo, hi) in RATIO_WINDOWS.items()
]
# "majority" is about a share (0..1), not a ratio; only checked for claims
# without an explicit unit.
MAJORITY_RULE = (re.compile(r"\bmajority\b", re.I), lambda v: v >= 0.50)
PHRASE_RULES.append(MAJORITY_RULE)
PCT_TOLERANCE_PP = 0.5
# A direction verb directly before the number ("rose 12%", "decreased by 4%")
# makes the sign part of the check; without one only the magnitude is compared.
_UP_STEMS = ("increas", "rose", "rise", "risen", "grew", "grow", "gain", "climb", "jump")
_DOWN_STEMS = ("decreas", "fell", "fall", "drop", "declin", "lost", "lose", "shrank",
               "shrunk", "slid", "slump")
_DIRECTION = "|".join(_UP_STEMS + _DOWN_STEMS)
_PCT_RE = re.compile(rf"(?:\b({_DIRECTION})\w*\s+(?:by\s+)?)?(\d+(?:\.\d+)?)\s*%", re.I)
_POINTS_RE = re.compile(rf"(?:\b({_DIRECTION})\w*\s+(?:by\s+)?)?(\d+(?:\.\d+)?)\s*"
                        r"(?:percentage[- ]points?|points?|pp)\b", re.I)
_FOLD_RE = re.compile(r"\b(\d+(?:\.\d+)?)[- ]?fold\b", re.I)


def _signed(direction: Optional[str], stated: float) -> float:
    d = (direction or "").lower()
    return -stated if any(d.startswith(s) for s in _DOWN_STEMS) else stated

SLOP_PHRASES = [
    "lorem ipsum", "[placeholder]", "[todo]", "TODO:", "as you can see",
    "as shown in the chart above", "interestingly", "studies suggest",
    "many believe", "it could be argued", "click here", "learn more →",
]

PII_PATTERNS = [
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "email address"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "SSN-shaped number"),
    (re.compile(r"\b\+?\d{1,2}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "phone-shaped number"),
]


# ---------- readability ----------

# Minimum Flesch reading ease per audience. Below the floor, the prose is
# harder than that audience should have to work for. Notes, not failures —
# domain vocabulary can legitimately depress the score.
READING_EASE_FLOORS: dict[str, float] = {
    "student":        60.0,   # plain conversational English
    "general-public": 50.0,   # newspaper level
    "policymaker":    40.0,
    "executive":      40.0,
    # technical-peer: no floor — jargon is the shared language.
}

_VOWEL_GROUPS = re.compile(r"[aeiouy]+")


def _count_syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    n = len(_VOWEL_GROUPS.findall(w))
    # Silent trailing 'e' (have, time) — but not -le (table) or -ee (free).
    if w.endswith("e") and not w.endswith(("le", "ee")) and n > 1:
        n -= 1
    return max(1, n)


def flesch_reading_ease(text: str) -> Optional[float]:
    """Flesch reading ease (higher = easier; ~60-70 is plain English).

    Returns None when there's too little text (< 40 words) to score reliably.
    English-only heuristic.
    """
    words = re.findall(r"[A-Za-z']+", text)
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    if len(words) < 40 or not sentences:
        return None
    syllables = sum(_count_syllables(w) for w in words)
    return (206.835
            - 1.015 * (len(words) / len(sentences))
            - 84.6 * (syllables / len(words)))


def _scene_text_shown(s: dict[str, Any]) -> bool:
    """Whether the template renders a scene's own headline and commentary.
    `chrome: false` hides them for simple, scrolly and pinned scenes; every
    other kind shows them (custom renderers are free to draw them)."""
    return not (s.get("chrome") is False
                and (s.get("kind") or "simple") in ("simple", "scrolly", "pinned"))


def _visible_text(data: dict[str, Any]) -> str:
    """Everything in data.json a reader can see on the page: meta text, scene
    prose, source lines, credits, and dataset cells (shown in the data
    tables). Not claims, ids or config, which no reader sees."""
    meta = data.get("meta") or {}
    parts = [_reader_prose(data)]
    for k in ("author", "credits", "published"):
        if meta.get(k):
            parts.append(str(meta[k]))
    for src in meta.get("sources") or []:
        if isinstance(src, dict):
            parts += [str(src[k]) for k in ("name", "note") if src.get(k)]
    for sc in data.get("scenes", []):
        if isinstance(sc, dict) and sc.get("source_line"):
            parts.append(str(sc["source_line"]))
    for rows in (data.get("datasets") or {}).values():
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    parts += [v for v in row.values() if isinstance(v, str)]
    return "\n".join(parts)


def _story_prose(data: dict[str, Any]) -> str:
    """Collect the reader-facing prose from data.json (headlines, commentary,
    steps, frames, deck) — the text a reader actually encounters."""
    parts: list[str] = []
    meta = data.get("meta", {})
    for k in ("deck", "subtitle", "description"):
        if meta.get(k):
            parts.append(str(meta[k]))
    for s in data.get("scenes", []):
        for k in ("headline", "commentary"):
            if s.get(k) and _scene_text_shown(s):
                parts.append(str(s[k]))
        for step in (s.get("steps") or []) + (s.get("frames") or []):
            for k in ("headline", "commentary"):
                if step.get(k):
                    parts.append(str(step[k]))
    # Join with ". " so unpunctuated headlines count as their own sentences
    # instead of fusing into one run-on (which would tank the score).
    return ". ".join(parts)


def _scene_prose(s: dict[str, Any]) -> str:
    """Everything a reader can see or hear for one scene."""
    keys = ("headline", "commentary", "alt") if _scene_text_shown(s) else ("alt",)
    parts = [str(s[k]) for k in keys if s.get(k)]
    for step in (s.get("steps") or []) + (s.get("frames") or []):
        if isinstance(step, dict):
            parts += [str(step[k]) for k in ("headline", "commentary") if step.get(k)]
    ann = s.get("annotation")
    if isinstance(ann, dict) and ann.get("text"):
        parts.append(str(ann["text"]))
    return ". ".join(parts)


def _reader_prose(data: dict[str, Any]) -> str:
    """The reader-facing text in data.json: meta title/deck and every scene's
    prose. Never the claims array, which no reader sees."""
    meta = data.get("meta") or {}
    parts = [str(meta[k]) for k in ("title", "subtitle", "deck", "description") if meta.get(k)]
    parts += [_scene_prose(s) for s in data.get("scenes", []) if isinstance(s, dict)]
    return ". ".join(p for p in parts if p)


def _strip_html_for_prose(html: str) -> str:
    out = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.I)
    out = re.sub(r"<style[\s\S]*?</style>",   "", out,  flags=re.I)
    return re.sub(r"<[^>]+>", " ", out)


def check_data_fidelity(html: str, data: dict[str, Any]) -> Dimension:
    r = Dimension("Data fidelity")
    claims = data.get("claims", [])
    if not claims:
        r.note("No claims in data.json — skipping cross-check. Add a 'claims' array to enable.")
        return r

    # What the reader sees: the static HTML (scripts stripped, so the inlined
    # data.json is not counted) plus the prose the runtime renders from
    # data.json. Not json.dumps(data): that contains the claims themselves,
    # so every claim would always be "found".
    prose = _strip_html_for_prose(html) + "\n" + _reader_prose(data)
    prose_lower = re.sub(r"\s+", " ", prose.lower())

    for c in claims:
        text  = c.get("text", "")
        value = c.get("value")
        cid   = c.get("id", "?")

        if not text:
            continue

        norm_text = re.sub(r"\s+", " ", text.strip().lower())
        if norm_text and norm_text not in prose_lower:
            r.note(f"Claim {cid!r} (\"{text}\") is not in any reader-facing text; the "
                   "story may say something else. Check the headline and commentary.")

        unit = c.get("unit")
        # Normalise the value to the two scales the rules need.
        if unit == "pp":
            _check_points_claim(r, cid, text, value)
            continue
        if value is None:
            as_ratio = actual_pct = None
        elif unit == "ratio":
            as_ratio, actual_pct = value, (value - 1.0) * 100.0
        elif unit == "pct":
            as_ratio, actual_pct = 1.0 + value / 100.0, value
        else:
            # Legacy, unit-less claim: 0..1 reads as a share, else as percent.
            as_ratio, actual_pct = value, (value * 100 if 0 <= value <= 1 else value)

        for pattern, predicate in PHRASE_RULES:
            if (pattern, predicate) == MAJORITY_RULE and unit is not None:
                continue
            if pattern.search(text):
                if value is None:
                    r.fail(f"Claim {cid!r} uses '{pattern.pattern}' but has no numeric value.")
                elif not predicate(as_ratio):
                    r.fail(f"Claim {cid!r}: prose says \"{text}\" but value={value}"
                           f"{f' ({unit})' if unit else ''} fails check for "
                           f"'{pattern.pattern}'. Either rephrase or fix the data.")

        if value is not None and unit in ("pct", "ratio") and actual_pct < -100:
            r.fail(f"Claim {cid!r}: a {actual_pct:.0f}% change means the value changed sign; "
                   "a percent change across zero misleads readers. Describe the swing "
                   "instead (e.g. 'turned negative').")

        m = _PCT_RE.search(text)
        if m and value is not None:
            direction, stated = m.group(1), float(m.group(2))
            stated = _signed(direction, stated)
            # Without an explicit direction word, compare magnitudes only.
            got = actual_pct if direction else abs(actual_pct)
            if abs(got - stated) > PCT_TOLERANCE_PP:
                r.fail(f"Claim {cid!r}: prose says {m.group(0).strip()}, derived value is "
                       f"{actual_pct:+.2f}% (tolerance {PCT_TOLERANCE_PP}pp).")

        f = _FOLD_RE.search(text)
        if f and value is not None and abs(as_ratio - float(f.group(1))) > 0.5:
            r.fail(f"Claim {cid!r}: prose says {f.group(0)}, but the ratio is "
                   f"{as_ratio:.2f}.")

    _check_scene_prose_against_claims(r, data, claims)
    return r


def _claim_ratio(c: dict[str, Any]) -> Optional[float]:
    value, unit = c.get("value"), c.get("unit")
    if value is None or unit == "pp":
        return None
    if unit == "pct":
        return 1.0 + value / 100.0
    return value


# Scene-prose drift (#25, #29). A change stated with a direction is checked
# against the scene's claims: "rose 30%", "down 4%", "a 30% drop", "5x",
# "five times over", "fell by half", "up 2 points". A bare "12%" with no
# direction may be a level or a share, so it is left alone.
_SCENE_UP = _UP_STEMS
_SCENE_DOWN = _DOWN_STEMS + ("cut", "plung", "sank", "sunk", "tumbl")
_NOUN_UP = ("increase", "rise", "gain", "jump", "growth", "climb", "surge")
_NOUN_DOWN = ("decrease", "drop", "decline", "fall", "loss", "cut", "slump", "plunge")
_VERB = rf"(?:(?P<verb>{'|'.join(_SCENE_UP + _SCENE_DOWN)})\w*|(?<!made )(?<!make )(?<!makes )(?<!making )(?<!ended )(?<!end )(?P<updown>up|down))"
_QUAL = r"(?P<qual>about|around|roughly|nearly|almost|over|more than|less than|under)?\s*"
_NOUN = rf"(?P<noun>{'|'.join(_NOUN_UP + _NOUN_DOWN)})\w*"
_SCENE_PCT_RE = re.compile(
    rf"\b{_VERB}\s+(?:by\s+)?{_QUAL}(?P<n>\d+(?:\.\d+)?)\s*(?:%|percent\b)"
    rf"|\b{_QUAL.replace('qual', 'qual2')}(?P<n2>\d+(?:\.\d+)?)\s*(?:%|percent)\s+{_NOUN}",
    re.I)
_SCENE_POINTS_RE = re.compile(
    rf"\b{_VERB}\s+(?:by\s+)?{_QUAL}(?P<n>\d+(?:\.\d+)?)\s*"
    r"(?:percentage[- ]points?|points?|pp)\b"
    rf"|\b{_QUAL.replace('qual', 'qual2')}(?P<n2>\d+(?:\.\d+)?)[- ]?"
    rf"(?:percentage[- ]points?|points?|pp)\s+{_NOUN}",
    re.I)
_NUM_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
              "eight": 8, "nine": 9, "ten": 10, "twice": 2}
_TIMES_RE = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)\s*[x×](?!\w)"
    r"|\b(\d+(?:\.\d+)?)\s+times\b(\s+more\b)?"
    rf"|\b({'|'.join(k for k in _NUM_WORDS if k != 'twice')})[- ]fold\b"
    rf"|\b({'|'.join(k for k in _NUM_WORDS if k != 'twice')})\s+times\s+"
    r"(over|as|larger|bigger|higher|greater|more)\b", re.I)
_HALF_RE = re.compile(rf"\b({'|'.join(_SCENE_UP + _SCENE_DOWN)})\w*\s+(?:by\s+)?(?:a\s+|one\s+)?half\b", re.I)


def _scene_sign(word: str) -> int:
    w = (word or "").lower()
    if w == "down" or any(w.startswith(s) for s in _SCENE_DOWN + _NOUN_DOWN):
        return -1
    return 1


def _stated_change(m: "re.Match") -> tuple[float, float]:
    """(signed value, tolerance) for a _SCENE_PCT_RE / _SCENE_POINTS_RE match.
    A hedge ("about", "nearly", "over") widens the tolerance to 10%."""
    if m.group("n") is not None:
        word = m.group("verb") or m.group("updown")
        n, qual = float(m.group("n")), m.group("qual")
    else:
        word, n, qual = m.group("noun"), float(m.group("n2")), m.group("qual2")
    tol = max(PCT_TOLERANCE_PP, 0.1 * n) if qual else PCT_TOLERANCE_PP
    return _scene_sign(word) * n, tol


def _check_scene_prose_against_claims(r: "Dimension", data: dict[str, Any],
                                      claims: list[dict[str, Any]]) -> None:
    """The prose a reader sees must agree with the claims tied to its scene.

    A claim registered with compute_claim() can be right while the headline
    above the chart was edited later ("tripled" -> "quintupled", "rose 30%"
    -> "fell 30%"). For every scene with claims, each ratio word, N-fold,
    Nx, directed percent change ("fell 30%") and directed points change in
    its prose must fit at least one of those claims; otherwise the scene
    has drifted."""
    by_scene: dict[str, list[dict[str, Any]]] = {}
    for c in claims:
        if isinstance(c, dict) and c.get("scene") and c.get("value") is not None:
            by_scene.setdefault(str(c["scene"]), []).append(c)
    if not by_scene:
        return
    for s in data.get("scenes", []):
        if not isinstance(s, dict) or s.get("id") not in by_scene:
            continue
        mine = by_scene[s["id"]]
        ratio_claims = [c for c in mine if _claim_ratio(c) is not None]
        ratios = [_claim_ratio(c) for c in ratio_claims]
        # Percent changes are compared only with claims that carry a unit;
        # a legacy unit-less claim may be a share, not a change.
        pcts = [(_claim_ratio(c) - 1.0) * 100.0 for c in ratio_claims
                if c.get("unit") in ("pct", "ratio")]
        unit_ratios = [_claim_ratio(c) for c in ratio_claims if c.get("unit") in ("pct", "ratio")]
        points = [float(c["value"]) for c in mine if c.get("unit") == "pp"]
        prose = _scene_prose(s)
        sid = s["id"]

        def drift(said: str, against: list[dict[str, Any]], have: str) -> None:
            ids = ", ".join(repr(c.get("id", "?")) for c in against)
            r.fail(f"Scene {sid!r} says \"{said.strip()}\", but its claim(s) {ids} "
                   f"{have}. The prose has drifted from the data: fix the text, or the "
                   "claim (register one for every change the scene states).")

        ratio_have = f"have ratio {', '.join(f'{x:.2f}' for x in ratios)}"
        if ratios:
            for pattern, predicate in PHRASE_RULES:
                if (pattern, predicate) == MAJORITY_RULE:
                    continue
                m = pattern.search(prose)
                if m and not any(predicate(x) for x in ratios):
                    drift(m.group(0), ratio_claims, ratio_have)
            for f in _FOLD_RE.finditer(prose):
                if not any(abs(x - float(f.group(1))) <= 0.5 for x in ratios):
                    drift(f.group(0), ratio_claims, ratio_have)
            for t in (_TIMES_RE.finditer(prose) if unit_ratios else ()):
                num, more = None, False
                if t.group(1):
                    num = float(t.group(1))
                elif t.group(2):
                    num, more = float(t.group(2)), bool(t.group(3))
                else:
                    num = float(_NUM_WORDS[(t.group(4) or t.group(5)).lower()])
                    more = (t.group(6) or "").lower() == "more"
                # "3 times more" is read both ways (3x, or 4x) to stay fair.
                targets = [num, num + 1] if more else [num]
                if not any(abs(x - n) <= 0.5 for x in unit_ratios for n in targets):
                    drift(t.group(0), ratio_claims, ratio_have)
            for h in (_HALF_RE.finditer(prose) if unit_ratios else ()):
                want = 0.5 if _scene_sign(h.group(1)) < 0 else 1.5
                if not any(abs(x - want) <= 0.05 for x in unit_ratios):
                    drift(h.group(0), ratio_claims, ratio_have)
        if pcts:
            pct_claims = [c for c in ratio_claims if c.get("unit") in ("pct", "ratio")]
            have = "change by " + ", ".join(f"{p:+.1f}%" for p in pcts)
            for m in _SCENE_PCT_RE.finditer(prose):
                stated, tol = _stated_change(m)
                if not any(abs(p - stated) <= tol for p in pcts):
                    drift(m.group(0), pct_claims, have)
        if points:
            pp_claims = [c for c in mine if c.get("unit") == "pp"]
            have = "change by " + ", ".join(f"{p:+.1f} points" for p in points)
            for m in _SCENE_POINTS_RE.finditer(prose):
                stated, tol = _stated_change(m)
                if not any(abs(p - stated) <= tol for p in points):
                    drift(m.group(0), pp_claims, have)


def _check_points_claim(r: "Dimension", cid: str, text: str, value: Optional[float]) -> None:
    """A "pp" claim: the text states a change in percentage points."""
    if value is None:
        r.fail(f"Claim {cid!r} has unit 'pp' but no numeric value.")
        return
    for pattern, _ in PHRASE_RULES:
        if pattern.search(text):
            r.fail(f"Claim {cid!r}: '{pattern.pattern}' describes a ratio, but the value is a "
                   "change in percentage points.")
    m = _POINTS_RE.search(text)
    if not m:
        r.note(f"Claim {cid!r} (unit 'pp') states no 'N points' figure to check.")
        return
    direction, stated = m.group(1), float(m.group(2))
    got = value if direction else abs(value)
    if abs(got - _signed(direction, stated)) > PCT_TOLERANCE_PP:
        r.fail(f"Claim {cid!r}: prose says {m.group(0).strip()}, value is "
               f"{value:+.2f} points (tolerance {PCT_TOLERANCE_PP}).")


_OVERDRAW_GEOMETRIES = (None, "rectangle", "area")


def check_vizzu_overdraw(data: dict[str, Any]) -> list[str]:
    """Vizzu frames whose colour series would hide data.

    In Vizzu, `color` alone does not stack or group: with rectangle/area
    geometry every mark starts at zero, so when one x position has several
    colour values the taller mark covers the shorter ones. Flag a frame only
    when the scene's own data proves the overlap (some x key carries more
    than one colour value), so colour-by-category charts stay clean.
    """
    from .schema import vizzu_channel_series
    issues: list[str] = []
    datasets = data.get("datasets") or {}
    for scene in data.get("scenes") or []:
        if scene.get("kind") != "vizzu":
            continue
        rows = datasets.get(scene.get("dataset")) or []
        if not isinstance(rows, list) or not rows:
            continue
        for i, frame in enumerate(scene.get("frames") or []):
            config = (frame or {}).get("config") or {}
            if config.get("geometry") not in _OVERDRAW_GEOMETRIES:
                continue
            ch = config.get("channels") or {}
            if config.get("coordSystem") not in (None, "cartesian"):
                continue
            x_set = set(vizzu_channel_series(ch.get("x")))
            y_set = set(vizzu_channel_series(ch.get("y")))
            color = [c for c in vizzu_channel_series(ch.get("color"))
                     if c not in x_set and c not in y_set]
            if not color:
                continue
            # The categorical axis: x for vertical bars; if x is all measures
            # (horizontal bars) the y dimensions act as the key instead.
            declared = {s.get("name"): s.get("type", "dimension")
                        for s in (scene.get("series") or []) if isinstance(s, dict)}
            if declared:
                key_cols = [c for c in (x_set | y_set) if declared.get(c) == "dimension"]
            else:
                key_cols = [c for c in (x_set | y_set) if isinstance(rows[0].get(c), str)]
            seen: dict[tuple, set] = {}
            for r in rows:
                if not isinstance(r, dict):
                    continue
                k = tuple(r.get(c) for c in sorted(key_cols))
                seen.setdefault(k, set()).add(tuple(r.get(c) for c in color))
            if any(len(v) > 1 for v in seen.values()):
                cname = color[0]
                issues.append(
                    f"Scene {scene.get('id')!r} frame {i + 1}: color {cname!r} is not on the x or "
                    f"y channel, so its {config.get('geometry') or 'rectangle'} marks overdraw "
                    f"each other and smaller {cname!r} values are hidden. Stack it "
                    f"(\"y\": [\"{cname}\", <measure>]) or group it (\"x\": [<dimension>, \"{cname}\"])."
                )
    return issues


def check_editorial(html: str, data: dict[str, Any]) -> Dimension:
    r = Dimension("Editorial integrity")
    # Scan the static HTML and the text the runtime renders from data.json.
    # Not json.dumps(data): that would block a story over text no reader sees
    # (a hidden headline, a claim note, an id).
    sources = [
        _strip_html_for_prose(html),
        _visible_text(data),
    ]
    low = "\n".join(sources).lower()
    for phrase in SLOP_PHRASES:
        if phrase.lower() in low:
            r.fail(f"Slop / placeholder phrase found: {phrase!r}")

    meta = data.get("meta", {})
    if not meta.get("title"):
        r.fail("data.json meta.title is empty.")
    if not meta.get("published"):
        r.note("data.json meta.published is empty — add a publish date.")
    if not meta.get("sources"):
        r.note("data.json meta.sources is empty — add at least one source citation.")

    for s in data.get("scenes", []):
        kind = s.get("kind", "")
        # Bleed and custom scenes are intentionally chrome-free / data-free; skip.
        if kind in ("bleed", "custom"):
            continue
        # Only demand a source_line when the scene actually references data.
        # A `simple` scene with no `dataset` is just typography or commentary —
        # no source needed. The check should fire only when data is present.
        references_data = bool(s.get("dataset")) or bool(s.get("frames"))
        if references_data and not s.get("source_line"):
            r.note(f"Scene {s.get('id', '?')} has no source_line — add one for stories with data.")
        h = s.get("headline", "") if _scene_text_shown(s) else ""
        if re.search(r"\b(analysis|overview|summary|breakdown)\b\s*$", h, re.I):
            r.note(f"Scene {s.get('id', '?')} headline {h!r} reads as a topic, not an insight.")

    # Readability vs. declared audience (English prose only).
    audience = meta.get("audience", "general-public")
    lang = (meta.get("lang") or "en").lower()
    floor = READING_EASE_FLOORS.get(audience)
    if floor is not None and lang.startswith("en"):
        score = flesch_reading_ease(_story_prose(data))
        if score is not None and score < floor:
            r.note(
                f"Readability: Flesch reading ease is {score:.0f}, below the ~{floor:.0f} "
                f"target for audience '{audience}'. Consider shorter sentences and plainer words."
            )

    return r


_VENDORED_SCRIPT = re.compile(r"<script\b[^>]*\bdata-vendored=[^>]*>.*?</script>", re.I | re.S)


def _strip_vendored(html: str) -> str:
    """Drop third-party library blocks inlined by `dstory bundle --vendor`."""
    return _VENDORED_SCRIPT.sub("", html)


def check_static_a11y(html: str, data: dict[str, Any]) -> Dimension:
    r = Dimension("Accessibility & ethics (static)")
    flat = json.dumps(data, ensure_ascii=False)
    for pat, label in PII_PATTERNS:
        if pat.search(flat):
            r.fail(f"data.json contains a {label}; verify this isn't sensitive PII.")

    # Library code inlined by `bundle --vendor` (d3 defines both axisLeft and
    # axisRight, for one) must not trip the author-code heuristics below.
    author = _strip_vendored(html)
    if re.search(r"\baxisRight\b", author) and re.search(r"\baxisLeft\b", author):
        r.note("Markup references both axisLeft and axisRight — dual y-axes are usually a mistake.")
    if re.search(r"\b(three\.js|webgl|3d|rotation: ?'\w*z')", author, re.I):
        r.note("3D / WebGL content detected — make sure no chart uses 3D for value encoding.")

    if not re.search(r"<html\b[^>]*\blang=", html):
        r.note("<html> has no lang attribute — set meta.lang so screen readers pick the right voice.")

    # Chart-bearing scenes should carry an alt text (scene.alt → aria-label).
    # The data panel's table is the other way in; with neither, a screen-reader
    # user gets nothing at all, so that fails.
    # "Table present" is decided by what shipped, not by data.json alone: a
    # bundle made with --no-a11y-extras carries a marker and no panel runtime.
    # (A bundle from a dstory older than 0.11 has neither; it keeps the old
    # note rather than starting to fail.)
    meta_a11y = (data.get("meta") or {}).get("a11y") or {}
    panel_shipped = not re.search(r'<meta\s+name="dstory:a11y-extras"\s+content="off"', html)
    for s in data.get("scenes", []):
        references_data = bool(s.get("dataset")) or bool(s.get("frames"))
        if not references_data or s.get("alt"):
            continue
        scene_a11y = s.get("a11y") or {}
        table = scene_a11y.get("table", meta_a11y.get("table"))
        if s.get("dataset") and (table is False or not panel_shipped):
            why = ("its data table is turned off (a11y.table: false)" if table is False else
                   "the bundle ships no data table (built with --no-a11y-extras / "
                   "a11y_extras=False)")
            r.fail(f"Scene {s.get('id', '?')} has no 'alt' text and {why}, so screen-reader "
                   "users get nothing. Add scene.alt or turn the table back on.")
        else:
            r.note(f"Scene {s.get('id', '?')} has a chart but no 'alt' text — "
                   "screen-reader users get a silent <div>. Add scene.alt.")
            if s.get("dataset") and "__DSTORY_DATA_PANEL__" not in html and table is not False:
                r.note(f"Scene {s.get('id', '?')}: this bundle predates the data panel; "
                       "re-bundle to give it an accessible data table.")
    return r


# ---------- browser-driven checks ----------

BROWSER_AUDIT_JS = r"""
(() => {
  const sceneEls = Array.from(document.querySelectorAll('[data-scene], .scene, .step, section'));
  const sampleSelectors = ['p', 'h1', 'h2', '.commentary'];
  const colorSamples = [];
  for (const sel of sampleSelectors) {
    const el = document.querySelector(sel);
    if (!el) continue;
    const cs = getComputedStyle(el);
    const bg = (() => {
      let n = el;
      while (n && n !== document.body) {
        const c = getComputedStyle(n).backgroundColor;
        if (c && c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent') return c;
        n = n.parentElement;
      }
      return getComputedStyle(document.body).backgroundColor;
    })();
    colorSamples.push({ selector: sel, color: cs.color, background: bg, fontSize: cs.fontSize });
  }
  return {
    sceneCount: sceneEls.length,
    svgCount: document.querySelectorAll('svg').length,
    canvasCount: document.querySelectorAll('canvas').length,
    colorSamples,
    imgsWithoutAlt: Array.from(document.querySelectorAll('img')).filter(i => !i.alt || !i.alt.trim()).length,
    mountsWithoutAria: Array.from(document.querySelectorAll('[data-mount]'))
      .filter(m => !m.getAttribute('aria-label')).length,
  };
})()
"""

# Scenes that carry data (a dataset or Vizzu frames) must paint something in
# their chart mount. Returns the ids of scenes whose mount is still empty:
# no svg with marks, no sized canvas, no image, and no HTML chart either.
PAINT_AUDIT_JS = r"""
(() => {
  const data = window.__STORY_DATA__;
  if (!data || !Array.isArray(data.scenes)) return [];
  const marks = 'path, rect, circle, line, polyline, polygon, ellipse, text, image, use';
  // A canvas counts only if it holds ink: more than 1% of its pixels differ
  // from its dominant (background) colour. A blank Vizzu canvas carries only
  // a tiny watermark, which stays well under that.
  const canvasInked = (c) => {
    if (!(c.width > 0 && c.height > 0)) return false;
    try {
      const W = 120, H = Math.max(1, Math.round(120 * c.height / c.width));
      const o = document.createElement('canvas'); o.width = W; o.height = H;
      const ctx = o.getContext('2d');
      ctx.drawImage(c, 0, 0, W, H);
      const px = ctx.getImageData(0, 0, W, H).data;
      const counts = new Map();
      const keys = new Array(W * H);
      for (let i = 0, j = 0; i < px.length; i += 4, j++) {
        const k = (px[i] >> 4) << 12 | (px[i + 1] >> 4) << 8 | (px[i + 2] >> 4) << 4 | (px[i + 3] >> 4);
        keys[j] = k; counts.set(k, (counts.get(k) || 0) + 1);
      }
      let bg = 0, best = -1;
      for (const [k, n] of counts) if (n > best) { best = n; bg = k; }
      return (keys.length - best) / keys.length > 0.01;
    } catch (e) {
      return true;  // unreadable (tainted / WebGL): can't tell, don't fail it
    }
  };
  const unpainted = [];
  for (const s of data.scenes) {
    if (!s || !s.id) continue;
    const hasData = !!s.dataset || (Array.isArray(s.frames) && s.frames.length > 0);
    if (!hasData) continue;
    const mount = document.querySelector(`[data-mount="${CSS.escape(s.id)}"]`);
    if (!mount) { unpainted.push(s.id); continue; }
    const svgs = Array.from(mount.querySelectorAll('svg'));
    const svgPainted = svgs.some(svg => svg.querySelector(marks));
    const canvases = Array.from(mount.querySelectorAll('canvas'));
    const canvasPainted = canvases.some(canvasInked);
    const imgPainted = !!mount.querySelector('img');
    // An HTML-only chart (no svg or canvas) counts if it built any elements.
    // Mounts start empty (for kind:"custom" the mount is the bare section).
    const htmlPainted = svgs.length === 0 && canvases.length === 0 && mount.children.length > 0;
    if (!(svgPainted || canvasPainted || imgPainted || htmlPainted)) unpainted.push(s.id);
  }
  return unpainted;
})()
"""

# A chart card (.scene__graphic) whose SVG extends past its bottom edge: the
# chart then sits on the source line, under the slide controls, or off-screen.
OVERFLOW_AUDIT_JS = r"""
(() => {
  const out = [];
  for (const g of document.querySelectorAll('.scene__graphic[data-mount]')) {
    const box = g.getBoundingClientRect();
    if (box.height === 0) continue;
    for (const svg of g.querySelectorAll(':scope > svg')) {
      const r = svg.getBoundingClientRect();
      if (r.height > 0 && r.bottom > box.bottom + 2) { out.push(g.getAttribute('data-mount')); break; }
    }
  }
  return out;
})()
"""

# The data panel (bundle a11y extras): every data scene's table and CSV must
# match the inlined dataset, so the numbers a reader can inspect are exactly
# the numbers the author supplied. Returns null when the bundle has no panel
# runtime (bundled by an older dstory, or with --no-a11y-extras).
DATA_TABLE_AUDIT_JS = r"""
(() => {
  const api = window.__DSTORY_DATA_PANEL__, data = window.__STORY_DATA__;
  if (!api || !data || !Array.isArray(data.scenes)) return null;
  const issues = [];
  const norm = t => (t || '').replace(/\s+/g, ' ').trim();
  for (const s of data.scenes) {
    if (!s || !s.id) continue;
    const rows = api.rowsOf(data, s);
    if (!rows) continue;
    const want = api.expected(s);
    if (!want.placed || (!want.table && !want.download)) continue;
    const panel = document.querySelector(`[data-scene-data="${CSS.escape(s.id)}"]`);
    if (!panel) { issues.push(`${s.id}: no Data panel under the chart.`); continue; }
    const cols = api.columnsOf(rows, s);
    if (want.table) {
      const t = panel.querySelector('table');
      if (!t) { issues.push(`${s.id}: the Data panel has no table.`); continue; }
      if (+t.dataset.rows !== rows.length)
        issues.push(`${s.id}: table says ${t.dataset.rows} rows, the dataset has ${rows.length}.`);
      const body = Array.from(t.tBodies[0]?.rows || []);
      if (body.length !== Math.min(rows.length, api.MAX_ROWS))
        issues.push(`${s.id}: table shows ${body.length} rows, expected ${Math.min(rows.length, api.MAX_ROWS)}.`);
      const head = Array.from(t.tHead?.rows[0]?.cells || []).map(c => norm(c.textContent));
      if (head.join('|') !== cols.join('|'))
        issues.push(`${s.id}: table columns ${JSON.stringify(head)} differ from ${JSON.stringify(cols)}.`);
      const check = (i) => {
        const cells = Array.from(body[i]?.cells || []).map(c => norm(c.textContent));
        const exp = (api.cellText ? api.cellText(rows, i, cols, s)
                     : cols.map(c => api.fmt(rows[i] ? rows[i][c] : ''))).map(norm);
        if (cells.join('|') !== exp.join('|'))
          issues.push(`${s.id}: table row ${i + 1} reads ${JSON.stringify(cells)}, the data says ${JSON.stringify(exp)}.`);
      };
      if (body.length) { check(0); check(body.length - 1); }
    }
    if (want.download) {
      const a = panel.querySelector('a[download]');
      if (!a) { issues.push(`${s.id}: no Download CSV link.`); continue; }
      let text = '';
      try { text = decodeURIComponent(a.getAttribute('href').split(',').slice(1).join(',')); }
      catch (e) { issues.push(`${s.id}: the CSV link does not decode.`); continue; }
      const lines = text.replace(/^﻿/, '').split('\r\n');
      if (lines.length !== rows.length + 1)
        issues.push(`${s.id}: the CSV has ${lines.length - 1} rows, the dataset has ${rows.length}.`);
      else if (lines[lines.length - 1] !== api.csvRow(rows[rows.length - 1], cols))
        issues.push(`${s.id}: the CSV's last row differs from the dataset's.`);
    }
  }
  return issues;
})()
"""

# The keyboard explorer: every data chart is focusable and, driven with the
# keys a reader would press, speaks numbers that are in its dataset. Returns
# null when the bundle has no explorer runtime.
EXPLORER_AUDIT_JS = r"""
(() => {
  const ex = window.__DSTORY_EXPLORER__, api = window.__DSTORY_DATA_PANEL__, data = window.__STORY_DATA__;
  if (!ex || !api || !data || !Array.isArray(data.scenes)) return null;
  const live = () => (document.getElementById('dstory-explore-live') || {}).textContent || '';
  const key = (el, k) => el.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true }));
  const issues = [];
  const before = document.activeElement;
  for (const s of data.scenes) {
    if (!s || !s.id || !api.rowsOf(data, s) || !ex.expected(s)) continue;
    const m = document.querySelector(`[data-explore="${CSS.escape(s.id)}"]`);
    if (!m) { issues.push(`${s.id}: the chart cannot be explored with the keyboard.`); continue; }
    if (m.tabIndex !== 0) issues.push(`${s.id}: the chart is not in the tab order.`);
    m.focus({ preventScroll: true });
    if (!live().trim()) issues.push(`${s.id}: focusing the chart announces nothing.`);
    key(m, 'Home');
    const said = live(), want = ex.describe(s.id, 0, 0);
    if (said !== want) issues.push(`${s.id}: Home announces ${JSON.stringify(said)}, expected ${JSON.stringify(want)}.`);
    const rows = api.rowsOf(data, s), roles = ex.rolesOf(rows, api.columnsOf(rows, s), s);
    const g = ex.groupsOf(rows, roles)[0], r0 = rows[g.idx[0]] || {};
    for (const c of roles.measures)
      if (typeof r0[c] === 'number' && !said.includes(api.fmt(r0[c])))
        issues.push(`${s.id}: the first point is read as ${JSON.stringify(said)}, without its ${c} (${api.fmt(r0[c])}).`);
    key(m, 'End');
    if (g.idx.length > 1 && live() === said) issues.push(`${s.id}: End does not move to the last point.`);
    m.blur();
  }
  if (before && before.focus) before.focus({ preventScroll: true });
  return issues;
})()
"""

# "Listen": every chart that can be heard has a button, plays one tone per
# numeric point, and a higher value is never a lower pitch. Returns null when
# the bundle has no sonifier.
LISTEN_AUDIT_JS = r"""
(() => {
  const L = window.__DSTORY_LISTEN__, api = window.__DSTORY_DATA_PANEL__, data = window.__STORY_DATA__;
  if (!L || !api || !data || !Array.isArray(data.scenes)) return null;
  const issues = [];
  for (const s of data.scenes) {
    if (!s || !s.id || !api.rowsOf(data, s) || !L.expected(s)) continue;
    if (s.kind === 'custom' && document.body.classList.contains('story-mode--slides')) continue;
    if (!document.querySelector(`[data-listen="${CSS.escape(s.id)}"]`)) {
      issues.push(`${s.id}: no Listen button under the chart.`); continue;
    }
    const plan = L.plan(s.id);
    const rows = api.rowsOf(data, s);
    const want = rows.filter(r => r && typeof r[plan.measure] === 'number' && isFinite(r[plan.measure])).length;
    const got = plan.series.reduce((n, x) => n + x.notes.length, 0);
    if (got !== want) issues.push(`${s.id}: Listen plays ${got} tones for ${want} values of ${plan.measure}.`);
    const notes = plan.series.flatMap(x => x.notes);
    for (let i = 1; i < notes.length; i++) {
      const a = notes[i - 1], b = notes[i];
      if ((b.value - a.value) * (b.freq - a.freq) < 0) {
        issues.push(`${s.id}: Listen plays a higher value at a lower pitch.`); break;
      }
    }
  }
  return issues;
})()
"""

_EMPTY_DATASET_WARNING = re.compile(r"^\[[\w-]+\] empty dataset")

SLIDES_AUDIT_JS = r"""
(() => {
  if (!document.body.classList.contains('story-mode--slides')) return null;
  const ind = document.querySelector('[data-slide-indicator]');
  return {
    hasIndicator: !!ind,
    indicatorText: ind?.textContent || '',
    hasPrev: !!document.querySelector('[data-slide-prev]'),
    hasNext: !!document.querySelector('[data-slide-next]'),
  };
})()
"""


def run_browser_checks(html_abs: Path, out_dir: Path) -> tuple[Dimension, Dimension, list[str], list[str]]:
    """Returns (renders, visual, dynamic_a11y_issues, dynamic_a11y_notes)."""
    renders = Dimension("Renders correctly")
    visual  = Dimension("Visual quality")
    extras: list[str] = []
    extra_notes: list[str] = []

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        renders.fail("Playwright not installed; run `pip install dstory[vet] && playwright install chromium`.")
        visual.fail("Skipped — Playwright unavailable.")
        return renders, visual, extras, extra_notes

    out_dir.mkdir(parents=True, exist_ok=True)
    viewports = [(1440, 900), (768, 1024), (480, 800)]
    url = "file://" + str(html_abs)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for w, h in viewports:
            ctx  = browser.new_context(viewport={"width": w, "height": h})
            page = ctx.new_page()
            console_errors: list[str] = []
            empty_warnings: list[str] = []

            def on_console(msg, errs=console_errors, empties=empty_warnings):
                if msg.type == "error":
                    errs.append(f"{msg.type}: {msg.text}")
                elif msg.type == "warning" and _EMPTY_DATASET_WARNING.match(msg.text or ""):
                    empties.append(msg.text)

            page.on("pageerror", lambda exc: console_errors.append(f"pageerror: {exc}"))
            page.on("console", on_console)

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=10000)
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception as e:
                renders.fail(f"viewport {w}x{h}: load error — {e}")
                ctx.close(); continue

            try:
                facts = page.evaluate(BROWSER_AUDIT_JS)
            except Exception as e:
                renders.fail(f"viewport {w}x{h}: audit error — {e}")
                ctx.close(); continue

            if console_errors:
                renders.fail(f"viewport {w}x{h}: console errors — {console_errors[:3]}")

            if facts["sceneCount"] == 0:
                renders.fail(f"viewport {w}x{h}: no scenes in DOM.")

            # "Charts paint": every data-bearing scene must draw something.
            # Renderers may be async (Vizzu), so give them a moment first.
            try:
                page.wait_for_function(f"{PAINT_AUDIT_JS.strip()}.length === 0", timeout=4000)
            except Exception:
                pass
            try:
                unpainted = page.evaluate(PAINT_AUDIT_JS)
            except Exception as e:
                unpainted = []
                renders.note(f"viewport {w}x{h}: paint check skipped — {e}")
            if unpainted:
                renders.fail(f"viewport {w}x{h}: chart did not paint in scene(s) "
                             f"{', '.join(unpainted)} — check the dataset columns match the "
                             "renderer (scene.config) and that a renderer is registered.")
            if empty_warnings:
                renders.fail(f"viewport {w}x{h}: recipe reported an empty dataset — {empty_warnings[:3]}")
            try:
                overflowing = page.evaluate(OVERFLOW_AUDIT_JS)
            except Exception:
                overflowing = []
            if overflowing:
                renders.fail(f"viewport {w}x{h}: chart overflows its card in scene(s) "
                             f"{', '.join(overflowing)} — it covers the source line or "
                             "runs off the slide.")
            if facts["svgCount"] == 0 and facts["canvasCount"] == 0:
                renders.note(f"viewport {w}x{h}: no SVG or Canvas charts detected.")

            for s in facts["colorSamples"]:
                fg = _parse_color(s["color"])
                bg = _parse_color(s["background"])
                if not fg or not bg:
                    continue
                ratio = _contrast_ratio(fg, bg)
                size  = float(re.match(r"([\d.]+)", s["fontSize"]).group(1))
                threshold = 3.0 if size >= 18 else 4.5
                if ratio < threshold:
                    extras.append(
                        f"viewport {w}x{h}: {s['selector']} contrast {ratio:.2f} "
                        f"(needs ≥ {threshold:.1f}). color={s['color']} bg={s['background']}"
                    )

            if w == 1440:
                try:
                    table_issues = page.evaluate(DATA_TABLE_AUDIT_JS)
                except Exception as e:
                    table_issues = None
                    extra_notes.append(f"data-table check skipped — {e}")
                for issue in table_issues or []:
                    extras.append(f"Data panel: {issue}")
                try:
                    explorer_issues = page.evaluate(EXPLORER_AUDIT_JS)
                except Exception as e:
                    explorer_issues = None
                    extra_notes.append(f"keyboard-explorer check skipped — {e}")
                for issue in explorer_issues or []:
                    extras.append(f"Chart explorer: {issue}")
                try:
                    listen_issues = page.evaluate(LISTEN_AUDIT_JS)
                except Exception as e:
                    listen_issues = None
                    extra_notes.append(f"Listen check skipped — {e}")
                for issue in listen_issues or []:
                    extras.append(f"Listen: {issue}")

            if facts["imgsWithoutAlt"] > 0:
                extras.append(f"viewport {w}x{h}: {facts['imgsWithoutAlt']} <img> without alt text.")

            if w == 1440 and facts.get("mountsWithoutAria", 0) > 0:
                extra_notes.append(
                    f"{facts['mountsWithoutAria']} chart mount(s) have no aria-label — "
                    "set scene.alt to describe each chart for screen readers."
                )

            # Slides mode keyboard nav check + bonus screenshots
            slide_screenshots: list[tuple[str, str]] = []
            try:
                slides = page.evaluate(SLIDES_AUDIT_JS)
                if slides:
                    if not slides["hasIndicator"]:
                        renders.fail(f"viewport {w}x{h}: slides mode but indicator missing.")
                    if not (slides["hasPrev"] and slides["hasNext"]):
                        renders.fail(f"viewport {w}x{h}: slides mode but prev/next buttons missing.")
                    page.evaluate("document.body.focus()")
                    before = page.evaluate("document.querySelector('[data-slide-indicator]')?.textContent || ''")
                    page.keyboard.press("ArrowRight"); page.wait_for_timeout(700)
                    page.keyboard.press("ArrowRight"); page.wait_for_timeout(700)
                    after = page.evaluate("document.querySelector('[data-slide-indicator]')?.textContent || ''")
                    if before == after:
                        renders.fail(f"viewport {w}x{h}: ArrowRight does not advance "
                                     f"(before={before!r}, after={after!r}).")
                    elif w == 1440:
                        sub = out_dir / f"{w}-slide-mid.png"
                        try:
                            page.screenshot(path=str(sub))
                            slide_screenshots.append((sub.name, after))
                        except Exception:
                            pass
                        for _ in range(4):
                            page.keyboard.press("ArrowRight"); page.wait_for_timeout(550)
                        deeper = page.evaluate("document.querySelector('[data-slide-indicator]')?.textContent || ''")
                        sub2 = out_dir / f"{w}-slide-deep.png"
                        try:
                            page.screenshot(path=str(sub2))
                            slide_screenshots.append((sub2.name, deeper))
                        except Exception:
                            pass
                    page.keyboard.press("ArrowLeft"); page.wait_for_timeout(700)
                    back = page.evaluate("document.querySelector('[data-slide-indicator]')?.textContent || ''")
                    if not slide_screenshots and back == after:
                        renders.fail(f"viewport {w}x{h}: ArrowLeft does not go back "
                                     f"(before={before!r}, after={after!r}, back={back!r}).")
            except Exception as e:
                renders.note(f"viewport {w}x{h}: slides keyboard-nav check skipped — {e}")

            shot = out_dir / f"{w}.png"
            try:
                page.screenshot(path=str(shot), full_page=True)
                rel = shot
                visual.note(f"Screenshot saved: {rel}")
            except Exception as e:
                visual.note(f"Screenshot failed at {w}x{h}: {e}")

            for name, indicator in slide_screenshots:
                visual.note(f"Screenshot saved: {name} (indicator={indicator})")

            ctx.close()
        browser.close()

    return renders, visual, extras, extra_notes


# ---------- top-level API ----------

_BROWSER_STATUS: Optional[tuple[bool, str]] = None


def _off_event_loop(fn, *args, **kwargs):
    """Call fn, in a worker thread if this thread runs an asyncio loop.

    Playwright's sync API refuses to start inside a running event loop, which
    is exactly where Jupyter/IPython cells execute. A plain thread has no loop.
    """
    import asyncio
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return fn(*args, **kwargs)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(fn, *args, **kwargs).result()


def _probe_browser() -> tuple[bool, str]:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return (False, 'Playwright not installed (pip install "dstory[vet]")')
    try:
        with sync_playwright() as p:
            p.chromium.launch().close()
        return (True, "")
    except Exception as e:  # missing Chromium, sandbox restrictions...
        first = (str(e).strip().splitlines() or ["unknown error"])[0]
        return (False, f"Chromium could not start ({first}); run `playwright install chromium`")


def browser_available() -> tuple[bool, str]:
    """(available, reason): can Playwright launch headless Chromium here?

    Cached per process: the first call launches and closes a browser once.
    """
    global _BROWSER_STATUS
    if _BROWSER_STATUS is None:
        _BROWSER_STATUS = _off_event_loop(_probe_browser)
    return _BROWSER_STATUS


def vet(
    html: str | Path,
    *,
    data: str | Path,
    browser: Optional[bool] = True,
    out_dir: Optional[Path] = None,
) -> Report:
    """Vet a bundled story. Returns a typed Report.

    browser: True runs the headless-browser checks (needs the [vet] extra and
    Chromium); False skips them; None runs them when a browser is available
    and skips them otherwise. Skipped dimensions are flagged (`Report.skipped`).
    """
    html_path = Path(html).resolve()
    data_path = Path(data).resolve()
    if not html_path.exists():
        raise FileNotFoundError(f"html not found: {html_path}")
    if not data_path.exists():
        raise FileNotFoundError(f"data.json not found: {data_path}")

    html_text = html_path.read_text(encoding="utf-8")
    data_obj  = json.loads(data_path.read_text(encoding="utf-8"))

    fidelity  = check_data_fidelity(html_text, data_obj)
    for issue in check_vizzu_overdraw(data_obj):
        fidelity.fail(issue)
    editorial = check_editorial(html_text, data_obj)
    a11y      = check_static_a11y(html_text, data_obj)

    skip_reason = "browser=False"
    if browser is None:
        browser, why = browser_available()
        if not browser:
            skip_reason = f"no browser available: {why}"

    if browser:
        # Default screenshots dir: <project>/vetting/screenshots/
        if out_dir is None:
            project = html_path.parent.parent  # .../slug/dist/story.html → .../slug
            out_dir = project / "vetting" / "screenshots"
        renders, visual, dynamic_extras, dynamic_notes = _off_event_loop(
            run_browser_checks, html_path, out_dir)
        for x in dynamic_extras:
            a11y.fail(x)
        for n in dynamic_notes:
            a11y.note(n)
    else:
        renders = Dimension("Renders correctly", skipped=True)
        renders.note(f"Skipped ({skip_reason}). Charts were NOT checked in a browser.")
        visual  = Dimension("Visual quality", skipped=True)
        visual.note(f"Skipped ({skip_reason}).")

    report = Report(
        html_path=str(html_path),
        data_path=str(data_path),
        dimensions=[renders, fidelity, editorial, visual, a11y],
    )

    # Persist alongside screenshots if browser ran
    if browser and out_dir:
        report_path = out_dir.parent / "report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report.to_json(), indent=2), encoding="utf-8")

    return report
