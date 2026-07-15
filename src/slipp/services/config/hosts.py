"""Unified host resolution for all commands.

This module provides a single source of truth for resolving hosts from:
- Service names (via lookup_host_by_service)
- Project names (via ProjectRegistry → local config → inventory)
- Current working directory context

Hosts are parsed on-demand from inventory files, not stored in the registry.
"""

from pathlib import Path

from slipp import output
from slipp.models.host import AnsibleHost
from slipp.services.config.inventory import load_project_ansible_hosts
from slipp.services.config.local import LocalConfigService
from slipp.services.discovery import lookup_host_by_service
from slipp.services.registry import ProjectRegistry
from slipp.utils.errors import ConfigError, HostNotFoundError, ProjectNotFoundError
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

    def __init__(self) -> None:
        self._registry = ProjectRegistry()

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
        results: list[tuple[str, AnsibleHost]] = []
        for project in self._registry.list_all():
            try:
                hosts = load_project_ansible_hosts(project.project_path)
                for host in hosts:
                    results.append((project.name, host))
            except (ConfigError, HostNotFoundError):
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
        service_name, host_filter, project_filter = parse_service_identifier(service)

        host = lookup_host_by_service(
            service_name, host=host_filter, project=project_filter
        )

        if host is None:
            raise HostNotFoundError(f"Service '{service}' not found in registry")

        return host

    def _first_host(self, hosts: list[AnsibleHost], context_label: str) -> AnsibleHost:
        """Return the first host, warning if others are being silently ignored.

        Commands that resolve a single host (host, exec, ssh, logs, ...) have
        no way to disambiguate between multiple hosts in one project's
        inventory. Rather than silently picking one, surface the choice.
        """
        if len(hosts) > 1:
            others = ", ".join(h.inventory_hostname for h in hosts[1:])
            output.warning(
                f"{context_label} has {len(hosts)} hosts; using "
                f"'{hosts[0].inventory_hostname}' (first in inventory). "
                f"Others: {others}"
            )
        return hosts[0]

    def by_project(self, project: str) -> AnsibleHost:
        """Resolve project name to host.

        Loads host from project's local config and inventory.

        Args:
            project: Project name

        Returns:
            First AnsibleHost from project's inventory

        Raises:
            ProjectNotFoundError: If project not registered
            HostNotFoundError: If the project's inventory is invalid
        """
        project_obj = self._registry.get(project)

        if project_obj is None:
            raise ProjectNotFoundError(f"Project '{project}' not found in registry")

        hosts = load_project_ansible_hosts(project_obj.project_path)
        return self._first_host(hosts, f"Project '{project}'")

    def _try_load_from(self, path: Path) -> AnsibleHost | None:
        """Load the first host from `path`'s inventory, or None if not found."""
        try:
            hosts = load_project_ansible_hosts(path)
            return self._first_host(hosts, "Current project")
        except (ConfigError, HostNotFoundError):
            return None

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
        project_root = LocalConfigService.find_root()
        local_config = LocalConfigService.load(project_root) if project_root else None
        if local_config:
            assert project_root is not None
            host = self._try_load_from(project_root)
            if host:
                return host

            if local_config.name:
                project_obj = self._registry.get(local_config.name)
                if project_obj:
                    host = self._try_load_from(project_obj.project_path)
                    if host:
                        return host

        raise HostNotFoundError(
            "No host context found.\n"
            "Either:\n"
            "  - cd to project directory (or a subdirectory of it) with slipp.yaml\n"
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
            ProjectNotFoundError: If `project` isn't registered
            AmbiguousServiceError: If service is ambiguous
        """
        if service:
            return self.by_service(service)

        if project:
            return self.by_project(project)

        return self.current()
