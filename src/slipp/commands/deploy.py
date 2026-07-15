"""Execute Ansible playbooks to deploy services and manage infrastructure."""

from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import (
    AskBecomePassOption,
    DryRunOption,
    RuntimeOption,
    run_deploy_or_exit,
    sync_wg_manage_after_deploy,
)
from slipp.constants import DEFAULT_ENV
from slipp.services.config import LocalConfigService, resolve_project_name
from slipp.services.deploy import (
    DeployOverrides,
    ensure_local_config,
    resolve_environment_and_tags,
)


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
            "--name", "-n", help="Project name (creates/updates local config)"
        ),
    ] = None,
    dry_run: DryRunOption = False,
    inventory: Annotated[
        str | None,
        typer.Option("--inventory", "-i", help="Custom inventory file path"),
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
        list[str] | None,
        typer.Option("--roles", help="Role search directories (repeatable)"),
    ] = None,
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
    runtime: RuntimeOption = None,
    ask_become_pass: AskBecomePassOption = False,
) -> None:
    """Execute ansible-playbook to deploy services and manage infrastructure."""
    roles = roles or []
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

    result = run_deploy_or_exit(
        project_root,
        project_name,
        environment,
        resolved_tags,
        resolved_skip_tags,
        overrides=DeployOverrides(
            inventory=inventory,
            playbook=playbook,
            roles=roles if roles else None,
            vault=vault,
            galaxy_path=galaxy_path_flag,
            runtime=runtime,
        ),
        cli_name=name,
        requirements=requirements,
        dry_run=dry_run,
        force_requirements=force_requirements,
        ask_become_pass=ask_become_pass,
    )

    output.success_animation("Deploy completed")

    # dry_run means the playbook ran in ansible --check mode -- nothing on
    # the host actually changed, so a real SSH `service rm` here would apply
    # destructive changes the user explicitly asked to preview rather than
    # perform.
    if not dry_run:
        sync_wg_manage_after_deploy(project_root, project_name)

    if result.app_url:
        output.hint(f"  {result.app_url}")
