"""Scaffold command - create inventory for existing Ansible projects."""

from pathlib import Path

import typer

from slipp.services.launch import ScaffoldContext, run_scaffold_pipeline


def scaffold_command(
    playbook: Path = typer.Option(
        ...,
        "--playbook",
        "-p",
        help="Playbook file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
    inventory: Path = typer.Option(
        None,
        "--inventory",
        "-i",
        help="Inventory directory (default: inventory/host_vars/<hostname>/)",
        resolve_path=True,
    ),
    requirements: Path = typer.Option(
        None,
        "--requirements",
        "-r",
        help="Path to requirements.yml (auto-detected if not specified)",
        resolve_path=True,
    ),
    roles_path: str = typer.Option(
        None,
        "--roles-path",
        help="Path to install roles (required if requirements.yml exists)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be done without making changes",
    ),
) -> None:
    """Scaffold inventory for existing Ansible project."""
    output_dir = playbook.parent
    reqs_path = requirements
    if not reqs_path:
        default_reqs = output_dir / "requirements.yml"
        if default_reqs.exists():
            reqs_path = default_reqs

    context = ScaffoldContext(
        output_dir=output_dir,
        environment="production",
        dry_run=dry_run,
        playbook_path=playbook,
        inventory_path=inventory,
        requirements_path=reqs_path,
        roles_path=roles_path,
    )

    run_scaffold_pipeline(context)
