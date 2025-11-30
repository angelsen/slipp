"""Launch command - generate Ansible deployment configurations."""

from pathlib import Path

import typer

from slipp import output
from slipp.constants import DEFAULT_ENV
from slipp.generator import TemplateGenerator
from slipp.generator.inventory_generator import InventoryGenerator
from slipp.generator.playbook_generator import PlaybookGenerator

from .context import FullContext
from .pipeline import LaunchPipeline
from .stages import (
    AppRolesStage,
    CaddyConfigStage,
    CaddyRoleStage,
    ComposeGenerationStage,
    DockerfileGenerationStage,
    GroupVarsStage,
    InventoryFileStage,
    InventoryLoadStage,
    InventoryValidationStage,
    PlaybookGenerationStage,
    ProjectScanStage,
    RegistrationStage,
    SummaryStage,
    ValidationStage,
)


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

    stages = [
        ValidationStage(),
        ProjectScanStage(),
        InventoryLoadStage(),
        InventoryValidationStage(),
        DockerfileGenerationStage(TemplateGenerator()),
        CaddyConfigStage(),
        InventoryFileStage(InventoryGenerator()),
        PlaybookGenerationStage(PlaybookGenerator()),
        GroupVarsStage(),
        CaddyRoleStage(),
        AppRolesStage(),
        ComposeGenerationStage(),
        RegistrationStage(),
        SummaryStage(),
    ]

    try:
        LaunchPipeline(stages).execute(context)
    except Exception as e:
        output.error(f"Launch failed: {e}")
        raise typer.Exit(1)


__all__ = ["launch_command"]
