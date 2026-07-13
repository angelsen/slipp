"""Generate Dockerfiles from project templates.

Scans projects and generates Dockerfiles without Ansible configuration files.
Supports dry-run mode.
"""

from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import DryRunOption, ProjectDirsOption, resolve_project_dirs
from slipp.models.service import Runtime
from slipp.services.launch import DockerfileContext, run_dockerfile_pipeline


def dockerfile_command(
    project_dirs: ProjectDirsOption = None,
    dry_run: DryRunOption = False,
    container_runtime: Annotated[
        Runtime, typer.Option("--runtime", help="Container runtime: docker, podman")
    ] = Runtime.DOCKER,
) -> None:
    """Generate Dockerfiles for specified projects."""
    dirs, output_dir = resolve_project_dirs(project_dirs)

    context = DockerfileContext(
        output_dir=output_dir,
        dry_run=dry_run,
        project_dirs=dirs,
        container_runtime=container_runtime,
    )

    run_dockerfile_pipeline(context)

    if not dry_run:
        output.success("Dockerfiles generated!")
