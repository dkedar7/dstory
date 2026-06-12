"""Brand — load a TOML brand/theme file, extend a preset, emit theme.css.

Brands let consumers fit dstory to their visual system without forking the
package. A brand is a TOML file (or Python object) defining color tokens,
typography, motion personality, atmosphere, and chart palette. The same
8 presets we ship are themselves brand TOML files.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore


PACKAGE_THEMES = "dstory.themes"


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    """Recursive dict merge. `over` wins on conflict; lists are replaced wholesale."""
    out = dict(base)
    for k, v in over.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_preset(name: str) -> dict[str, Any]:
    """Load one of the bundled preset TOMLs by name (e.g., 'editorial-noir')."""
    try:
        text = resources.files(PACKAGE_THEMES).joinpath(f"{name}.toml").read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Theme preset {name!r} not found. Available: {list_presets()}"
        ) from e
    return tomllib.loads(text)


def list_presets() -> list[str]:
    """List the bundled theme preset names."""
    files = resources.files(PACKAGE_THEMES).iterdir()
    return sorted(p.name.removesuffix(".toml") for p in files if p.name.endswith(".toml"))


@dataclass
class Brand:
    """A resolved brand, ready to emit CSS or be passed to scaffold/bundle.

    Construct via `Brand.from_preset("editorial-noir")` or
    `Brand.from_toml("./acme.toml")`. Use `.css()` to get the theme.css string.
    """
    config: dict[str, Any]
    name: str = ""
    fonts_dir: Optional[Path] = None  # local fonts to inline at bundle time
    extra_css: Optional[Path] = None  # last-mile override CSS to append
    wordmark: Optional[Path] = None   # SVG/PNG to inline on hero/outro
    favicon: Optional[Path] = None

    @classmethod
    def from_preset(cls, name: str) -> "Brand":
        cfg = _load_preset(name)
        brand_meta = cfg.get("brand", {})
        return cls(config=cfg, name=brand_meta.get("name", name))

    @classmethod
    def from_toml(cls, path: str | Path) -> "Brand":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Brand TOML not found: {path}")
        raw = tomllib.loads(path.read_text(encoding="utf-8"))

        # If `brand.extends` is set, deep-merge with that preset.
        extends = raw.get("brand", {}).get("extends")
        if extends:
            base = _load_preset(extends)
            cfg = _deep_merge(base, raw)
            # Don't carry the 'extends' chain forward in the resolved brand.
            cfg.get("brand", {}).pop("extends", None)
        else:
            cfg = raw

        brand_meta = cfg.get("brand", {})
        # Resolve relative file paths against the TOML's directory.
        def _resolve(p: Optional[str]) -> Optional[Path]:
            if not p: return None
            pp = Path(p)
            return pp if pp.is_absolute() else (path.parent / pp).resolve()

        return cls(
            config    = cfg,
            name      = brand_meta.get("name", path.stem),
            fonts_dir = _resolve(brand_meta.get("fonts_dir") or cfg.get("typography", {}).get("fonts_dir")),
            extra_css = _resolve(cfg.get("escape", {}).get("extra_css")),
            wordmark  = _resolve(cfg.get("brand_marks", {}).get("wordmark")),
            favicon   = _resolve(cfg.get("brand_marks", {}).get("favicon")),
        )

    def extend(self, **overrides: Any) -> "Brand":
        """Return a new Brand with overrides merged on top.

        Overrides are flat keyword args mapped to top-level sections by convention:
        `accent="#FF6B35"` → colors.accent
        `display="GT America"` → typography.display
        For nested control, pass `colors={...}`, `typography={...}` etc.
        """
        SECTION_FOR_KEY = {
            # colors
            **{k: "colors" for k in (
                "bg","bg_elev","bg_deep","ink","ink_soft","ink_faint","ink_invert",
                "accent","accent_2","alert","rule","frame")},
            # typography
            **{k: "typography" for k in ("display","body","mono","google_fonts","fonts_dir")},
            # atmosphere
            **{k: "atmosphere" for k in ("grain_opacity","vignette_strength","noise_mix")},
            # motion
            **{k: "motion" for k in ("base_ms","hero_ms","easing_in","easing_out")},
        }
        patch: dict[str, Any] = {}
        for k, v in overrides.items():
            if k in ("colors", "typography", "atmosphere", "motion", "brand"):
                patch[k] = v
            elif k in SECTION_FOR_KEY:
                patch.setdefault(SECTION_FOR_KEY[k], {})[k] = v
            else:
                # Last-resort: drop into top-level
                patch[k] = v
        merged = _deep_merge(self.config, patch)
        return Brand(
            config=merged, name=self.name,
            fonts_dir=self.fonts_dir, extra_css=self.extra_css,
            wordmark=self.wordmark, favicon=self.favicon,
        )

    # ---------- accessors ----------

    @property
    def colors(self) -> dict[str, Any]:    return self.config.get("colors", {})
    @property
    def typography(self) -> dict[str, Any]: return self.config.get("typography", {})
    @property
    def motion(self) -> dict[str, Any]:    return self.config.get("motion", {})
    @property
    def atmosphere(self) -> dict[str, Any]: return self.config.get("atmosphere", {})

    def google_fonts_url(self) -> Optional[str]:
        families = self.typography.get("google_fonts")
        if not families:
            return None
        joined = "&".join(f"family={f}" for f in families)
        return f"https://fonts.googleapis.com/css2?{joined}&display=swap"

    # ---------- CSS emission ----------

    def css(self) -> str:
        """Render the theme.css contents from this brand's tokens."""
        c   = self.colors
        cat = (c.get("categorical") or {}).get("palette", [])
        seq = c.get("ramp_sequential") or {}
        div = c.get("ramp_diverging") or {}
        t   = self.typography
        m   = self.motion
        a   = self.atmosphere

        def get(d: dict, key: str, default: str = "") -> str:
            return str(d.get(key, default))

        cat_lines = "\n".join(
            f"  --cat-{i+1}: {col};"
            for i, col in enumerate(cat[:7])
        )

        return f"""/* Generated by dstory.Brand({self.name!r}). Do not edit by hand —
   regenerate from the brand TOML via `dstory init` or `Brand(...).css()`. */
:root {{
  /* Surfaces */
  --bg:         {get(c, 'bg')};
  --bg-elev:    {get(c, 'bg_elev')};
  --bg-deep:    {get(c, 'bg_deep')};

  /* Ink */
  --ink:        {get(c, 'ink')};
  --ink-soft:   {get(c, 'ink_soft')};
  --ink-faint:  {get(c, 'ink_faint')};
  --ink-invert: {get(c, 'ink_invert')};

  /* Brand */
  --accent:     {get(c, 'accent')};
  --accent-2:   {get(c, 'accent_2')};
  --alert:      {get(c, 'alert')};

  /* Categorical palette */
{cat_lines}

  /* Sequential ramp */
  --ramp-low:   {get(seq, 'low')};
  --ramp-high:  {get(seq, 'high')};

  /* Diverging ramp */
  --ramp-neg:   {get(div, 'neg')};
  --ramp-mid:   {get(div, 'mid')};
  --ramp-pos:   {get(div, 'pos')};

  /* Lines */
  --rule:       {get(c, 'rule')};
  --frame:      {get(c, 'frame')};

  /* Typography */
  --font-display: {get(t, 'display')};
  --font-body:    {get(t, 'body')};
  --font-mono:    {get(t, 'mono')};

  /* Type scale */
  --step--1: clamp(0.875rem, 0.85rem + 0.125vw, 0.95rem);
  --step-0:  clamp(1rem,    0.95rem + 0.25vw,  1.125rem);
  --step-1:  clamp(1.25rem, 1.15rem + 0.5vw,   1.5rem);
  --step-2:  clamp(1.75rem, 1.5rem + 1vw,      2.5rem);
  --step-3:  clamp(2.5rem,  2rem + 2vw,        4rem);
  --step-4:  clamp(3.5rem,  2.5rem + 4vw,      6rem);

  /* Motion */
  --motion-base: {m.get('base_ms', 450)}ms;
  --motion-hero: {m.get('hero_ms', 1200)}ms;
  --easing-out:  {get(m, 'easing_out', 'cubic-bezier(0.22, 1, 0.36, 1)')};
  --easing-in:   {get(m, 'easing_in',  'cubic-bezier(0.55, 0, 0.7, 0.5)')};

  /* Atmosphere */
  --grain-opacity:     {a.get('grain_opacity', 0.0)};
  --vignette-strength: {a.get('vignette_strength', 0.0)};
  --noise-mix:         {a.get('noise_mix', 0.0)};
}}
"""

    def __repr__(self) -> str:
        return f"Brand(name={self.name!r}, accent={self.colors.get('accent')!r})"
