"""Launch command - generate Ansible deployment configurations."""

from typing import Annotated

import typer

from slipp.commands.common import DryRunOption, ProjectDirsOption, resolve_project_dirs
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
    project_dirs: ProjectDirsOption = None,
    dry_run: DryRunOption = False,
    reconfigure: Annotated[
        bool,
        typer.Option(
            "--reconfigure",
            help="Prompt for inventory config even if inventory.yml exists",
        ),
    ] = False,
    proxy: Annotated[
        str,
        typer.Option(
            "--proxy",
            help="Reverse proxy: auto (probe host), caddy, none, wg-manage",
        ),
    ] = "auto",
    public: Annotated[
        bool,
        typer.Option(
            "--public",
            help="Expose via Let's Encrypt instead of internal CA (--proxy wg-manage only)",
        ),
    ] = False,
    python_extra: Annotated[
        str | None,
        typer.Option(
            "--python-extra", help="uv sync --extra group (Python systemd deploys)"
        ),
    ] = None,
    exec_args: Annotated[
        str | None,
        typer.Option(
            "--exec-args", help="Extra ExecStart arguments (Python systemd deploys)"
        ),
    ] = None,
    health_check: Annotated[
        str | None,
        typer.Option(
            "--health-check",
            help="HTTP path polled after restart; rolls back on failure (systemd deploys)",
        ),
    ] = None,
) -> None:
    """Generate complete Ansible project from codebase."""
    dirs, output_dir = resolve_project_dirs(project_dirs)

    if health_check and not health_check.startswith("/"):
        raise typer.BadParameter(
            f"--health-check must start with '/', got '{health_check}'"
        )

    context = FullContext(
        output_dir=output_dir,
        environment=environment,
        dry_run=dry_run,
        project_dirs=dirs,
        reconfigure=reconfigure,
        proxy=proxy,
        public=public,
        project_name=name,
        python_extra=python_extra,
        exec_args=exec_args,
        health_check=health_check,
    )

    run_full_pipeline(context)
