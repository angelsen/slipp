"""Local config persistence for the deploy command."""

from pathlib import Path
from typing import Any

from slipp import output
from slipp.output import format_path
from slipp.services.config import LocalConfigService
from slipp.services.registry import ProjectRegistry
from slipp.utils.errors import ConfigError, ConfigParseError, SlippError


def ensure_local_config(
    name: str,
    inventory: str,
    playbook: str | None,
    roles: list[str],
    vault: str | None,
    project_root: Path,
) -> None:
    """Create or update slipp.yaml when --name and --inventory are both given.

    Args:
        name: Project name.
        inventory: Inventory file path (relative to project_root).
        playbook: Playbook file path, defaults to "playbook.yml".
        roles: Role search directories.
        vault: Vault file path.
        project_root: Project root directory.

    Raises:
        ConfigError: If the inventory file doesn't exist or config creation fails.
    """
    inventory_path = Path(inventory)

    if not inventory_path.exists():
        raise ConfigError(
            f"Inventory file not found: {format_path(inventory_path, project_root)}"
        )

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
                roles_path=roles if roles else None,
                vault_path=vault,
                project_root=project_root,
            )
            output.info(f"Created slipp.yaml with name '{name}'")
    except Exception as e:
        raise ConfigError(f"Failed to create config: {e}") from e


def persist_config_updates(
    inventory: str | None,
    playbook: str | None,
    roles_list: list[str] | None,
    galaxy_path_flag: str | None,
    vault: str | None,
) -> None:
    """Persist CLI flag overrides into slipp.yaml after a successful deploy.

    Args:
        inventory: Inventory path CLI override, if given.
        playbook: Playbook path CLI override, if given.
        roles_list: Role search directories CLI override, if given.
        galaxy_path_flag: Galaxy install path CLI override, if given.
        vault: Vault path CLI override, if given.
    """
    changes: dict[str, Any] = {}
    if inventory:
        changes["inventory"] = inventory
    if playbook:
        changes["playbook"] = playbook
    if roles_list:
        merged_roles = list(roles_list)
        if galaxy_path_flag and galaxy_path_flag not in merged_roles:
            merged_roles.append(galaxy_path_flag)
        changes["roles_path"] = merged_roles
    if galaxy_path_flag:
        changes["galaxy_path"] = galaxy_path_flag
    if vault:
        changes["vault"] = vault

    try:
        LocalConfigService.update(changes)
        output.info("Updated slipp.yaml")
    except ConfigParseError:
        output.warning("Config flags ignored - no slipp.yaml exists")
        output.hint(
            "Use --name to create config: slipp deploy --name <name> -i <inventory>"
        )


def register_project(project_name: str) -> None:
    """Best-effort registration of the current project in the global registry.

    Args:
        project_name: Name to register the project under.
    """
    try:
        ProjectRegistry().register(name=project_name, project_path=Path.cwd())
    except SlippError:
        output.warning("Could not register project in global registry")
