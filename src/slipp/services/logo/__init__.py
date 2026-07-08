"""Logo rendering and HTML export."""

import sys
from pathlib import Path
from typing import TextIO, cast

from rich.console import Console
from rich_pyfiglet import RichFiglet
from rich_pyfiglet.fonts_list import ALL_FONTS

from slipp import output

DEFAULT_COLORS = ["#00d4ff", "#006688"]
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
    "template": [
        "${color_0}",
        "${color_1}",
        "${color_2}",
        "${color_3}",
        "${color_4}",
        "${color_5}",
    ],
}


def apply_theme(html: str, theme: str) -> str:
    """Replace colors in HTML with themed values by position."""
    import re

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
    colors: list[str] | None = None,
    animate: bool = False,
    text: str = DEFAULT_TEXT,
    theme: str | None = None,
) -> None:
    """Render and display the slipp logo to terminal or save as HTML.

    Args:
        file: Output file handle. Defaults to stderr.
        save_path: Optional path to export as HTML file.
        font: Figlet font name. Defaults to "ansi_shadow".
        colors: List of hex colors for gradient. Defaults to cyan palette.
        animate: If True, animate the gradient effect.
        text: Text to render. Defaults to "SLIPP".
        theme: Optional color theme name for HTML export.
    """
    from pyfiglet import Figlet

    color_list = colors or DEFAULT_COLORS

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
    "DEFAULT_COLORS",
    "DEFAULT_FONT",
    "DEFAULT_TEXT",
    "RECOMMENDED_FONTS",
    "THEMES",
    "apply_theme",
    "show_logo",
]
