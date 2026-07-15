"""Show a tag preset's Ansible configuration."""

from typing import Annotated

import typer

from slipp import output
from slipp.services.config import PresetResolver, parse_preset_args


def tag_command(
    preset: Annotated[str | None, typer.Argument(help="Preset name to show")] = None,
) -> None:
    """Show a tag preset's configuration."""
    if not preset:
        output.info("No preset specified")
        output.hint("Use 'slipp tags list' to see available presets")
        output.hint("Use 'slipp tag <preset>' to show a preset's tags")
        return

    available = PresetResolver().list_presets()

    if preset not in available:
        output.error(f"Preset '{preset}' not found")
        if available:
            output.hint(f"Available presets: {', '.join(available.keys())}")
        raise typer.Exit(1)

    args = available[preset]
    tags, skip_tags = parse_preset_args(args)
    output.info(f"Preset '{preset}':")
    output.stdout(f"  {args}")
    output.blank()

    if tags:
        output.stdout(f"  --tags: {tags}")
    if skip_tags:
        output.stdout(f"  --skip-tags: {skip_tags}")

    output.blank()
    output.hint(f"Use: slipp deploy {preset}")
