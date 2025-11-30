"""Full command - generate complete Ansible project from codebase."""

from pathlib import Path

import typer

from slipp.commands.launch import launch_command as _launch_command


def full_command(
    name: str = typer.Option(
        ...,
        "--name",
        "-n",
        help="Project name (required)",
    ),
    environment: str = typer.Option(
        "production",
        "--env",
        "-e",
        help="Environment (production, dev, staging, etc.)",
    ),
    project_dirs: list[Path] = typer.Option(
        None,
        "--dir",
        "-d",
        help="Directories to scan (default: current directory)",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be done without making changes",
    ),
    reconfigure: bool = typer.Option(
        False,
        "--reconfigure",
        help="Prompt for inventory config even if inventory.yml exists",
    ),
    proxy: str = typer.Option(
        "caddy",
        "--proxy",
        help="Reverse proxy: caddy, none",
    ),
) -> None:
    """Generate complete Ansible project from codebase."""
    _launch_command(
        name=name,
        environment=environment,
        project_dirs=project_dirs,
        dry_run=dry_run,
        reconfigure=reconfigure,
        proxy=proxy,
    )
