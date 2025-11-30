"""Deploy command for executing Ansible playbooks."""

from pathlib import Path
from typing import Any

import typer

from slipp import output
from slipp.constants import DEFAULT_ENV
from slipp.output import format_path
from slipp.services.ansible import (
    check_roles_installed,
    install_requirements,
    run_playbook,
)
from slipp.services.config import (
    ConfigResolver,
    LocalConfigService,
    PresetResolver,
    parse_preset_args,
    resolve_project_name,
)
from slipp.services.registry import ProjectRegistry
from slipp.services.vault import (
    has_vault_content,
    vault_password_file as get_vault_password_file,
)
from slipp.utils.errors import AnsibleNotFoundError, ConfigParseError


def deploy_command(
    target: str = typer.Argument(
        DEFAULT_ENV,
        help="Environment name or tag preset (preset if it exists, else environment)",
    ),
    preset: str = typer.Argument(
        None, help="Tag preset name (when using 'ac deploy <env> <preset>')"
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
        [], "--roles", help="Role directories to scan (repeatable)"
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
    """Execute ansible-playbook to deploy services."""
    if name and inventory:
        project_root = Path.cwd()
        inventory_path = Path(inventory)

        if not inventory_path.exists():
            output.error(
                f"Inventory file not found: {format_path(inventory_path, project_root)}"
            )
            raise typer.Exit(1)

        try:
            if LocalConfigService.exists(project_root):
                LocalConfigService.update(
                    {"name": name, "inventory": inventory},
                    project_root=project_root,
                )
                output.info(f"Updated slipp.yaml with name '{name}'")
            else:
                LocalConfigService.create(
                    name=name,
                    inventory_path=inventory,
                    playbook_path=playbook or "playbook.yml",
                    roles=roles if roles else None,
                    vault_path=vault,
                    project_root=project_root,
                )
                output.info(f"Created slipp.yaml with name '{name}'")
        except Exception as e:
            output.error(f"Failed to create config: {e}")
            raise typer.Exit(1)

    project_name = resolve_project_name(cli_name=name)

    preset_resolver = PresetResolver()
    presets = preset_resolver.list_presets()

    if preset:
        environment = target
        if preset not in presets:
            output.error(f"Preset '{preset}' not found")
            if presets:
                output.hint(f"Available presets: {', '.join(presets.keys())}")
            raise typer.Exit(1)
        preset_tags, preset_skip_tags = parse_preset_args(presets[preset])
        output.info(f"Using preset '{preset}': {presets[preset]}")
    elif target != DEFAULT_ENV and target in presets:
        environment = DEFAULT_ENV
        preset_tags, preset_skip_tags = parse_preset_args(presets[target])
        output.info(f"Using preset '{target}': {presets[target]}")
    else:
        environment = target
        preset_tags, preset_skip_tags = None, None

    if preset_tags and not tags:
        tags = preset_tags
    if preset_skip_tags and not skip_tags:
        skip_tags = preset_skip_tags

    resolver = ConfigResolver()
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
    roles_paths = [str(r) for r in config.roles]

    project_root = resolver.project_root
    if not inventory and config.inventory_source == "local":
        output.info(
            f"Using inventory from slipp.yaml: {format_path(inventory_file, project_root)}"
        )
    if not playbook and config.playbook_source == "local":
        output.info(
            f"Using playbook from slipp.yaml: {format_path(playbook_file, project_root)}"
        )

    if not Path(inventory_file).exists():
        output.error(
            f"Inventory file not found: {format_path(inventory_file, project_root)}"
        )
        if not resolver.has_local_config:
            output.hint("Run 'ac register <name> -i <inventory>' to configure project")
        raise typer.Exit(1)

    if not Path(playbook_file).exists():
        output.error(
            f"Playbook file not found: {format_path(playbook_file, project_root)}"
        )
        raise typer.Exit(1)

    inventory_dir = Path(inventory_file).parent
    needs_vault_password = has_vault_content(inventory_dir)

    vault_file: str | None = None
    if config.vault:
        vault_path = config.vault
        if vault_path.exists():
            vault_file = str(vault_path)
            needs_vault_password = True
        else:
            output.warning(
                f"Vault file not found: {format_path(vault_path, project_root)}"
            )

    log_dir = output.get_log_dir()
    reqs_file = requirements or "requirements.yml"
    if Path(reqs_file).exists():
        roles_dir = roles_paths[0] if roles_paths else None
        if not roles_dir:
            output.error("--roles required when requirements.yml exists")
            output.hint("Example: ac deploy --roles ./roles")
            raise typer.Exit(1)

        if not force_requirements and check_roles_installed(roles_dir):
            output.info(f"Roles already installed in {roles_dir}")
        else:
            with output.spinner("Installing requirements") as update:
                result = install_requirements(
                    reqs_file,
                    roles_dir,
                    log_dir=log_dir,
                    force=force_requirements,
                    on_progress=update,
                )
            if result.exit_code == 0:
                output.success("Installing requirements")
            else:
                output.error("Installing requirements failed")
                if result.log_path:
                    output.hint(f"See log: {result.log_path}")
                raise typer.Exit(1)

    try:
        with output.spinner("Running playbook", spinner_type="earth") as update:
            if needs_vault_password:
                with get_vault_password_file(confirm=False) as pw_file:
                    result = run_playbook(
                        playbook_file,
                        inventory_file,
                        check=dry_run,
                        vault_file=vault_file,
                        vault_password_file=pw_file,
                        tags=tags,
                        skip_tags=skip_tags,
                        log_dir=log_dir,
                        on_progress=update,
                    )
            else:
                result = run_playbook(
                    playbook_file,
                    inventory_file,
                    check=dry_run,
                    tags=tags,
                    skip_tags=skip_tags,
                    log_dir=log_dir,
                    on_progress=update,
                )
        returncode = result.exit_code
        if returncode != 0:
            output.error("Running playbook failed")
            if result.log_path:
                output.hint(f"See log: {result.log_path}")
    except AnsibleNotFoundError as e:
        output.error(str(e))
        raise typer.Exit(1)

    if returncode == 0:
        output.success_animation("Deploy completed")

        if any([inventory, playbook, roles_list, vault]) and not dry_run and not name:
            changes: dict[str, Any] = {}
            if inventory:
                changes["inventory"] = inventory
            if playbook:
                changes["playbook"] = playbook
            if roles_list:
                changes["roles"] = roles_list
            if vault:
                changes["vault"] = vault

            try:
                LocalConfigService.update(changes)
                output.info("Updated slipp.yaml")
            except ConfigParseError:
                output.warning("Config flags ignored - no slipp.yaml exists")
                output.hint(
                    "Use --name to create config: ac deploy --name <name> -i <inventory>"
                )

        try:
            ProjectRegistry().register(name=project_name, project_path=Path.cwd())
        except Exception:
            pass

        LocalConfigService.ensure_logs_gitignore()
    else:
        output.hint(f"Review log: {format_path(log_dir, project_root)}")
        raise typer.Exit(returncode)
