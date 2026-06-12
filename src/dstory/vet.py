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


# ---------- result types ----------

@dataclass
class Dimension:
    name: str
    passed: bool = True
    issues: list[str] = field(default_factory=list)
    notes:  list[str] = field(default_factory=list)

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

    def to_json(self) -> dict[str, Any]:
        return {
            "html_path": self.html_path,
            "data_path": self.data_path,
            "passed": self.passed,
            "dimensions": [
                {"name": d.name, "passed": d.passed, "issues": d.issues, "notes": d.notes}
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

PHRASE_RULES: list[tuple[re.Pattern, callable]] = [
    (re.compile(r"\bdoubled\b", re.I),    lambda v: 1.95 <= v <= 2.10),
    (re.compile(r"\btripled\b", re.I),    lambda v: 2.85 <= v <= 3.15),
    (re.compile(r"\bquadrupled\b", re.I), lambda v: 3.85 <= v <= 4.15),
    (re.compile(r"\bhalved\b", re.I),     lambda v: 0.45 <= v <= 0.55),
    (re.compile(r"\bmajority\b", re.I),   lambda v: v >= 0.50),
]
PCT_TOLERANCE_PP = 0.5

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

    # Combine static HTML prose + data JSON, since dynamic scenes' commentary
    # lives in data.json and is rendered by JS at runtime — invisible to a
    # static HTML scan.
    prose = _strip_html_for_prose(html) + "\n" + json.dumps(data, ensure_ascii=False)
    prose_lower = re.sub(r"\s+", " ", prose.lower())

    for c in claims:
        text  = c.get("text", "")
        value = c.get("value")
        cid   = c.get("id", "?")

        if not text:
            continue

        norm_text = re.sub(r"\s+", " ", text.strip().lower())
        if norm_text and norm_text not in prose_lower:
            r.note(f"Claim {cid!r} text not found verbatim in prose; check chart and prose match.")

        for pattern, predicate in PHRASE_RULES:
            if pattern.search(text):
                if value is None:
                    r.fail(f"Claim {cid!r} uses '{pattern.pattern}' but has no numeric value.")
                elif not predicate(value):
                    r.fail(f"Claim {cid!r}: prose says \"{text}\" but value={value} fails check for "
                           f"'{pattern.pattern}'. Either rephrase or fix the data.")

        m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
        if m and value is not None:
            stated = float(m.group(1))
            actual_pct = value * 100 if 0 <= value <= 1 else value
            if abs(actual_pct - stated) > PCT_TOLERANCE_PP:
                r.fail(f"Claim {cid!r}: prose says {stated}%, derived value is "
                       f"{actual_pct:.2f}% (tolerance {PCT_TOLERANCE_PP}pp).")

    return r


def check_editorial(html: str, data: dict[str, Any]) -> Dimension:
    r = Dimension("Editorial integrity")
    # Scan both static HTML AND the data dict — scenes built dynamically from
    # data.json don't appear in the static HTML body, so we'd miss slop there.
    sources = [
        _strip_html_for_prose(html),
        json.dumps(data, ensure_ascii=False),
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
        h = s.get("headline", "")
        if re.search(r"\b(analysis|overview|summary|breakdown)\b\s*$", h, re.I):
            r.note(f"Scene {s.get('id', '?')} headline {h!r} reads as a topic, not an insight.")

    return r


def check_static_a11y(html: str, data: dict[str, Any]) -> Dimension:
    r = Dimension("Accessibility & ethics (static)")
    flat = json.dumps(data, ensure_ascii=False)
    for pat, label in PII_PATTERNS:
        if pat.search(flat):
            r.fail(f"data.json contains a {label}; verify this isn't sensitive PII.")

    if re.search(r"\baxisRight\b", html) and re.search(r"\baxisLeft\b", html):
        r.note("Markup references both axisLeft and axisRight — dual y-axes are usually a mistake.")
    if re.search(r"\b(three\.js|webgl|3d|rotation: ?'\w*z')", html, re.I):
        r.note("3D / WebGL content detected — make sure no chart uses 3D for value encoding.")
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
  };
})()
"""

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


def run_browser_checks(html_abs: Path, out_dir: Path) -> tuple[Dimension, Dimension, list[str]]:
    """Returns (renders, visual, dynamic_a11y_issues)."""
    renders = Dimension("Renders correctly")
    visual  = Dimension("Visual quality")
    extras: list[str] = []

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        renders.fail("Playwright not installed; run `pip install dstory[vet] && playwright install chromium`.")
        visual.fail("Skipped — Playwright unavailable.")
        return renders, visual, extras

    out_dir.mkdir(parents=True, exist_ok=True)
    viewports = [(1440, 900), (768, 1024), (480, 800)]
    url = "file://" + str(html_abs)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for w, h in viewports:
            ctx  = browser.new_context(viewport={"width": w, "height": h})
            page = ctx.new_page()
            console_errors: list[str] = []
            page.on("pageerror", lambda exc: console_errors.append(f"pageerror: {exc}"))
            page.on("console", lambda msg:
                    console_errors.append(f"{msg.type}: {msg.text}") if msg.type == "error" else None)

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

            if facts["imgsWithoutAlt"] > 0:
                extras.append(f"viewport {w}x{h}: {facts['imgsWithoutAlt']} <img> without alt text.")

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

    return renders, visual, extras


# ---------- top-level API ----------

def vet(
    html: str | Path,
    *,
    data: str | Path,
    browser: bool = True,
    out_dir: Optional[Path] = None,
) -> Report:
    """Vet a bundled story. Returns a typed Report."""
    html_path = Path(html).resolve()
    data_path = Path(data).resolve()
    if not html_path.exists():
        raise FileNotFoundError(f"html not found: {html_path}")
    if not data_path.exists():
        raise FileNotFoundError(f"data.json not found: {data_path}")

    html_text = html_path.read_text(encoding="utf-8")
    data_obj  = json.loads(data_path.read_text(encoding="utf-8"))

    fidelity  = check_data_fidelity(html_text, data_obj)
    editorial = check_editorial(html_text, data_obj)
    a11y      = check_static_a11y(html_text, data_obj)

    if browser:
        # Default screenshots dir: <project>/vetting/screenshots/
        if out_dir is None:
            project = html_path.parent.parent  # .../slug/dist/story.html → .../slug
            out_dir = project / "vetting" / "screenshots"
        renders, visual, dynamic_extras = run_browser_checks(html_path, out_dir)
        for x in dynamic_extras:
            a11y.fail(x)
    else:
        renders = Dimension("Renders correctly"); renders.note("Skipped (browser=False).")
        visual  = Dimension("Visual quality");    visual.note("Skipped (browser=False).")

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
