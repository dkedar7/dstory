"""dstory CLI — `dstory init/bundle/vet/themes`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .brand import Brand, list_presets
from .bundle import bundle as bundle_story
from .cookbook import list_recipes, recipe_js, recipe_kind
from .scaffold import init as scaffold_init, starter_scene_js, write_scene
from .vet import vet as vet_story
from . import __version__

console = Console()

# Status glyphs degrade to ASCII when stdout can't encode them (e.g. Windows
# consoles on cp1252) — otherwise every success message would crash the CLI.
_UNICODE_OK = "utf" in (getattr(sys.stdout, "encoding", "") or "").lower()
CHECK, CROSS, WARN = ("✓", "✗", "⚠") if _UNICODE_OK else ("OK", "X", "!")


@click.group()
@click.version_option(__version__, prog_name="dstory")
def cli() -> None:
    """dstory — interactive scrollytelling and slide-deck data stories.

    Scaffold a project, bundle to a single HTML, and vet it for delivery.
    """
    pass


@cli.command()
@click.argument("slug")
@click.option("--theme", "-t", default="editorial-noir",
              help="Preset name (e.g., editorial-noir) or path to a brand TOML.")
@click.option("--audience", "-a", default="general-public",
              type=click.Choice(["executive", "general-public", "technical-peer", "student", "policymaker"]))
@click.option("--mode", "-m", default="scroll", type=click.Choice(["scroll", "slides"]))
@click.option("--title", default="Untitled Story", help="Starter title written into data.json's meta.")
@click.option("--overwrite", is_flag=True, help="Allow writing into a non-empty directory.")
def init(slug: str, theme: str, audience: str, mode: str, title: str, overwrite: bool) -> None:
    """Scaffold a new story project at SLUG."""
    # Resolve theme: preset name OR brand TOML file
    if theme.endswith(".toml") or "/" in theme or "\\" in theme:
        brand = Brand.from_toml(theme)
        console.print(f"[dim]Brand loaded from TOML:[/dim] {brand.name}")
    else:
        if theme not in list_presets():
            console.print(f"[red]Unknown preset:[/red] {theme}")
            console.print(f"Available: {', '.join(list_presets())}")
            sys.exit(2)
        brand = Brand.from_preset(theme)

    try:
        dest = scaffold_init(slug, brand=brand, audience=audience, mode=mode,
                             title=title, overwrite=overwrite)
    except FileExistsError as e:
        console.print(f"[red]{CROSS}[/red] {e}")
        sys.exit(1)

    console.print(f"[green]{CHECK}[/green] Scaffolded [bold]{dest}[/bold] (theme={brand.name}, audience={audience}, mode={mode})")
    console.print()
    console.print("[dim]Next:[/dim]")
    console.print(f"  1. Populate {dest}/data.json from your raw data")
    console.print(f"  2. Author scenes in {dest}/scenes/ and wire them in {dest}/index.html")
    console.print(f"  3. Bundle:  [cyan]dstory bundle {dest}[/cyan]")
    console.print(f"  4. Vet:     [cyan]dstory vet {dest}/dist/story.html --data {dest}/data.json[/cyan]")


@cli.command()
@click.argument("slug")
@click.option("--no-validate", is_flag=True, help="Skip data.json schema validation before bundling.")
@click.option("--vendor", is_flag=True,
              help="Inline the CDN runtime libs (d3, scrollama, Motion) so the "
                   "story works fully offline. Needs network now; adds ~300 KB.")
def bundle(slug: str, no_validate: bool, vendor: bool) -> None:
    """Bundle SLUG into a single self-contained HTML file."""
    try:
        result = bundle_story(slug, validate=not no_validate, vendor=vendor)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]{CROSS} Bundle failed:[/red] {e}")
        sys.exit(1)

    console.print(f"[green]{CHECK}[/green] Wrote {result.out} ({result.size_bytes/1024:.1f} KB)")
    console.print(f"  inlined: {result.inlined_styles} styles, {result.inlined_scripts} scripts, {result.inlined_images} images")
    for w in result.warnings:
        console.print(f"  [yellow]{WARN}[/yellow] {w}")


@cli.command()
@click.argument("html_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--data", "data_path", required=True, type=click.Path(exists=True, dir_okay=False),
              help="Path to data.json")
@click.option("--no-browser", is_flag=True,
              help="Skip browser-driven checks (renders, screenshots, dynamic a11y).")
def vet(html_path: str, data_path: str, no_browser: bool) -> None:
    """Vet a bundled HTML against the 5-dimension rubric."""
    report = vet_story(html_path, data=data_path, browser=not no_browser)

    table = Table(title=f"Vetting Report — {Path(html_path).name}", show_header=True)
    table.add_column("Dimension")
    table.add_column("Status")
    table.add_column("Issues / Notes")

    for d in report.dimensions:
        status = f"[green]{CHECK}[/green]" if d.passed else f"[red]{CROSS}[/red]"
        details: list[str] = []
        for i in d.issues:
            details.append(f"[red]- {i}[/red]")
        for n in d.notes[:3]:
            details.append(f"· {n}")
        if len(d.notes) > 3:
            details.append(f"· ...and {len(d.notes) - 3} more")
        table.add_row(d.name, status, "\n".join(details) or "—")

    console.print(table)
    if report.passed:
        console.print("[green bold]OVERALL: PASS[/green bold] — safe to deliver.")
    else:
        console.print("[red bold]OVERALL: BLOCKED[/red bold] — fix the issues above.")
        sys.exit(1)


@cli.command()
@click.argument("slug", type=click.Path(exists=True, file_okay=False))
@click.argument("scene_id")
@click.option("--kind", "-k", default="simple",
              type=click.Choice(["simple", "scrolly", "pinned", "bleed", "custom", "vizzu"]))
@click.option("--from", "-f", "recipe",
              help="Start from a cookbook recipe instead of a blank stub "
                   "(see `dstory recipes`). Overrides --kind.")
def scene(slug: str, scene_id: str, kind: str, recipe: str | None) -> None:
    """Write a scene script at SLUG/scenes/SCENE_ID.js and wire it.

    By default writes a blank stub with the correct renderer contract for
    --kind (scrolly returns onStep, pinned returns onProgress, ...). With
    --from, copies a complete cookbook recipe — a finished, themed chart you
    then own and edit.
    """
    try:
        if recipe:
            js, kind = recipe_js(recipe, scene_id), recipe_kind(recipe)
        else:
            js = starter_scene_js(scene_id, kind)
        target = write_scene(slug, scene_id, js)
    except (FileNotFoundError, KeyError, ValueError) as e:
        console.print(f"[red]{CROSS}[/red] {e}")
        sys.exit(1)
    src_desc = f"recipe={recipe}, kind={kind}" if recipe else f"kind={kind}"
    console.print(f"[green]{CHECK}[/green] Wrote [bold]{target}[/bold] ({src_desc}) and wired it in index.html")
    console.print(f'[dim]Next:[/dim] add {{"id": "{scene_id}", "kind": "{kind}", ...}} to scenes[] in {slug}/data.json')
    if recipe:
        console.print(f"[dim]The recipe header in {target} documents its dataset columns and config options.[/dim]")


@cli.command()
def recipes() -> None:
    """List the cookbook recipes available for `dstory scene --from`."""
    table = Table(title="dstory cookbook")
    table.add_column("Recipe")
    table.add_column("Kind")
    table.add_column("Summary")
    for r in list_recipes():
        table.add_row(r.name, r.kind, r.summary)
    console.print(table)
    console.print("[dim]Use:[/dim] dstory scene <slug> <scene-id> --from <recipe>")


@cli.command()
@click.argument("slug", type=click.Path(exists=True, file_okay=False))
@click.option("--port", "-p", default=8000, help="Port to serve on.")
@click.option("--no-open", is_flag=True, help="Don't open a browser automatically.")
def preview(slug: str, port: int, no_open: bool) -> None:
    """Serve SLUG locally for development.

    Dev mode (unbundled index.html) fetches data.json, which browsers block
    under file:// — so previewing an unbundled project needs a local server.
    Ctrl+C to stop.
    """
    import http.server
    import functools
    import webbrowser

    directory = str(Path(slug).resolve())
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    url = f"http://127.0.0.1:{port}/"
    try:
        with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
            console.print(f"[green]{CHECK}[/green] Serving [bold]{slug}[/bold] at {url} — Ctrl+C to stop")
            if not no_open:
                webbrowser.open(url)
            httpd.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")
    except OSError as e:
        console.print(f"[red]{CROSS}[/red] Could not bind port {port}: {e} (try --port)")
        sys.exit(1)


@cli.command()
def themes() -> None:
    """List the bundled theme presets."""
    table = Table(title="dstory presets")
    table.add_column("Name")
    table.add_column("Accent")
    table.add_column("Description")
    for name in list_presets():
        b = Brand.from_preset(name)
        accent = b.colors.get("accent", "")
        desc = b.config.get("brand", {}).get("description", "")
        table.add_row(name, f"[on {accent}]   [/]  {accent}", desc)
    console.print(table)


if __name__ == "__main__":
    cli()
