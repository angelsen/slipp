"""Logo display and export commands (singular = action)."""

from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.services.logo import (
    COLOR_PALETTES,
    DEFAULT_FONT,
    DEFAULT_TEXT,
    RECOMMENDED_FONTS,
    THEMES,
    show_logo,
)

logo_app = typer.Typer(name="logo", help="Display the slipp ASCII logo")


@logo_app.callback(invoke_without_command=True)
def logo_command(
    ctx: typer.Context,
    save: Annotated[
        Path | None, typer.Option("--save", "-s", help="Export to HTML file")
    ] = None,
    theme: Annotated[
        str | None,
        typer.Option(
            "--theme", "-T", help="Color theme (default: starlight when saving)"
        ),
    ] = None,
    text: Annotated[str, typer.Option("--text", "-t", help="Logo text")] = DEFAULT_TEXT,
    font: Annotated[str, typer.Option("--font", help="Figlet font")] = DEFAULT_FONT,
    colors: Annotated[
        str | None,
        typer.Option("--colors", "-c", help="Colors (comma-sep or palette name)"),
    ] = None,
    animate: Annotated[
        bool, typer.Option("--animate", "-a", help="Animate gradient")
    ] = False,
) -> None:
    """Display the slipp ASCII logo with customizable colors, fonts, and themes."""
    if ctx.invoked_subcommand is not None:
        return

    if animate and save:
        output.error("Cannot use --animate with --save")
        raise typer.Exit(1)

    if theme and theme not in THEMES and theme != "none":
        output.error(
            f"Unknown theme: {theme}. Use 'slipp logo themes' to see available themes"
        )
        raise typer.Exit(1)

    show_logo(
        save_path=save,
        font=font,
        colors=colors,
        animate=animate,
        text=text,
        theme=theme,
    )


@logo_app.command(name="fonts")
def fonts_command() -> None:
    """List recommended figlet fonts."""
    output.info("Recommended fonts (use with --font):")
    for font_name in RECOMMENDED_FONTS:
        output.stdout(f"  {font_name}")
    output.hint("Run 'pyfiglet --list_fonts' for all 500+ fonts")


@logo_app.command(name="colors")
def colors_command() -> None:
    """List available color palettes."""
    output.info("Color palettes (use with --colors):")
    for name, palette in COLOR_PALETTES.items():
        output.stdout(f"  {name}: {', '.join(palette)}")
    output.hint("Or use custom: --colors '#ff0000,#00ff00'")


@logo_app.command(name="themes")
def themes_command() -> None:
    """List available themes."""
    output.info("Available themes (use with --theme):")
    for name, values in THEMES.items():
        output.stdout(f"  {name}: {values[0]} ... {values[-1]}")
