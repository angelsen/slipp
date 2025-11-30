"""Service for loading and managing Ansible inventory.

This module provides utilities for working with Ansible inventory files,
supporting the standard inventory.yml format used by slipp.
"""

from pathlib import Path
from typing import Any

import yaml

from slipp.constants import DEFAULT_ENV, get_inventory_filename
from slipp.models.deployment import DeploymentHostConfig, InventoryConfig
from slipp.models.host import AnsibleHost
from slipp.services.ansible import run_inventory, run_list_tasks
from slipp.utils.errors import InventoryParseError


class InventoryService:
    """Service for loading and managing Ansible inventory.

    Provides static methods for loading inventory from YAML files
    and extracting host configurations.
    """

    @staticmethod
    def load(
        environment: str = DEFAULT_ENV, inventory_path: Path | None = None
    ) -> InventoryConfig:
        """Load inventory from YAML file.

        Args:
            environment: Environment name (production, dev, staging, etc.)
            inventory_path: Optional override path. If None, uses get_inventory_filename(environment)

        Returns:
            InventoryConfig instance parsed from file

        Raises:
            FileNotFoundError: If inventory file does not exist
            yaml.YAMLError: If inventory file is not valid YAML
        """
        if inventory_path is None:
            inventory_path = Path(get_inventory_filename(environment))

        if not inventory_path.exists():
            raise FileNotFoundError(
                f"Inventory file not found: {inventory_path}\n"
                f"Run 'slipp launch {environment}' to generate inventory."
            )

        with open(inventory_path) as f:
            data = yaml.safe_load(f)

        return InventoryConfig.from_ansible_format(data)

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
    def build(hosts: dict[str, dict[str, Any]]) -> InventoryConfig:
        """Build InventoryConfig programmatically.

        Used by scaffold and launch stages that generate inventory.

        Args:
            hosts: Dict of hostname -> host config dict
                   Keys: ansible_host, ansible_user, ansible_port, app_domain, admin_email, etc.

        Returns:
            InventoryConfig

        Example:
            config = InventoryService.build({
                "server.example.com": {
                    "ansible_host": "1.2.3.4",
                    "ansible_user": "slipp",
                }
            })
        """
        host_configs = {}
        for hostname, config in hosts.items():
            host_configs[hostname] = DeploymentHostConfig(
                name=hostname,
                inventory_hostname=hostname,
                ansible_host=config.get("ansible_host", hostname),
                ansible_user=config.get("ansible_user", "root"),
                ansible_port=config.get("ansible_port", 22),
                app_domain=config.get("app_domain"),
                admin_email=config.get("admin_email"),
            )
        return InventoryConfig(hosts=host_configs)

    @staticmethod
    def parse_playbook_roles(
        playbook_path: Path, inventory_path: Path | None = None
    ) -> list[str]:
        """Extract role names from playbook using ansible-playbook --list-tasks.

        Args:
            playbook_path: Path to playbook.yml
            inventory_path: Optional inventory file (needed for variable resolution)

        Returns:
            List of unique role names (e.g., ['caddy', 'app-backend', 'app-frontend'])

        Raises:
            FileNotFoundError: If playbook file doesn't exist
            RuntimeError: If ansible-playbook command fails
        """
        if not playbook_path.exists():
            raise FileNotFoundError(f"Playbook not found: {playbook_path}")

        stdout = run_list_tasks(playbook_path, inventory_path)
        return InventoryService._parse_role_names(stdout)

    @staticmethod
    def _parse_role_names(output: str) -> list[str]:
        """Parse role names from --list-tasks output.

        Output format:
            role-name : Task name    TAGS: [...]
            galaxy/role-name : Task name    TAGS: [...]
            custom/role-name : Task name    TAGS: [...]

        Returns:
            Deduplicated list of role names (prefixes stripped)
        """
        roles: set[str] = set()
        for line in output.splitlines():
            line = line.strip()
            if " : " in line:
                role_part = line.split(" : ")[0].strip()
                if "/" in role_part:
                    role_part = role_part.split("/")[-1]
                roles.add(role_part)
        return sorted(roles)

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

    @staticmethod
    def get_first_host(inventory: InventoryConfig) -> DeploymentHostConfig:
        """Get first host from inventory (for single-host deployments).

        Args:
            inventory: InventoryConfig instance

        Returns:
            First DeploymentHostConfig from inventory

        Raises:
            ValueError: If no hosts defined in inventory
        """
        if not inventory.hosts:
            raise ValueError("No hosts defined in inventory")

        return list(inventory.hosts.values())[0]

    @staticmethod
    def _try_local_inventory(environment: str) -> AnsibleHost | None:
        """Try to load host config from local inventory file.

        Args:
            environment: Environment name (production, dev, staging, etc.)

        Returns:
            AnsibleHost instance if found, None otherwise
        """
        inventory_path = Path(get_inventory_filename(environment))
        if inventory_path.exists():
            inventory = InventoryService.load(environment, inventory_path)
            deployment_config = InventoryService.get_first_host(inventory)
            return AnsibleHost.model_validate(deployment_config.model_dump())
        return None

    @staticmethod
    def _parse_service_identifier(service: str) -> tuple[str, str | None, str | None]:
        """Parse service identifier into components.

        Supports syntax:
        - "service" → (service, None, None)
        - "service@host" → (service, host, None)
        - "project:service" → (service, None, project)

        Args:
            service: Service identifier string

        Returns:
            Tuple of (service_name, host_filter, project_filter)
        """
        host_filter = None
        project_filter = None
        service_name = service

        if "@" in service:
            service_name, host_filter = service.split("@", 1)
        elif ":" in service:
            project_filter, service_name = service.split(":", 1)

        return service_name, host_filter, project_filter

    @staticmethod
    def _try_service_index(service: str) -> AnsibleHost | None:
        """Try to lookup service in global service index.

        Args:
            service: Service identifier (supports: "service", "service@host", "project:service")

        Returns:
            AnsibleHost instance if found, None otherwise

        Raises:
            ValueError: If service lookup is ambiguous
        """
        from slipp.services.discovery import ServiceRegistry

        service_name, host_filter, project_filter = (
            InventoryService._parse_service_identifier(service)
        )

        service_registry = ServiceRegistry()
        return service_registry.lookup_host_by_service(
            service_name, host=host_filter, project=project_filter
        )

    @staticmethod
    def _try_project_registry(project: str) -> AnsibleHost | None:
        """Try to lookup project in global registry and load hosts from config.

        Args:
            project: Project name

        Returns:
            AnsibleHost instance (first host) if found, None otherwise
        """
        from slipp.services.config.local import LocalConfigService
        from slipp.services.registry import ProjectRegistry

        project_obj = ProjectRegistry().get(project)
        if not project_obj:
            return None

        local_config = LocalConfigService.load(project_obj.project_path)
        if not local_config:
            return None

        inventory_path = project_obj.project_path / local_config.inventory
        if not inventory_path.exists():
            return None

        try:
            inventory_config = InventoryService.parse(inventory_path)
            if inventory_config.hosts:
                first_host = next(iter(inventory_config.hosts.values()))
                return AnsibleHost(
                    inventory_hostname=next(iter(inventory_config.hosts.keys())),
                    ansible_host=first_host.ansible_host,
                    ansible_user=first_host.ansible_user,
                    ansible_port=first_host.ansible_port,
                    key_file=first_host.key_file,
                )
        except Exception:
            return None

        return None

    @staticmethod
    def _try_current_directory() -> AnsibleHost | None:
        """Try to load host from current directory's local config.

        Returns:
            AnsibleHost instance (first host) if found, None otherwise
        """
        from slipp.services.config.local import LocalConfigService

        local_config = LocalConfigService.load()
        if not local_config:
            return None

        inventory_path = Path.cwd() / local_config.inventory
        if not inventory_path.exists():
            return None

        try:
            inventory_config = InventoryService.parse(inventory_path)
            if inventory_config.hosts:
                first_host = next(iter(inventory_config.hosts.values()))
                return AnsibleHost(
                    inventory_hostname=next(iter(inventory_config.hosts.keys())),
                    ansible_host=first_host.ansible_host,
                    ansible_user=first_host.ansible_user,
                    ansible_port=first_host.ansible_port,
                    key_file=first_host.key_file,
                )
        except Exception:
            return None

        return None

    @staticmethod
    def _build_not_found_error(
        environment: str,
        service: str | None,
        project: str | None,
    ) -> str:
        """Build user-friendly error message for not found case.

        Args:
            environment: Environment name
            service: Service identifier (if provided)
            project: Project name (if provided)

        Returns:
            Formatted error message
        """
        inventory_file = get_inventory_filename(environment)
        project_name = Path.cwd().name

        context_parts = []
        if service:
            context_parts.append(f"service: {service}")
        if project:
            context_parts.append(f"project: {project}")
        context_parts.append(f"cwd: {project_name}")
        context = ", ".join(context_parts)

        return (
            f"No configuration found ({context}, env: {environment}).\n"
            f"Either:\n"
            f"  - cd to project directory with {inventory_file}\n"
            f"  - Run 'slipp deploy {environment}' to register project globally\n"
            f"  - Use valid service name or --project flag"
        )

    @staticmethod
    def get_host_config_with_fallback(
        environment: str = DEFAULT_ENV,
        service: str | None = None,
        project: str | None = None,
    ) -> AnsibleHost:
        """Get host config from local inventory, service index, project, or global registry.

        Fallback chain:
        1. ./inventory[-environment].yml (local project, environment-specific)
        2. Global service index (if service provided, supports syntax: service, service@host, project:service)
        3. Project registry (if project provided)
        4. Global registry (by current directory name)
        5. Error (not found)

        Args:
            environment: Environment name (production, dev, staging, etc.)
            service: Optional service identifier (supports: "service", "service@host", "project:service")
            project: Optional project name for direct project lookup

        Returns:
            AnsibleHost instance (base SSH connection info)

        Raises:
            FileNotFoundError: If no configuration found
            ValueError: If service lookup is ambiguous
        """
        host_config = InventoryService._try_local_inventory(environment)
        if host_config:
            return host_config

        if service:
            host_config = InventoryService._try_service_index(service)
            if host_config:
                return host_config

        if project:
            host_config = InventoryService._try_project_registry(project)
            if host_config:
                return host_config

        host_config = InventoryService._try_current_directory()
        if host_config:
            return host_config

        error_msg = InventoryService._build_not_found_error(
            environment, service, project
        )
        raise FileNotFoundError(error_msg)
