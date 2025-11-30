"""Generate Dockerfiles from project templates.

Scans projects and generates Dockerfiles without Ansible configuration files.
Supports dry-run mode and reverse proxy configuration.
"""

from pathlib import Path

import typer

from slipp import output
from slipp.commands.launch.context import DockerfileContext
from slipp.commands.launch.pipeline import LaunchPipeline
from slipp.commands.launch.stages import (
    DockerfileGenerationStage,
    ProjectScanStage,
    ValidationStage,
)
from slipp.generator import TemplateGenerator


def dockerfile_command(
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
    proxy: str = typer.Option(
        "caddy",
        "--proxy",
        help="Reverse proxy: caddy, none",
    ),
) -> None:
    """Generate Dockerfiles for specified projects."""
    dirs = project_dirs if project_dirs else [Path.cwd()]
    output_dir = Path.cwd() if len(dirs) > 1 else dirs[0]

    context = DockerfileContext(
        output_dir=output_dir,
        environment="production",
        dry_run=dry_run,
        project_dirs=dirs,
        proxy=proxy,
    )

    stages = [
        ValidationStage(),
        ProjectScanStage(),
        DockerfileGenerationStage(TemplateGenerator()),
    ]

    try:
        LaunchPipeline(stages).execute(context)
        if not dry_run:
            output.success("Dockerfiles generated!")
    except Exception as e:
        output.error(f"Dockerfile generation failed: {e}")
        raise typer.Exit(1)
