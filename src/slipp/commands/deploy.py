"""Execute Ansible playbooks to deploy services and manage infrastructure."""

from pathlib import Path

import typer

from slipp import output
from slipp.constants import DEFAULT_ENV, DEFAULT_GALAXY_PATH
from slipp.output import format_path
from slipp.services.config import (
    ConfigResolver,
    LocalConfigService,
    resolve_project_name,
)
from slipp.services.deploy import (
    ensure_local_config,
    execute_playbook,
    install_galaxy_requirements,
    persist_config_updates,
    register_project,
    resolve_environment_and_tags,
    validate_deploy_files,
)


def deploy_command(
    target: str = typer.Argument(
        DEFAULT_ENV,
        help="Environment name or tag preset (preset if it exists, else environment)",
    ),
    preset: str = typer.Argument(
        None, help="Tag preset name (when using 'slipp deploy <env> <preset>')"
    ),
    name: str = typer.Option(
        None, "-n", "--name", help="Project name (creates/updates local config)"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without making changes"
    ),
    inventory: str = typer.Option(
        None, "-i", "--inventory", help="Custom inventory file path"
    ),
    playbook: str = typer.Option(None, "--playbook", help="Custom playbook file path"),
    vault: str = typer.Option(None, "--vault", help="Path to vault file"),
    requirements: str = typer.Option(
        None,
        "-r",
        "--requirements",
        help="Path to requirements.yml (auto-detected if not specified)",
    ),
    roles: list[str] = typer.Option(
        [], "--roles", help="Role search directories (repeatable)"
    ),
    galaxy_path_flag: str = typer.Option(
        None,
        "--galaxy-path",
        help="Install path for external roles from requirements.yml",
    ),
    force_requirements: bool = typer.Option(
        False,
        "--force-requirements",
        help="Force reinstall roles even if already installed",
    ),
    tags: str = typer.Option(
        None, "--tags", "-t", help="Ansible tags to run (comma-separated)"
    ),
    skip_tags: str = typer.Option(
        None, "--skip-tags", help="Ansible tags to skip (comma-separated)"
    ),
):
    """Execute ansible-playbook to deploy services and manage infrastructure."""
    if name and inventory:
        # Bound to cwd, never a walked root: creates/updates *this* directory's
        # config. The resolve_root() below then finds the file just created
        # here, keeping the rest of deploy self-consistent.
        ensure_local_config(name, inventory, playbook, roles, vault, Path.cwd())

    project_root = LocalConfigService.resolve_root()
    project_name = resolve_project_name(cli_name=name)
    environment, resolved_tags, resolved_skip_tags = resolve_environment_and_tags(
        target, preset, tags, skip_tags
    )

    resolver = ConfigResolver(project_root)
    roles_list = roles if roles else None
    config = resolver.resolve(
        cli_inventory=inventory,
        cli_playbook=playbook,
        cli_roles=roles_list,
        cli_vault=vault,
        environment=environment,
    )

    inventory_file = str(config.inventory)
    playbook_file = str(config.playbook)
    roles_paths = [str(r) for r in config.roles_path]

    galaxy_path = (
        galaxy_path_flag
        or (str(config.galaxy_path) if config.galaxy_path else None)
        or DEFAULT_GALAXY_PATH
    )
    if galaxy_path not in roles_paths:
        roles_paths.append(galaxy_path)

    needs_vault_password, vault_file = validate_deploy_files(
        config, resolver, inventory, playbook
    )

    log_dir = output.get_log_dir(project_root)
    install_galaxy_requirements(requirements, galaxy_path, force_requirements, log_dir)

    result = execute_playbook(
        playbook_file,
        inventory_file,
        dry_run=dry_run,
        vault_file=vault_file,
        needs_vault_password=needs_vault_password,
        tags=resolved_tags,
        skip_tags=resolved_skip_tags,
        roles_paths=roles_paths,
        log_dir=log_dir,
    )

    if result.exit_code == 0 and result.no_hosts_matched:
        output.error(
            "Playbook matched no hosts "
            "(check the playbook's 'hosts:' pattern against your inventory groups)"
        )
        output.hint(f"See log: {format_path(log_dir, resolver.project_root)}")
        raise typer.Exit(1)

    if result.exit_code == 0:
        output.success_animation("Deploy completed")

        if (
            any([inventory, playbook, roles_list, galaxy_path_flag, vault])
            and not dry_run
            and not name
        ):
            persist_config_updates(
                inventory, playbook, roles_list, galaxy_path_flag, vault, project_root
            )

        register_project(project_name, project_root)
        LocalConfigService.ensure_logs_gitignore(project_root)
    else:
        output.hint(f"Review log: {format_path(log_dir, resolver.project_root)}")
        raise typer.Exit(result.exit_code)
