"""Launch command - generate Ansible deployment configurations."""

from pathlib import Path

import typer

from slipp.constants import DEFAULT_ENV
from slipp.services.launch import FullContext, run_full_pipeline


def launch_command(
    name: str = typer.Option(
        ...,
        "--name",
        "-n",
        help="Project name (required)",
    ),
    environment: str = typer.Option(
        DEFAULT_ENV,
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
    dirs = project_dirs if project_dirs else [Path.cwd()]
    output_dir = Path.cwd() if len(dirs) > 1 else dirs[0]

    context = FullContext(
        output_dir=output_dir,
        environment=environment,
        dry_run=dry_run,
        project_dirs=dirs,
        reconfigure=reconfigure,
        proxy=proxy,
        project_name=name,
    )

    run_full_pipeline(context)


__all__ = ["launch_command"]
