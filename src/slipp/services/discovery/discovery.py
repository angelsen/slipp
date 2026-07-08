"""Service discovery via systemctl queries.

Provides low-level systemctl querying with caching (DiscoveryService) and
business logic functions for filtering, lookup, and discovery pipeline.
These are the single source of truth for service discovery logic used by commands.
"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from slipp.models.host import AnsibleHost
from slipp.models.service import Runtime, Service, ServiceState
from slipp.services.ssh import SSHService
from slipp.utils.cache import Cache
from slipp.utils.identifiers import parse_service_identifier


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

    CACHE_TTL_SECONDS = 300

    def __init__(self):
        """Initialize discovery service."""
        self.cache = Cache()

    def discover(
        self,
        host_config: AnsibleHost,
        force: bool = False,
        include_system: bool = False,
    ) -> list[Service]:
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

        services = None
        if not force:
            cached = self.cache.get(cache_key)
            if cached:
                services = [Service.model_validate(svc) for svc in cached]

        if services is None:
            services = self._query_systemctl_batch(host_config)
            self.cache.set(
                cache_key,
                [svc.model_dump() for svc in services],
                ttl_seconds=self.CACHE_TTL_SECONDS,
            )

        if not include_system:
            services = self._filter_system_services(services)

        return services

    def _query_systemctl_batch(self, host_config: AnsibleHost) -> list[Service]:
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
            # systemctl list-units legitimately exits non-zero in some setups
            # while still returning usable stdout - don't check the exit code
            output_list = ssh.execute(cmd_list).stdout
            unit_names, states = self._parse_list_units(output_list)

            if not unit_names:
                return []

            services_arg = " ".join(unit_names)
            cmd_show = (
                f"sudo systemctl show {services_arg} "
                "-p ExecStart -p ActiveEnterTimestampMonotonic; "
                "echo __UPTIME__=$(cut -d' ' -f1 /proc/uptime)"
            )
            output_show = ssh.execute(cmd_show).stdout
            show_text, boot_uptime_seconds = self._split_uptime_marker(output_show)
            metadata = self._parse_show_output(show_text, len(unit_names))

            return self._build_services_from_batch(
                unit_names, states, metadata, host_config, boot_uptime_seconds
            )

    def _split_uptime_marker(self, output: str) -> tuple[str, float | None]:
        """Split the appended `__UPTIME__=<seconds>` marker from systemctl show output.

        The marker carries /proc/uptime (seconds since boot, monotonic clock)
        so uptime can be computed without parsing a server-local wall-clock
        timestamp string, whose trailing %Z abbreviation is not reliably
        parseable and whose comparison against UTC "now" is wrong on any
        non-UTC server.

        Args:
            output: Raw combined output of the systemctl show + echo command

        Returns:
            Tuple of (systemctl show output with marker line removed, boot uptime
            in seconds, or None if the marker was missing/unparseable)
        """
        boot_uptime_seconds = None
        show_lines = []
        for line in output.splitlines():
            if line.startswith("__UPTIME__="):
                try:
                    boot_uptime_seconds = float(line.split("=", 1)[1].strip())
                except ValueError:
                    boot_uptime_seconds = None
            else:
                show_lines.append(line)
        return "\n".join(show_lines), boot_uptime_seconds

    def _filter_system_services(self, services: list[Service]) -> list[Service]:
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

    def enrich_with_projects(self, services: list[Service]) -> list[Service]:
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

    def _calculate_uptime_from_monotonic(
        self, monotonic_usec: str, boot_uptime_seconds: float | None
    ) -> str | None:
        """Calculate uptime from ActiveEnterTimestampMonotonic.

        Args:
            monotonic_usec: Microseconds since boot when the unit became active
                (systemd's ActiveEnterTimestampMonotonic value)
            boot_uptime_seconds: Current /proc/uptime seconds-since-boot, captured
                in the same SSH round-trip as monotonic_usec so both share a clock

        Returns:
            Formatted uptime (e.g., "2h 31m", "5d 3h") or None
        """
        if not monotonic_usec or monotonic_usec == "0" or boot_uptime_seconds is None:
            return None

        try:
            active_seconds_since_boot = float(monotonic_usec) / 1_000_000
        except ValueError:
            return None

        uptime_seconds = boot_uptime_seconds - active_seconds_since_boot
        if uptime_seconds < 0:
            return None

        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)

        if days > 0:
            return f"{days}d {hours}h"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"

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
            ActiveEnterTimestampMonotonic=12345678
            (blank line)
            ExecStart={ path=/usr/sbin/nginx ... }
            ActiveEnterTimestampMonotonic=98765432
            (blank line)

        NOTE: If ExecStart is missing, systemd omits the property entirely.

        Args:
            output: Raw output from
                'systemctl show -p ExecStart -p ActiveEnterTimestampMonotonic'
                (with the `__UPTIME__=` marker line already stripped)
            expected_count: Number of services queried (for validation)

        Returns:
            List of metadata dicts: [{'exec': '...', 'monotonic': '...'}, ...]

        Edge cases:
            - Missing ExecStart (oneshot services): Property omitted, use empty string
            - Missing/zero monotonic timestamp (inactive services): Use '0'
            - Extra blank lines: Skip
        """
        lines = output.splitlines()
        metadata = []
        i = 0

        while i < len(lines) and len(metadata) < expected_count:
            exec_cmd = ""
            monotonic = "0"

            while i < len(lines) and lines[i].strip():
                line = lines[i].strip()

                if line.startswith("ExecStart="):
                    exec_cmd = line.replace("ExecStart=", "", 1).strip()
                elif line.startswith("ActiveEnterTimestampMonotonic="):
                    monotonic = line.replace(
                        "ActiveEnterTimestampMonotonic=", "", 1
                    ).strip()
                    if not monotonic:
                        monotonic = "0"

                i += 1

            metadata.append({"exec": exec_cmd, "monotonic": monotonic})

            if i < len(lines) and not lines[i].strip():
                i += 1

        while len(metadata) < expected_count:
            metadata.append({"exec": "", "monotonic": "0"})

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
        boot_uptime_seconds: float | None,
    ) -> list[Service]:
        """Build Service objects from batched data.

        Args:
            unit_names: List of unit names ['nginx.service', 'postgres.service']
            states: List of active states ['active', 'active', 'inactive']
            metadata: List of metadata dicts [{'exec': '...', 'monotonic': '...'}, ...]
            host_config: Host configuration
            boot_uptime_seconds: /proc/uptime seconds-since-boot captured alongside
                the metadata query, used to compute each service's uptime

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
                uptime = self._calculate_uptime_from_monotonic(
                    meta["monotonic"], boot_uptime_seconds
                )

            # NOTE: projects=[] by default, enriched later via enrich_with_projects()
            services.append(
                Service(
                    name=service_name,
                    host=host_config.ansible_host,
                    inventory_hostname=host_config.inventory_hostname,
                    unit_name=unit_name,
                    runtime=runtime,
                    state=state,
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


def _discover_on_host(
    project: str,
    host: AnsibleHost,
    include_system: bool,
    force: bool,
) -> tuple[str, list[Service], str | None]:
    """Discover services on a single host.

    Args:
        project: Project name
        host: Host to query
        include_system: Include system services
        force: Force re-discovery

    Returns:
        Tuple of (project_name, services, error_message)
    """
    try:
        services = discover_and_enrich(host, include_system=include_system, force=force)
        return (project, services, None)
    except Exception as e:
        # One unreachable host shouldn't abort discovery of the others.
        return (project, [], str(e))


def discover_across_hosts(
    hosts: list[tuple[str, AnsibleHost]],
    *,
    include_system: bool = False,
    force: bool = False,
    max_workers: int = 5,
) -> tuple[list[Service], list[str]]:
    """Discover services across multiple hosts in parallel.

    Args:
        hosts: List of (project_name, AnsibleHost) tuples
        include_system: Include system services
        force: Force re-discovery
        max_workers: Maximum parallel connections

    Returns:
        Tuple of (all_services, error_messages)
    """
    all_services: list[Service] = []
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_discover_on_host, project, host, include_system, force): (
                project,
                host,
            )
            for project, host in hosts
        }

        for future in as_completed(futures):
            project, host = futures[future]
            try:
                _, services, error = future.result(timeout=30)
                if error:
                    errors.append(f"{project} ({host.ansible_host}): {error}")
                else:
                    all_services.extend(services)
            except Exception as e:
                # Thread pool surfaces arbitrary errors (e.g. timeout); one
                # host's failure shouldn't abort discovery of the others.
                errors.append(f"{project} ({host.ansible_host}): {e}")

    return all_services, errors


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

    service_clean = service_name.lower().replace(".service", "")
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

    if project:
        result = [s for s in result if project in s.projects]

    if host:
        result = [s for s in result if s.inventory_hostname == host]

    if service_name:
        result = [s for s in result if s.name == service_name]

    if managed_roles and not show_all and not service_name:
        result = [s for s in result if _fuzzy_match_roles(s.name, managed_roles)]
    elif not show_all and not service_name:
        result = [s for s in result if s.projects]

    return result


def parse_systemctl_status(output_text: str) -> dict:
    """Parse systemctl status output to extract key details.

    Args:
        output_text: Raw output from systemctl status command.

    Returns:
        Dictionary with keys: loaded, active, pid, memory, tasks.
    """
    details = {}

    for line in output_text.splitlines():
        line = line.strip()

        if line.startswith("Loaded:"):
            details["loaded"] = line.replace("Loaded:", "").strip()
        elif line.startswith("Active:"):
            details["active"] = line.replace("Active:", "").strip()
        elif line.startswith("Main PID:"):
            match = re.search(r"Main PID:\s+(\d+)", line)
            if match:
                details["pid"] = match.group(1)
        elif line.startswith("Memory:"):
            match = re.search(r"Memory:\s+([\d.]+\w+)", line)
            if match:
                details["memory"] = match.group(1)
        elif line.startswith("Tasks:"):
            match = re.search(r"Tasks:\s+(\d+)", line)
            if match:
                details["tasks"] = match.group(1)

    return details


def extract_status_log_lines(output_text: str) -> list[str]:
    """Extract log lines from systemctl status output.

    Args:
        output_text: Raw output from systemctl status command.

    Returns:
        List of log lines from the systemctl output.
    """
    log_lines = []
    in_logs = False

    months = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]

    for line in output_text.splitlines():
        if in_logs or any(line.strip().startswith(m) for m in months):
            in_logs = True
            log_lines.append(line)

    return log_lines


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
    service_name, host_filter, project_filter = parse_service_identifier(
        service_identifier
    )

    matches = [s for s in services if s.name == service_name]

    if not matches:
        from slipp.utils.matching import fuzzy_match

        service_names = [s.name for s in services]
        best_match = fuzzy_match(service_name, service_names)
        if best_match:
            matches = [s for s in services if s.name == best_match]

    if host_filter:
        matches = [s for s in matches if s.inventory_hostname == host_filter]
    if project_filter:
        matches = [s for s in matches if project_filter in s.projects]

    return matches[0] if matches else None
