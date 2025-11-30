"""Service discovery via systemctl queries.

This module contains:
1. DiscoveryService - Low-level systemctl querying with caching
2. Business logic functions - Filtering, lookup, and discovery pipeline

The functions here are the single source of truth for service discovery
and filtering logic, used by both ServiceLocator and commands.
"""

from typing import List

from slipp.models.host import AnsibleHost
from slipp.models.service import Runtime, Service, ServiceState
from slipp.services.ssh import SSHService
from slipp.utils.cache import Cache


class DiscoveryService:
    """Service discovery via systemctl with caching.

    Auto-discovers services on remote hosts by querying systemctl.
    Results are cached for 5 minutes to avoid repeated SSH queries.

    Example:
        >>> from slipp.models.host import AnsibleHost
        >>> host = AnsibleHost(ansible_host='46.251.249.252', ansible_user='root')
        >>> discovery = DiscoveryService()
        >>> services = discovery.discover(host)
        >>> for service in services:
        ...     print(f"{service.name}: {service.state}")
    """

    def __init__(self, cache_ttl: int = 300):
        """Initialize discovery service.

        Args:
            cache_ttl: Cache TTL in seconds (default: 300 = 5 minutes)
        """
        self.cache = Cache()
        self.cache_ttl = cache_ttl

    def discover(
        self,
        host_config: AnsibleHost,
        force: bool = False,
        include_system: bool = False,
    ) -> List[Service]:
        """Discover services on host.

        Args:
            host_config: Host to query
            force: Skip cache, force re-discovery
            include_system: Include system services (systemd-*, getty@, etc.)

        Returns:
            List of discovered services

        Example:
            >>> services = discovery.discover(host_config)
            >>> print(f"Found {len(services)} services")
        """
        cache_key = f"services:{host_config.ansible_host}"

        if not force:
            cached = self.cache.get(cache_key)
            if cached:
                services = [Service.model_validate(svc) for svc in cached]

                if not include_system:
                    services = self._filter_system_services(services)

                return services

        services = self._query_systemctl_batch(host_config)

        self.cache.set(
            cache_key,
            [svc.model_dump() for svc in services],
            ttl_seconds=self.cache_ttl,
        )

        if not include_system:
            services = self._filter_system_services(services)

        return services

    def _query_systemctl_batch(self, host_config: AnsibleHost) -> List[Service]:
        """Query all service data in TWO passes (aligned).

        Pass 1: Get filtered service list + states
        Pass 2: Query ONLY those specific services for metadata

        This ensures perfect alignment between services and metadata.

        Args:
            host_config: Host to query

        Returns:
            List of discovered services
        """
        with SSHService(host_config) as ssh:
            cmd_list = (
                "sudo systemctl list-units --type=service --all --no-pager --plain"
            )
            output_list = ssh.execute(cmd_list)
            unit_names, states = self._parse_list_units(output_list)

            if not unit_names:
                return []

            services_arg = " ".join(unit_names)
            cmd_show = f"sudo systemctl show {services_arg} -p ExecStart -p ActiveEnterTimestamp"
            output_show = ssh.execute(cmd_show)
            metadata = self._parse_show_output(output_show, len(unit_names))

            return self._build_services_from_batch(
                unit_names, states, metadata, host_config
            )

    def _filter_system_services(self, services: List[Service]) -> List[Service]:
        """Filter out system/noise services.

        Args:
            services: List of all services

        Returns:
            Filtered list (excluding system services)
        """
        return [s for s in services if not self._is_system_service(s.name)]

    def _is_system_service(self, name: str) -> bool:
        """Check if service is a system service (noise).

        Args:
            name: Service name

        Returns:
            True if system service, False otherwise
        """
        system_patterns = [
            "systemd-",
            "getty@",
            "user@",
            "session-",
            "plymouth-",
            "emergency",
            "rescue",
            "dbus-org",
        ]
        return any(name.startswith(p) for p in system_patterns)

    def enrich_with_projects(self, services: List[Service]) -> List[Service]:
        """Enrich services with project names based on host ownership.

        All services on a host belong to ALL projects that own that host.
        This supports multi-project hosts (e.g., same VPS as 'PoC' and 'staging').

        Args:
            services: List of discovered services

        Returns:
            Same list with projects field populated based on host ownership
        """
        from slipp.services.config import HostResolver

        resolver = HostResolver()

        # Build reverse lookup: ansible_host → [project_names]
        host_to_projects: dict[str, list[str]] = {}
        for project_name, host in resolver.all_hosts():
            ip = host.ansible_host
            if ip not in host_to_projects:
                host_to_projects[ip] = []
            host_to_projects[ip].append(project_name)

        # Enrich services - all services on a host belong to that host's projects
        for service in services:
            service.projects = host_to_projects.get(service.host, [])

        return services

    def _calculate_uptime_from_timestamp(self, timestamp: str) -> str | None:
        """Calculate uptime from ActiveEnterTimestamp.

        Args:
            timestamp: Timestamp string from systemd (e.g., "Sun 2025-11-23 18:07:23 UTC")

        Returns:
            Formatted uptime (e.g., "2h 31m", "5d 3h") or None
        """
        from datetime import datetime

        try:
            if not timestamp or timestamp == "n/a":
                return None

            parts = timestamp.strip().split()
            if len(parts) >= 4:
                dt_str = " ".join(parts[1:4])
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S %Z")
            else:
                return None

            now = datetime.utcnow()
            delta = now - dt

            days = delta.days
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60

            if days > 0:
                return f"{days}d {hours}h"
            elif hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m"

        except Exception:
            return None

    def _parse_list_units(self, output: str) -> tuple[list[str], list[str]]:
        """Parse systemctl list-units output.

        Args:
            output: Raw output from 'systemctl list-units'

        Returns:
            Tuple of (unit_names, states)
            - unit_names: ['nginx.service', 'postgres.service']
            - states: ['active', 'active', 'inactive']

        Example input:
            nginx.service      loaded active   running Nginx HTTP Server
            postgres.service   loaded active   running PostgreSQL Database
            ssh.service        loaded inactive dead    OpenBSD Secure Shell
        """
        unit_names = []
        states = []

        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 5 or not parts[0].endswith(".service"):
                continue

            unit_name = parts[0]
            load = parts[1]
            active = parts[2]

            if load == "not-found":
                continue

            unit_names.append(unit_name)
            states.append(active)

        return unit_names, states

    def _parse_show_output(self, output: str, expected_count: int) -> list[dict]:
        """Parse systemctl show output (property=value pairs).

        When showing multiple properties for multiple services, systemd outputs:
            ExecStart={ path=/usr/bin/podman ... }
            ActiveEnterTimestamp=Sun 2025-11-23 18:07:23 UTC
            (blank line)
            ExecStart={ path=/usr/sbin/nginx ... }
            ActiveEnterTimestamp=Mon 2025-11-17 09:59:12 UTC
            (blank line)

        NOTE: If ExecStart is missing, systemd omits the property entirely.

        Args:
            output: Raw output from 'systemctl show -p ExecStart -p ActiveEnterTimestamp'
            expected_count: Number of services queried (for validation)

        Returns:
            List of metadata dicts: [{'exec': '...', 'timestamp': '...'}, ...]

        Edge cases:
            - Missing ExecStart (oneshot services): Property omitted, use empty string
            - Blank timestamp (inactive services): Use 'n/a'
            - Extra blank lines: Skip
        """
        lines = output.splitlines()
        metadata = []
        i = 0

        while i < len(lines) and len(metadata) < expected_count:
            exec_cmd = ""
            timestamp = "n/a"

            while i < len(lines) and lines[i].strip():
                line = lines[i].strip()

                if line.startswith("ExecStart="):
                    exec_cmd = line.replace("ExecStart=", "", 1).strip()
                elif line.startswith("ActiveEnterTimestamp="):
                    timestamp = line.replace("ActiveEnterTimestamp=", "", 1).strip()
                    if not timestamp:
                        timestamp = "n/a"

                i += 1

            metadata.append({"exec": exec_cmd, "timestamp": timestamp})

            if i < len(lines) and not lines[i].strip():
                i += 1

        while len(metadata) < expected_count:
            metadata.append({"exec": "", "timestamp": "n/a"})

        return metadata[:expected_count]

    def _detect_runtime(self, exec_cmd: str) -> Runtime:
        """Detect service runtime from ExecStart command.

        Args:
            exec_cmd: ExecStart value from systemctl show

        Returns:
            Runtime enum (SYSTEMD, DOCKER, or PODMAN)
        """
        if not exec_cmd:
            return Runtime.SYSTEMD

        exec_lower = exec_cmd.lower()
        if "podman" in exec_lower:
            return Runtime.PODMAN
        elif "docker" in exec_lower:
            return Runtime.DOCKER

        return Runtime.SYSTEMD

    def _build_services_from_batch(
        self,
        unit_names: list[str],
        states: list[str],
        metadata: list[dict],
        host_config: AnsibleHost,
    ) -> list[Service]:
        """Build Service objects from batched data.

        Args:
            unit_names: List of unit names ['nginx.service', 'postgres.service']
            states: List of active states ['active', 'active', 'inactive']
            metadata: List of metadata dicts [{'exec': '...', 'timestamp': '...'}, ...]
            host_config: Host configuration

        Returns:
            List of Service objects
        """
        services = []

        for i, unit_name in enumerate(unit_names):
            service_name = unit_name.replace(".service", "")
            active = states[i]
            meta = metadata[i]

            runtime = self._detect_runtime(meta["exec"])

            if active == "active":
                state = ServiceState.ACTIVE
            elif active == "failed":
                state = ServiceState.FAILED
            else:
                state = ServiceState.INACTIVE

            uptime = None
            if state == ServiceState.ACTIVE:
                uptime = self._calculate_uptime_from_timestamp(meta["timestamp"])

            # NOTE: projects=[] by default, enriched later via enrich_with_projects()
            services.append(
                Service(
                    name=service_name,
                    host=host_config.ansible_host,
                    inventory_hostname=host_config.inventory_hostname,
                    unit_name=unit_name,
                    runtime=runtime,
                    state=state,
                    pid=None,
                    uptime=uptime,
                )
            )

        return services


