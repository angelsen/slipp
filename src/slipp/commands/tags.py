"""Manage tag presets for Ansible deployments."""

import typer

from slipp import output
from slipp.constants import OutputFormat
from slipp.services.config import LocalConfigService, PresetResolver


tags_app = typer.Typer(
    name="tags",
    help="Manage tag presets for deployments",
)


@tags_app.command(name="list")
def list_presets() -> None:
    """List all tag presets."""
    resolver = PresetResolver()
    presets = resolver.list_presets()

    if not resolver.config:
        output.warning("No slipp.yaml found")
        output.hint("Run 'slipp projects add' or 'slipp launch' first")
        return

    if not presets:
        output.info("No tag presets configured")
        output.hint("Add preset: slipp tags add <name> --tags <tag>")
        return

    rows = [{"name": name, "args": args} for name, args in presets.items()]

    if output.get_output_format() != OutputFormat.json:
        output.info("Tag presets:")

    output.table(rows)

    if output.get_output_format() != OutputFormat.json:
        output.blank()
        output.hint("Use: slipp deploy <preset> or slipp deploy <env> <preset>")


@tags_app.command(name="add")
def add_preset(
    name: str = typer.Argument(..., help="Preset name (e.g., setup, install)"),
    tags: str = typer.Option(
        None, "--tags", "-t", help="Ansible tags to run (comma-separated)"
    ),
    skip_tags: str = typer.Option(
        None, "--skip-tags", help="Ansible tags to skip (comma-separated)"
    ),
) -> None:
    """Add or update a tag preset."""
    root = LocalConfigService.resolve_root()
    config = LocalConfigService.load(root)

    if not config:
        output.error("No slipp.yaml found")
        output.hint("Run 'slipp projects add' or 'slipp launch' first")
        raise typer.Exit(1)

    if not tags and not skip_tags:
        output.error("Must specify --tags and/or --skip-tags")
        output.hint("Example: slipp tags add setup --tags setup-all")
        raise typer.Exit(1)

    parts = []
    if tags:
        parts.append(f"--tags {tags}")
    if skip_tags:
        parts.append(f"--skip-tags {skip_tags}")
    args = " ".join(parts)

    if name in config.tag_presets:
        old_args = config.tag_presets[name]
        output.warning(f"Updating preset '{name}'")
        output.info(f"  Was: {old_args}")
        output.info(f"  Now: {args}")
    else:
        output.success(f"Added preset '{name}'")

    config.tag_presets[name] = args
    LocalConfigService.save(config, root)

    output.hint(f"Use: slipp deploy {name}")


@tags_app.command(name="remove")
def remove_preset(
    name: str = typer.Argument(..., help="Preset name to remove"),
) -> None:
    """Remove a tag preset."""
    root = LocalConfigService.resolve_root()
    config = LocalConfigService.load(root)

    if not config:
        output.error("No slipp.yaml found")
        raise typer.Exit(1)

    if name not in config.tag_presets:
        output.error(f"Preset '{name}' not found")
        if config.tag_presets:
            output.hint(f"Available presets: {', '.join(config.tag_presets.keys())}")
        raise typer.Exit(1)

    del config.tag_presets[name]
    LocalConfigService.save(config, root)

    output.success(f"Removed preset '{name}'")
