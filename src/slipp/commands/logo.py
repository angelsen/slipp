"""Logo display and export command."""

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


def logo_command(
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
    font: Annotated[
        str, typer.Option("--font", "-f", help="Figlet font")
    ] = DEFAULT_FONT,
    colors: Annotated[
        str | None,
        typer.Option("--colors", "-c", help="Colors (comma-sep or palette name)"),
    ] = None,
    animate: Annotated[
        bool, typer.Option("--animate", "-a", help="Animate gradient")
    ] = False,
    list_fonts: Annotated[
        bool, typer.Option("--list-fonts", help="List recommended fonts")
    ] = False,
    list_colors: Annotated[
        bool, typer.Option("--list-colors", help="List color palettes")
    ] = False,
    list_themes: Annotated[
        bool, typer.Option("--list-themes", help="List available themes")
    ] = False,
) -> None:
    """Display the slipp ASCII logo with customizable colors, fonts, and themes."""
    if list_fonts:
        output.info("Recommended fonts (use with --font):")
        for font_name in RECOMMENDED_FONTS:
            output.stdout(f"  {font_name}")
        output.hint("Run 'pyfiglet --list_fonts' for all 500+ fonts")
        return

    if list_colors:
        output.info("Color palettes (use with --colors):")
        for name, palette in COLOR_PALETTES.items():
            output.stdout(f"  {name}: {', '.join(palette)}")
        output.hint("Or use custom: --colors '#ff0000,#00ff00'")
        return

    if list_themes:
        output.info("Available themes (use with --theme):")
        for name, values in THEMES.items():
            output.stdout(f"  {name}: {values[0]} ... {values[-1]}")
        return

    if animate and save:
        raise typer.BadParameter("Cannot use --animate with --save")

    if theme and theme not in THEMES and theme != "none":
        raise typer.BadParameter(
            f"Unknown theme: {theme}. Use --list-themes to see available themes"
        )

    effective_theme = theme
    if save and theme is None:
        effective_theme = "starlight"
    elif theme == "none":
        effective_theme = None

    color_list = None
    if colors:
        if colors in COLOR_PALETTES:
            color_list = COLOR_PALETTES[colors]
        else:
            color_list = [c.strip() for c in colors.split(",")]

    show_logo(
        save_path=save,
        font=font,
        colors=color_list,
        animate=animate,
        text=text,
        theme=effective_theme,
    )
