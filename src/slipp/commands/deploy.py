"""Execute Ansible playbooks to deploy services and manage infrastructure."""

from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import (
    DryRunOption,
    resolve_declared_dirs,
    resolve_project_dirs,
)
from slipp.constants import DEFAULT_ENV, DEFAULT_GALAXY_PATH
from slipp.output import format_path
from slipp.services import wg_manage
from slipp.services.config import (
    ConfigResolver,
    LocalConfigService,
    load_first_host,
    resolve_app_domain,
    resolve_app_port,
    resolve_project_name,
)
from slipp.services.deploy import (
    ensure_local_config,
    ensure_project_registered,
    execute_playbook,
    install_galaxy_requirements,
    persist_config_updates,
    resolve_environment_and_tags,
    validate_deploy_files,
)
from slipp.utils.errors import WgManageError
from slipp.utils.files import get_log_dir
from slipp.utils.network import format_app_url


def _sync_wg_manage_after_deploy(project_root: Path, project_name: str) -> None:
    """Best-effort post-deploy wg-manage exposure converge.

    Removes stray wg-manage services this project labeled but no longer
    declares (renamed/removed services since the last deploy), so a live
    exposure never silently outlives the service it pointed at. No-op for
    non-wg-manage projects.

    Never raises: a sync hiccup here shouldn't retroactively turn an
    already-successful deploy into a failed one, it just means one fewer
    thing got tidied up this run -- `slipp resources sync` remains
    available to run by hand. wg_manage.sync() converts every internal
    failure mode (SSH, scanning, missing config) to WgManageError, so
    catching that one type here is actually exhaustive, unlike catching
    typer.Exit (a CLI-layer concept the service doesn't raise at all).
    """
    host = load_first_host(project_root)
    if not host or host.proxy_owner != "wg-manage":
        return

    dirs, _ = resolve_project_dirs(
        resolve_declared_dirs(project_root), root=project_root, quiet=True
    )
    local_config = LocalConfigService.load(project_root)
    try:
        wg_manage.sync(
            dirs,
            project_name,
            host,
            expose=local_config.expose if local_config else None,
            quiet=True,
        )
    except WgManageError as e:
        output.warning(f"wg-manage exposure sync failed after deploy: {e}")


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
    ask_become_pass: Annotated[
        bool,
        typer.Option(
            "--ask-become-pass",
            help="Prompt for the sudo/become password (target host has no passwordless sudo)",
        ),
    ] = False,
) -> None:
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

    log_dir = get_log_dir(project_root)
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
        ask_become_pass=ask_become_pass,
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

        # dry_run means the playbook ran in ansible --check mode -- nothing
        # on the host actually changed, so a real SSH `service rm` here
        # would apply destructive changes the user explicitly asked to
        # preview rather than perform.
        if not dry_run:
            _sync_wg_manage_after_deploy(project_root, project_name)

        domain = resolve_app_domain(project_root)
        if domain:
            has_caddy = (project_root / "roles" / "caddy").exists()
            port = resolve_app_port(project_root)
            output.hint(f"  {format_app_url(domain, has_caddy=has_caddy, port=port)}")

        if (
            any([inventory, playbook, roles_list, galaxy_path_flag, vault])
            and not dry_run
            and not name
        ):
            persist_config_updates(
                inventory, playbook, roles_list, galaxy_path_flag, vault, project_root
            )

        ensure_project_registered(project_name, project_root)
        LocalConfigService.ensure_logs_gitignore(project_root)
    else:
        output.hint(f"Review log: {format_path(log_dir, resolver.project_root)}")
        raise typer.Exit(result.exit_code)
