"""Service for loading and managing Ansible inventory.

This module provides utilities for working with Ansible inventory files,
supporting the standard inventory.yml format used by slipp.
"""

from pathlib import Path

import yaml

from slipp.models.deployment import DeploymentHostConfig, InventoryConfig
from slipp.models.host import AnsibleHost
from slipp.services.ansible import run_inventory
from slipp.utils.errors import ConfigError, HostNotFoundError, InventoryParseError


def _load_first_host_raw(project_root: Path) -> DeploymentHostConfig:
    """Load the first host from the raw inventory YAML.

    Reads the inventory file directly (not via ansible-inventory, which
    drops slipp-specific fields like app_domain/app_port/proxy_owner).
    Shared core for load_first_host() (which converts failures to None)
    and load_first_host_strict() (which adds the app_domain requirement).

    Raises:
        ConfigError: If no inventory/host is configured.
    """
    # Must stay lazy: local.py top-imports this module (see
    # load_project_ansible_hosts).
    from slipp.services.config.local import LocalConfigService

    local_config = LocalConfigService.load(project_root)
    if not local_config or not local_config.inventory:
        raise ConfigError(f"No inventory configured in {project_root}")

    inventory_path = project_root / local_config.inventory
    if not inventory_path.exists():
        raise ConfigError(f"Inventory not found: {inventory_path}")

    data = yaml.safe_load(inventory_path.read_text()) or {}
    inventory = InventoryConfig.from_ansible_format(data)

    if not inventory.hosts:
        raise ConfigError(f"No hosts found in inventory: {inventory_path}")

    return inventory.first_host


def load_first_host(project_root: Path) -> DeploymentHostConfig | None:
    """Best-effort load of the first host from the raw inventory YAML.

    Returns None if anything is missing or unparseable. Public (not just
    this module's resolve_app_domain/resolve_app_port):
    commands/resources.py and commands/deploy.py's post-deploy hook use it
    directly to peek at proxy_owner and get full SSH connection details in
    one read, without duplicating the from_ansible_format() plumbing.
    """
    try:
        return _load_first_host_raw(project_root)
    except Exception:
        return None


def load_first_host_strict(project_root: Path) -> tuple[str, DeploymentHostConfig]:
    """Load the first host from the raw inventory YAML, requiring app_domain.

    The strict counterpart to load_first_host() for commands that converge
    external routing (dns sync, resources sync) and need a definite
    domain + address rather than a best-effort peek. Returns the validated
    app_domain separately (as str, not str | None) alongside the host.

    Raises:
        ConfigError: If no inventory/host/app_domain is configured.
    """
    host = _load_first_host_raw(project_root)
    if not host.app_domain:
        raise ConfigError(
            f"No app_domain configured on inventory host '{host.inventory_hostname}'"
        )

    return host.app_domain, host


def write_minimal_inventory(path: Path, environment: str, ip: str) -> None:
    """Write a minimal single-host inventory YAML for a freshly provisioned VPS.

    Uses the bootstrap defaults (slipp user, port 22); app_domain/app_port
    are left for the user to configure afterwards.
    """
    host_config = DeploymentHostConfig(
        inventory_hostname=environment,
        ansible_host=ip,
        ansible_user="slipp",
        ansible_port=22,
    )
    inventory = InventoryConfig(hosts={environment: host_config})
    path.write_text(yaml.dump(inventory.to_ansible_format(), default_flow_style=False))


def resolve_app_domain(project_root: Path) -> str | None:
    """Best-effort extraction of app_domain from the raw inventory YAML."""
    host = load_first_host(project_root)
    return host.app_domain if host else None


def resolve_app_port(project_root: Path) -> int | None:
    """Best-effort extraction of app_port from the raw inventory YAML.

    Only meaningful for --proxy none deploys (see DeploymentHostConfig.app_port) -
    a Caddy-fronted deploy's domain already implies the right port (:80/:443),
    so callers should check for a caddy role before using this.
    """
    host = load_first_host(project_root)
    return host.app_port if host else None


def load_project_ansible_hosts(project_path: Path) -> list[AnsibleHost]:
    """Load hosts from a project's local config and inventory.

    Args:
        project_path: Path to project directory

    Returns:
        List of AnsibleHost from inventory

    Raises:
        HostNotFoundError: If config or inventory invalid
    """
    # Must stay lazy: local.py top-imports this module (InventoryService), so
    # a top-level import here would be a mutual from-import cycle.
    from slipp.services.config.local import LocalConfigService

    local_config = LocalConfigService.load(project_path)
    if not local_config:
        raise HostNotFoundError(f"No slipp.yaml found in {project_path}")
    if not local_config.inventory:
        raise HostNotFoundError(f"No inventory configured in {project_path}")

    inventory_path = project_path / local_config.inventory
    if not inventory_path.exists():
        raise HostNotFoundError(f"Inventory not found: {inventory_path}")

    try:
        inventory_config = InventoryService.parse(inventory_path)
    except Exception as e:
        raise HostNotFoundError(f"Failed to parse inventory: {e}")

    hosts = [
        AnsibleHost(
            inventory_hostname=hostname,
            ansible_host=host.ansible_host,
            ansible_user=host.ansible_user,
            ansible_port=host.ansible_port,
            key_file=host.key_file,
        )
        for hostname, host in inventory_config.hosts.items()
    ]

    if not hosts:
        raise HostNotFoundError(f"No hosts found in inventory: {inventory_path}")

    return hosts


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
    try:
        hosts = load_project_ansible_hosts(project_path)
    except HostNotFoundError:
        return []

    return [
        {
            "inventory_hostname": host.inventory_hostname,
            "ansible_host": host.ansible_host,
            "ansible_user": host.ansible_user,
            "ansible_port": host.ansible_port,
        }
        for host in hosts
    ]


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
