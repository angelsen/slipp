"""Scaffold command - create inventory for existing Ansible projects."""

from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.services.launch import ScaffoldContext, run_scaffold_pipeline


def scaffold_command(
    playbook: Annotated[
        Path,
        typer.Option(
            "--playbook",
            "-p",
            help="Playbook file",
            exists=True,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ],
    name: Annotated[
        str | None,
        typer.Option(
            "--name",
            "-n",
            help="Project name (default: playbook's parent directory name)",
        ),
    ] = None,
    inventory: Annotated[
        Path | None,
        typer.Option(
            "--inventory",
            "-i",
            help="Inventory directory (default: inventory/host_vars/<hostname>/)",
            resolve_path=True,
        ),
    ] = None,
    requirements: Annotated[
        Path | None,
        typer.Option(
            "--requirements",
            "-r",
            help="Path to requirements.yml (auto-detected if not specified)",
            resolve_path=True,
        ),
    ] = None,
    roles_path: Annotated[
        str | None,
        typer.Option(
            "--roles-path",
            help="Path to install roles (required if requirements.yml exists)",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Show what would be done without making changes"
        ),
    ] = False,
) -> None:
    """Scaffold inventory for existing Ansible project."""
    output_dir = playbook.parent
    reqs_path = requirements
    if not reqs_path:
        default_reqs = output_dir / "requirements.yml"
        if default_reqs.exists():
            reqs_path = default_reqs

    project_name = name or output_dir.name
    if not name:
        output.info(f"Project name: '{project_name}' (from playbook directory)")

    context = ScaffoldContext(
        output_dir=output_dir,
        environment="production",
        dry_run=dry_run,
        playbook_path=playbook,
        inventory_path=inventory,
        requirements_path=reqs_path,
        roles_path=roles_path,
        project_name=project_name,
    )

    run_scaffold_pipeline(context)
