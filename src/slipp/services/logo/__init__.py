"""Logo rendering and HTML export."""

import re
import sys
from pathlib import Path
from typing import TextIO, cast

from rich.console import Console
from rich_pyfiglet import RichFiglet
from rich_pyfiglet.fonts_list import ALL_FONTS

from slipp import output

DEFAULT_FONT: ALL_FONTS = "ansi_shadow"
DEFAULT_TEXT = "SLIPP"

# Position-based theme mapping [brightest → darkest]
THEMES: dict[str, list[str]] = {
    "starlight": [
        "var(--logo-color-1)",
        "var(--logo-color-2)",
        "var(--logo-color-3)",
        "var(--logo-color-4)",
        "var(--logo-color-5)",
        "var(--logo-color-6)",
    ],
}


def apply_theme(html: str, theme: str) -> str:
    """Replace colors in HTML with themed values by position."""
    if theme not in THEMES:
        return html

    color_pattern = r"color: (#[0-9a-fA-F]{6})"
    colors_found = re.findall(color_pattern, html)

    seen: set[str] = set()
    unique_colors: list[str] = []
    for c in colors_found:
        if c.lower() not in seen:
            seen.add(c.lower())
            unique_colors.append(c)

    target_colors = THEMES[theme]
    for i, color in enumerate(unique_colors):
        if i < len(target_colors):
            html = html.replace(color, target_colors[i])

    return html


COLOR_PALETTES = {
    "cyan": ["#00d4ff", "#006688"],
    "sunset": ["#ff9966", "#ff5e62"],
    "fire": ["#ff0844", "#ffb199"],
    "ocean": ["#667eea", "#764ba2"],
    "matrix": ["#00ff41", "#008f11"],
    "gold": ["#f7971e", "#ffd200"],
}

DEFAULT_COLORS = COLOR_PALETTES["cyan"]

RECOMMENDED_FONTS = [
    "slant",
    "ansi_shadow",
    "isometric1",
    "banner",
    "big",
    "block",
    "digital",
    "standard",
]


def show_logo(
    file: TextIO = sys.stderr,
    save_path: Path | None = None,
    font: str = DEFAULT_FONT,
    colors: str | None = None,
    animate: bool = False,
    text: str = DEFAULT_TEXT,
    theme: str | None = None,
) -> None:
    """Render and display the slipp logo to terminal or save as HTML.

    Args:
        file: Output file handle. Defaults to stderr.
        save_path: Optional path to export as HTML file.
        font: Figlet font name. Defaults to "ansi_shadow".
        colors: Palette name (see COLOR_PALETTES) or comma-separated hex
            values. Defaults to the cyan palette.
        animate: If True, animate the gradient effect.
        text: Text to render. Defaults to "SLIPP".
        theme: Color theme name for HTML export. Defaults to "starlight"
            when save_path is set; pass "none" to force no theme.
    """
    from pyfiglet import Figlet

    if save_path and theme is None:
        theme = "starlight"
    elif theme == "none":
        theme = None

    if colors:
        color_list = COLOR_PALETTES.get(colors) or [
            c.strip() for c in colors.split(",")
        ]
    else:
        color_list = DEFAULT_COLORS

    figlet = Figlet(font=font)
    rendered = figlet.renderText(text)
    content_lines = [line for line in rendered.splitlines() if line.strip()]
    content_width = max(len(line) for line in content_lines) + 2
    content_height = len(content_lines)

    if save_path:
        console = Console(
            file=file,
            record=True,
            width=content_width,
            height=content_height,
            force_terminal=True,
        )
    else:
        console = Console(file=file)

    logo = RichFiglet(
        text,
        font=cast(ALL_FONTS, font),
        colors=color_list,
        animation="gradient_down" if animate else None,
        width=content_width if save_path else None,
        remove_blank_lines=bool(save_path),
    )

    console.print(logo)

    if save_path:
        html = console.export_html(
            inline_styles=True,
            code_format=f'<pre class="sl-logo" style="font-size: var(--logo-size, 0.5rem)" aria-label="{text}">{{code}}</pre>',
        )
        if theme:
            html = apply_theme(html, theme)
        save_path.write_text(html)
        output.success(f"Logo saved to {save_path}")


__all__ = [
    "COLOR_PALETTES",
    "DEFAULT_FONT",
    "DEFAULT_TEXT",
    "RECOMMENDED_FONTS",
    "THEMES",
    "show_logo",
]
