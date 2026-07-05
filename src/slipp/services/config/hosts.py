"""Unified host resolution for all commands.

This module provides a single source of truth for resolving hosts from:
- Service names (via ServiceRegistry)
- Project names (via ProjectRegistry → local config → inventory)
- Current working directory context

Hosts are parsed on-demand from inventory files, not stored in the registry.
"""

from pathlib import Path

from slipp.models.host import AnsibleHost
from slipp.utils.errors import HostNotFoundError
from slipp.utils.identifiers import parse_service_identifier


class HostResolver:
    """Unified host resolution for all commands.

    Provides methods for different resolution strategies:
    - all_hosts(): All registered hosts (for ps)
    - by_service(): Service → host (for logs/status/ssh/exec)
    - by_project(): Project → host
    - current(): CWD-based lookup

    Hosts are loaded on-demand from inventory files via local config.
    """

    def _load_hosts_for_project(self, project_path: Path) -> list[AnsibleHost]:
        """Load hosts from project's local config and inventory.

        Args:
            project_path: Path to project directory

        Returns:
            List of AnsibleHost from inventory

        Raises:
            HostNotFoundError: If config or inventory invalid
        """
        from slipp.services.config.inventory import InventoryService
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

    def all_hosts(self) -> list[tuple[str, AnsibleHost]]:
        """Get all registered hosts across all projects.

        Loads hosts on-demand from each project's inventory.

        Returns:
            List of (project_name, AnsibleHost) tuples

        Example:
            >>> resolver = HostResolver()
            >>> hosts = resolver.all_hosts()
            >>> # [("mdad", host1), ("myapp", host2)]
        """
        from slipp.services.registry import ProjectRegistry

        results: list[tuple[str, AnsibleHost]] = []
        for project in ProjectRegistry().list_all():
            try:
                hosts = self._load_hosts_for_project(project.project_path)
                for host in hosts:
                    results.append((project.name, host))
            except HostNotFoundError:
                continue

        return results

    def by_service(self, service: str) -> AnsibleHost:
        """Resolve service name to host.

        Supports syntax:
        - "service" → lookup in service index
        - "service@host" → filter by host
        - "project:service" → filter by project
        - "project:service@host" → fully qualified

        Args:
            service: Service identifier

        Returns:
            AnsibleHost for the service

        Raises:
            HostNotFoundError: If service not found
            AmbiguousServiceError: If multiple matches found
        """
        from slipp.services.discovery import ServiceRegistry

        service_name, host_filter, project_filter = parse_service_identifier(service)

        host = ServiceRegistry().lookup_host_by_service(
            service_name, host=host_filter, project=project_filter
        )

        if host is None:
            raise HostNotFoundError(f"Service '{service}' not found in registry")

        return host

    def by_project(self, project: str) -> AnsibleHost:
        """Resolve project name to host.

        Loads host from project's local config and inventory.

        Args:
            project: Project name

        Returns:
            First AnsibleHost from project's inventory

        Raises:
            HostNotFoundError: If project not found or invalid
        """
        from slipp.services.registry import ProjectRegistry

        project_obj = ProjectRegistry().get(project)

        if project_obj is None:
            raise HostNotFoundError(f"Project '{project}' not found in registry")

        hosts = self._load_hosts_for_project(project_obj.project_path)
        return hosts[0]

    def current(self) -> AnsibleHost:
        """Resolve host from current working directory.

        Tries:
        1. Local slipp.yaml config → inventory
        2. Project name in registry (if name in local config)

        Returns:
            AnsibleHost for current context

        Raises:
            HostNotFoundError: If no context found
        """
        from slipp.services.config.local import LocalConfigService
        from slipp.services.registry import ProjectRegistry

        local_config = LocalConfigService.load()
        if local_config:
            try:
                return self._load_hosts_for_project(Path.cwd())[0]
            except HostNotFoundError:
                pass

            if local_config.name:
                project_obj = ProjectRegistry().get(local_config.name)
                if project_obj:
                    try:
                        hosts = self._load_hosts_for_project(project_obj.project_path)
                        return hosts[0]
                    except HostNotFoundError:
                        pass

        raise HostNotFoundError(
            "No host context found.\n"
            "Either:\n"
            "  - cd to project directory with slipp.yaml\n"
            "  - Use service name: slipp <cmd> <service>\n"
            "  - Use project flag: slipp <cmd> -p <project>"
        )

    def resolve(
        self,
        service: str | None = None,
        project: str | None = None,
    ) -> AnsibleHost:
        """Resolve host with fallback chain.

        Resolution order:
        1. Service (if provided)
        2. Project (if provided)
        3. Current context (CWD)

        Args:
            service: Optional service identifier
            project: Optional project name

        Returns:
            AnsibleHost

        Raises:
            HostNotFoundError: If resolution fails
            AmbiguousServiceError: If service is ambiguous
        """
        if service:
            return self.by_service(service)

        if project:
            return self.by_project(project)

        return self.current()