def discover_and_enrich(
    ssh_config: AnsibleHost,
    include_system: bool = False,
    force: bool = False,
) -> list[Service]:
    """Standard discovery pipeline: discover → enrich with project names.

    Args:
        ssh_config: Host configuration to discover services on
        include_system: Include system services (systemd-*, getty@, etc.)
        force: Skip cache, force re-discovery

    Returns:
        List of discovered services enriched with project names

    Example:
        >>> services = discover_and_enrich(ssh_config, include_system=True)
        >>> for s in services:
        ...     projects_str = ', '.join(s.projects) if s.projects else 'no project'
        ...     print(f"{s.name} ({projects_str})")
    """
    discovery = DiscoveryService()
    services = discovery.discover(
        ssh_config, include_system=include_system, force=force
    )
    services = discovery.enrich_with_projects(services)
    return services


def _fuzzy_match_roles(
    service_name: str, roles: list[str], threshold: float = 0.6
) -> bool:
    """Check if service name fuzzy-matches any role name.

    Args:
        service_name: Name of the service (e.g., 'poc-backend')
        roles: List of role names from playbook (e.g., ['caddy', 'app-backend'])
        threshold: Minimum similarity ratio (0.0 to 1.0, default: 0.6)

    Returns:
        True if service name matches any role with similarity >= threshold
    """
    from slipp.utils.matching import fuzzy_match

    # Normalize service name (strip .service suffix)
    service_clean = service_name.lower().replace(".service", "")

    # Check if service matches any role
    return fuzzy_match(service_clean, roles, threshold=threshold) is not None


