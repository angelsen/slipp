"""Manage tag presets for Ansible deployments."""

import typer

from slipp import output
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
        output.hint("Run 'ac register' or 'ac launch' first")
        return

    if not presets:
        output.info("No tag presets configured")
        output.hint("Add preset: ac tags add <name> --tags <tag>")
        return

    output.info("Tag presets:")
    rows = [{"name": name, "args": args} for name, args in presets.items()]
    output.table(rows)
    output.blank()
    output.hint("Use: ac deploy <preset> or ac deploy <env> <preset>")


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
    config = LocalConfigService.load()

    if not config:
        output.error("No slipp.yaml found")
        output.hint("Run 'ac register' or 'ac launch' first")
        raise typer.Exit(1)

    if not tags and not skip_tags:
        output.error("Must specify --tags and/or --skip-tags")
        output.hint("Example: ac tags add setup --tags setup-all")
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
        output.text(f"  Was: {old_args}")
        output.text(f"  Now: {args}")
    else:
        output.success(f"Added preset '{name}'")

    config.tag_presets[name] = args
    LocalConfigService.save(config)

    output.hint(f"Use: ac deploy {name}")


@tags_app.command(name="remove")
def remove_preset(
    name: str = typer.Argument(..., help="Preset name to remove"),
) -> None:
    """Remove a tag preset."""
    config = LocalConfigService.load()

    if not config:
        output.error("No slipp.yaml found")
        raise typer.Exit(1)

    if name not in config.tag_presets:
        output.error(f"Preset '{name}' not found")
        if config.tag_presets:
            output.hint(f"Available presets: {', '.join(config.tag_presets.keys())}")
        raise typer.Exit(1)

    del config.tag_presets[name]
    LocalConfigService.save(config)

    output.success(f"Removed preset '{name}'")
