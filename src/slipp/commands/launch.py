"""Launch command - generate Ansible deployment configurations."""

from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import DryRunOption
from slipp.constants import DEFAULT_ENV
from slipp.scanner.workspaces import detect_workspace_members
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
    if project_dirs:
        dirs = project_dirs
    else:
        cwd = Path.cwd()
        members = detect_workspace_members(cwd)
        if members:
            output.info(f"Detected workspace: {len(members)} member(s)")
            dirs = [cwd, *members]
        else:
            dirs = [cwd]
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