def filter_services(
    services: list[Service],
    *,
    project: str | None = None,
    host: str | None = None,
    service_name: str | None = None,
    show_all: bool = False,
    managed_roles: list[str] | None = None,
) -> list[Service]:
    """Single source of truth for service filtering logic.

    This function consolidates filtering logic that was duplicated across
    multiple commands. It respects the show_all flag consistently.

    Hybrid filtering strategy (when managed_roles provided):
    1. Services fuzzy-matching a role name → included
    2. Otherwise → excluded (system service, podman management, etc.)

    Args:
        services: List of services to filter
        project: Filter by project name (checks if project is in service.projects list)
        host: Filter by inventory_hostname (exact match)
        service_name: Filter by service name (exact match)
        show_all: If False (default), exclude services without any project ownership
        managed_roles: Optional list of role names for hybrid filtering

    Returns:
        Filtered list of services

    Example:
        >>> # Show only services belonging to a specific project
        >>> filtered = filter_services(services, project="PoC", show_all=False)
        >>>
        >>> # Show all services including unregistered ones
        >>> all_svcs = filter_services(services, show_all=True)
        >>>
        >>> # Hybrid filter: containers + fuzzy-matched roles
        >>> filtered = filter_services(services, project="PoC", managed_roles=['caddy', 'app-backend'])
    """
    result = services

    # Filter by project (check if project is in the service's projects list)
    if project:
        result = [s for s in result if project in s.projects]

    # Filter by host
    if host:
        result = [s for s in result if s.inventory_hostname == host]

    # Filter by service name
    if service_name:
        result = [s for s in result if s.name == service_name]

    # Hybrid filtering: fuzzy role match (unless show_all or specific service)
    # All services (including containers) must match a managed role
    if managed_roles and not show_all and not service_name:
        result = [s for s in result if _fuzzy_match_roles(s.name, managed_roles)]
    # Default behavior: hide services with no project ownership (unless show_all or specific service)
    elif not show_all and not service_name:
        result = [s for s in result if s.projects]  # Non-empty projects list

    return result


