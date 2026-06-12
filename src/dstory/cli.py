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
from .scaffold import init as scaffold_init
from .vet import vet as vet_story
from . import __version__

console = Console()


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
        console.print(f"[red]✗[/red] {e}")
        sys.exit(1)

    console.print(f"[green]✓[/green] Scaffolded [bold]{dest}[/bold] (theme={brand.name}, audience={audience}, mode={mode})")
    console.print()
    console.print("[dim]Next:[/dim]")
    console.print(f"  1. Populate {dest}/data.json from your raw data")
    console.print(f"  2. Author scenes in {dest}/scenes/ and wire them in {dest}/index.html")
    console.print(f"  3. Bundle:  [cyan]dstory bundle {dest}[/cyan]")
    console.print(f"  4. Vet:     [cyan]dstory vet {dest}/dist/story.html --data {dest}/data.json[/cyan]")


@cli.command()
@click.argument("slug")
@click.option("--no-validate", is_flag=True, help="Skip data.json schema validation before bundling.")
def bundle(slug: str, no_validate: bool) -> None:
    """Bundle SLUG into a single self-contained HTML file."""
    try:
        result = bundle_story(slug, validate=not no_validate)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]✗ Bundle failed:[/red] {e}")
        sys.exit(1)

    console.print(f"[green]✓[/green] Wrote {result.out} ({result.size_bytes/1024:.1f} KB)")
    console.print(f"  inlined: {result.inlined_styles} styles, {result.inlined_scripts} scripts, {result.inlined_images} images")
    for w in result.warnings:
        console.print(f"  [yellow]⚠[/yellow] {w}")


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
        status = "[green]✓[/green]" if d.passed else "[red]✗[/red]"
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
