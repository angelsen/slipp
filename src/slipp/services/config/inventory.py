"""Service for loading and managing Ansible inventory.

This module provides utilities for working with Ansible inventory files,
supporting the standard inventory.yml format used by slipp.
"""

from pathlib import Path

from slipp.models.deployment import InventoryConfig
from slipp.services.ansible import run_inventory
from slipp.utils.errors import InventoryParseError


def load_project_hosts(project_path: Path) -> list[dict[str, str | int]]:
    """Load a summarized host list from a project's local config and inventory.

    Best-effort: returns an empty list rather than raising if the project has
    no config, no configured inventory, a missing inventory file, or an
    unparsable one - callers use this for display (project listings) where
    one bad project's inventory shouldn't block the rest.

    Args:
        project_path: Root directory of the project

    Returns:
        List of dicts with inventory_hostname, ansible_host, ansible_user,
        and ansible_port - one per host in the inventory.
    """
    from slipp.services.config.local import LocalConfigService

    local_config = LocalConfigService.load(project_path)
    if not local_config or not local_config.inventory:
        return []

    inventory_path = project_path / local_config.inventory
    if not inventory_path.exists():
        return []

    try:
        inventory_config = InventoryService.parse(inventory_path)
        return [
            {
                "inventory_hostname": hostname,
                "ansible_host": host.ansible_host,
                "ansible_user": host.ansible_user,
                "ansible_port": host.ansible_port,
            }
            for hostname, host in inventory_config.hosts.items()
        ]
    except InventoryParseError:
        # Unparsable inventory shouldn't block displaying the rest
        return []


class InventoryService:
    """Service for loading and managing Ansible inventory.

    Provides static methods for loading inventory from YAML files
    and extracting host configurations.
    """

    @staticmethod
    def parse(inventory_path: Path) -> InventoryConfig:
        """Parse any Ansible inventory format.

        Supports INI, YAML, JSON, and executable scripts.
        Normalizes ansible_ssh_user -> ansible_user.

        Args:
            inventory_path: Path to inventory file

        Returns:
            InventoryConfig

        Raises:
            InventoryParseError: If parsing fails
        """
        if not inventory_path.exists():
            raise InventoryParseError(f"Inventory not found: {inventory_path}")

        try:
            data = run_inventory(inventory_path)
            return InventoryConfig.from_ansible_inventory_json(data)
        except Exception as e:
            raise InventoryParseError(f"Failed to parse {inventory_path}: {e}") from e

    @staticmethod
    def scan_roles_from_directories(
        roles_paths: list[str], project_root: Path
    ) -> list[str]:
        """Scan role directories for role names (faster than ansible-playbook --list-tasks).

        Args:
            roles_paths: List of role directory paths (relative or absolute)
            project_root: Project root for resolving relative paths

        Returns:
            Sorted list of unique role names
        """
        roles: set[str] = set()
        for role_path_str in roles_paths:
            role_path = Path(role_path_str)
            if not role_path.is_absolute():
                role_path = project_root / role_path
            if role_path.exists():
                roles.update(d.name for d in role_path.iterdir() if d.is_dir())
        return sorted(roles)