def extract_service_name(service_identifier: str) -> str:
    """Extract bare service name from identifier.

    Handles three syntax patterns:
    1. Simple: "service" → "service"
    2. Host-qualified: "service@host" → "service"
    3. Project-qualified: "project:service" → "service"

    Args:
        service_identifier: Service identifier in one of the supported formats

    Returns:
        Bare service name without qualifiers

    Example:
        >>> extract_service_name("poc-backend")
        'poc-backend'
        >>> extract_service_name("poc-backend@production")
        'poc-backend'
        >>> extract_service_name("PoC:poc-backend")
        'poc-backend'
    """
    if "@" in service_identifier:
        return service_identifier.split("@", 1)[0]
    elif ":" in service_identifier:
        return service_identifier.split(":", 1)[1]
    return service_identifier


def find_service(
    services: list[Service],
    service_identifier: str,
) -> Service | None:
    """Find service by name with syntax support.

    Handles three syntax patterns:
    1. Simple: "service" → Match by name
    2. Host-qualified: "service@host" → Match by name and inventory_hostname
    3. Project-qualified: "project:service" → Match by project membership and name

    Args:
        services: List of services to search
        service_identifier: Service identifier in one of the supported formats

    Returns:
        Matched Service object, or None if not found

    Example:
        >>> # Simple lookup
        >>> svc = find_service(services, "poc-backend")
        >>>
        >>> # Host-qualified lookup
        >>> svc = find_service(services, "poc-backend@production")
        >>>
        >>> # Project-qualified lookup (checks if project is in service.projects)
        >>> svc = find_service(services, "PoC:poc-backend")
    """
    # Parse service identifier syntax
    service_name = extract_service_name(service_identifier)
    host_filter = None
    project_filter = None

    if "@" in service_identifier:
        _, host_filter = service_identifier.split("@", 1)
    elif ":" in service_identifier:
        project_filter, _ = service_identifier.split(":", 1)

    # Find matching services (exact match first)
    matches = [s for s in services if s.name == service_name]

    # Fuzzy fallback if no exact match
    if not matches:
        from slipp.utils.matching import fuzzy_match

        service_names = [s.name for s in services]
        best_match = fuzzy_match(service_name, service_names)
        if best_match:
            matches = [s for s in services if s.name == best_match]

    # Apply additional filters if specified
    if host_filter:
        matches = [s for s in matches if s.inventory_hostname == host_filter]
    if project_filter:
        matches = [s for s in matches if project_filter in s.projects]

    # Return first match or None
    return matches[0] if matches else None
