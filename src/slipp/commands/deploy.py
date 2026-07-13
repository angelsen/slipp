"""Execute Ansible playbooks to deploy services and manage infrastructure."""

from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import (
    AskBecomePassOption,
    DryRunOption,
    sync_wg_manage_after_deploy,
)
from slipp.constants import DEFAULT_ENV
from slipp.models.service import Runtime
from slipp.output import format_path
from slipp.services.config import LocalConfigService, resolve_project_name
from slipp.services.deploy import (
    ensure_local_config,
    resolve_environment_and_tags,
    run_deploy,
)
from slipp.utils.errors import DeployError


def deploy_command(
    target: Annotated[
        str,
        typer.Argument(
            help="Environment name or tag preset (preset if it exists, else environment)"
        ),
    ] = DEFAULT_ENV,
    preset: Annotated[
        str | None,
        typer.Argument(
            help="Tag preset name (when using 'slipp deploy <env> <preset>')"
        ),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option(
            "-n", "--name", help="Project name (creates/updates local config)"
        ),
    ] = None,
    dry_run: DryRunOption = False,
    inventory: Annotated[
        str | None,
        typer.Option("-i", "--inventory", help="Custom inventory file path"),
    ] = None,
    playbook: Annotated[
        str | None, typer.Option("--playbook", help="Custom playbook file path")
    ] = None,
    vault: Annotated[
        str | None, typer.Option("--vault", help="Path to vault file")
    ] = None,
    requirements: Annotated[
        str | None,
        typer.Option(
            "-r",
            "--requirements",
            help="Path to requirements.yml (auto-detected if not specified)",
        ),
    ] = None,
    roles: Annotated[
        list[str], typer.Option("--roles", help="Role search directories (repeatable)")
    ] = [],
    galaxy_path_flag: Annotated[
        str | None,
        typer.Option(
            "--galaxy-path",
            help="Install path for external roles from requirements.yml",
        ),
    ] = None,
    force_requirements: Annotated[
        bool,
        typer.Option(
            "--force-requirements",
            help="Force reinstall roles even if already installed",
        ),
    ] = False,
    tags: Annotated[
        str | None,
        typer.Option("--tags", "-t", help="Ansible tags to run (comma-separated)"),
    ] = None,
    skip_tags: Annotated[
        str | None,
        typer.Option("--skip-tags", help="Ansible tags to skip (comma-separated)"),
    ] = None,
    runtime: Annotated[
        Runtime | None,
        typer.Option("--runtime", help="How the app runs: systemd, docker, podman"),
    ] = None,
    ask_become_pass: AskBecomePassOption = False,
) -> None:
    """Execute ansible-playbook to deploy services and manage infrastructure."""
    if name and inventory:
        # Bound to cwd, never a walked root: creates/updates *this* directory's
        # config. The resolve_root() below then finds the file just created
        # here, keeping the rest of deploy self-consistent.
        ensure_local_config(
            name,
            inventory,
            playbook,
            roles,
            vault,
            Path.cwd(),
            runtime,
            galaxy_path_flag,
        )

    project_root = LocalConfigService.resolve_root()
    project_name = resolve_project_name(cli_name=name)
    environment, resolved_tags, resolved_skip_tags = resolve_environment_and_tags(
        target, preset, tags, skip_tags
    )

    try:
        result = run_deploy(
            project_root,
            project_name,
            environment,
            resolved_tags,
            resolved_skip_tags,
            cli_name=name,
            cli_inventory=inventory,
            cli_playbook=playbook,
            cli_roles=roles if roles else None,
            cli_vault=vault,
            cli_galaxy_path=galaxy_path_flag,
            requirements=requirements,
            runtime=runtime,
            dry_run=dry_run,
            force_requirements=force_requirements,
            ask_become_pass=ask_become_pass,
        )
    except DeployError as e:
        output.error(str(e))
        if e.log_dir:
            output.hint(f"See log: {format_path(e.log_dir, project_root)}")
        raise typer.Exit(1)

    if result.exit_code != 0:
        output.hint(f"Review log: {format_path(result.log_dir, project_root)}")
        raise typer.Exit(result.exit_code)

    output.success_animation("Deploy completed")

    # dry_run means the playbook ran in ansible --check mode -- nothing on
    # the host actually changed, so a real SSH `service rm` here would apply
    # destructive changes the user explicitly asked to preview rather than
    # perform.
    if not dry_run:
        sync_wg_manage_after_deploy(project_root, project_name)

    if result.app_url:
        output.hint(f"  {result.app_url}")
