"""Service for loading and managing Ansible inventory.

This module provides utilities for working with Ansible inventory files,
supporting the standard inventory.yml format used by slipp.
"""

from pathlib import Path

from slipp.models.deployment import InventoryConfig
from slipp.services.ansible import run_inventory
from slipp.utils.errors import InventoryParseError


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
