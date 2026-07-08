"""Generate Dockerfiles from project templates.

Scans projects and generates Dockerfiles without Ansible configuration files.
Supports dry-run mode and reverse proxy configuration.
"""

from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import DryRunOption
from slipp.models.service import Runtime
from slipp.services.launch import DockerfileContext, run_dockerfile_pipeline


def dockerfile_command(
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
    proxy: Annotated[
        str, typer.Option("--proxy", help="Reverse proxy: caddy, none")
    ] = "caddy",
    container_runtime: Annotated[
        str, typer.Option("--runtime", help="Container runtime: docker, podman")
    ] = Runtime.DOCKER.value,
) -> None:
    """Generate Dockerfiles for specified projects."""
    dirs = project_dirs if project_dirs else [Path.cwd()]
    output_dir = Path.cwd() if len(dirs) > 1 else dirs[0]

    context = DockerfileContext(
        output_dir=output_dir,
        dry_run=dry_run,
        project_dirs=dirs,
        proxy=proxy,
        container_runtime=container_runtime,
    )

    run_dockerfile_pipeline(context)

    if not dry_run:
        output.success("Dockerfiles generated!")
