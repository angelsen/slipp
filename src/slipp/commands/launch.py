"""Launch command - generate Ansible deployment configurations."""

from pathlib import Path
from typing import Annotated

import typer

from slipp.commands.common import DryRunOption, resolve_project_dirs
from slipp.constants import DEFAULT_ENV
from slipp.services.launch import FullContext, run_full_pipeline


def launch_command(
    name: Annotated[
        str,
        typer.Option("--name", "-n", help="Project name (required)"),
    ],
    environment: Annotated[
        str,
        typer.Option(
            "--env", "-e", help="Environment (production, dev, staging, etc.)"
        ),
    ] = DEFAULT_ENV,
    project_dirs: Annotated[
        list[Path] | None,
        typer.Option(
            "--dir",
            "-d",
            help="Directories to scan (default: current directory)",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = None,
    dry_run: DryRunOption = False,
    reconfigure: Annotated[
        bool,
        typer.Option(
            "--reconfigure",
            help="Prompt for inventory config even if inventory.yml exists",
        ),
    ] = False,
    proxy: Annotated[
        str, typer.Option("--proxy", help="Reverse proxy: caddy, none")
    ] = "caddy",
) -> None:
    """Generate complete Ansible project from codebase."""
    dirs, output_dir = resolve_project_dirs(project_dirs)

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
