"""ServiceLocator - Unified service discovery and lookup across all commands.

This module establishes "one way to find services" to eliminate the duplicated
3-line pattern (discover → filter → find) repeated across 5+ commands.

Philosophy:
- Single responsibility: Service location (discovery + filtering + lookup)
- Commands import ServiceLocator instead of calling common functions directly
- Encapsulates the standard discovery pipeline
- Makes it easier to add caching/optimization later

Usage:
    from slipp.services.service_locator import ServiceLocator

    # Find single service
    locator = ServiceLocator(ssh_config)
    service = locator.find_one("synapse")

    # Find multiple services with filters
    services = locator.find_many(project="PoC", host="production")
"""

from slipp.models.host import AnsibleHost
from slipp.models.service import Service
from slipp.services.discovery.discovery import (
    discover_and_enrich,
    filter_services,
    find_service,
)
from slipp.utils.errors import ServiceNotFoundError


class ServiceLocator:
    """Unified service discovery and lookup.

    Consolidates the common pattern of discover → filter → find that was
    duplicated across commands (logs, exec, deploy, etc.).

    Attributes:
        ssh_config: Host configuration to discover services on
        include_system: Whether to include system services in discovery

    Example:
        >>> locator = ServiceLocator(ssh_config)
        >>> service = locator.find_one("synapse")
        >>> print(f"Found: {service.name}@{service.host}")

        >>> # With filters
        >>> service = locator.find_one("backend", project="PoC")

        >>> # Find multiple services
        >>> services = locator.find_many(project="PoC")
    """

    def __init__(self, ssh_config: AnsibleHost, include_system: bool = False):
        """Initialize ServiceLocator.

        Args:
            ssh_config: Host configuration to discover services on
            include_system: Include system services (systemd-*, getty@, etc.)
        """
        self.ssh_config = ssh_config
        self.include_system = include_system

    def find_one(
        self,
        identifier: str,
        project: str | None = None,
        host: str | None = None,
    ) -> Service:
        """Find single service by identifier with optional filters.

        This is the canonical way to find a single service. Raises
        ServiceNotFoundError if not found (rather than returning None).

        Args:
            identifier: Service identifier (supports: "service", "service@host", "project:service")
            project: Optional project filter
            host: Optional host filter

        Returns:
            Matched Service object

        Raises:
            ServiceNotFoundError: If service not found

        Example:
            >>> locator = ServiceLocator(ssh_config)
            >>> service = locator.find_one("synapse")
            >>> service = locator.find_one("backend@production")
            >>> service = locator.find_one("PoC:backend", project="PoC")
        """
        services = discover_and_enrich(
            self.ssh_config,
            include_system=self.include_system,
        )

        filtered = filter_services(
            services,
            project=project,
            host=host,
            show_all=self.include_system,
        )

        service = find_service(filtered, identifier)

        if not service:
            raise ServiceNotFoundError(
                f"Service '{identifier}' not found on {self.ssh_config.ansible_host}"
            )

        return service

    def find_many(
        self,
        project: str | None = None,
        host: str | None = None,
        service_name: str | None = None,
    ) -> list[Service]:
        """Find multiple services with filters.

        Unlike find_one(), this never raises ServiceNotFoundError - it just
        returns an empty list if no services match.

        Args:
            project: Filter by project name
            host: Filter by inventory_hostname
            service_name: Filter by service name

        Returns:
            List of matched services (may be empty)

        Example:
            >>> locator = ServiceLocator(ssh_config)
            >>> services = locator.find_many(project="PoC")
            >>> services = locator.find_many(service_name="synapse")
        """
        services = discover_and_enrich(
            self.ssh_config,
            include_system=self.include_system,
        )

        return filter_services(
            services,
            project=project,
            host=host,
            service_name=service_name,
            show_all=True,
        )
