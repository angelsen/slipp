"""Service discovery via systemctl queries.

Provides low-level systemctl querying with caching (DiscoveryService).
See services/discovery/pipeline.py for the discover → enrich pipeline
(single-host and multi-host) used by commands, services/discovery/filtering.py
for filtering/lookup over already-discovered services, and services/status
for `systemctl status` output parsing.
"""

from slipp.models.host import AnsibleHost
from slipp.models.service import Runtime, Service, ServiceState
from slipp.services.ssh import SSHService
from slipp.utils.cache import Cache


def _split_uptime_marker(output: str) -> tuple[str, float | None]:
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


def _is_system_service(name: str) -> bool:
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


def _calculate_uptime_from_monotonic(
    monotonic_usec: str, boot_uptime_seconds: float | None
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


def _parse_list_units(output: str) -> tuple[list[str], list[str]]:
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


def _parse_show_output(output: str, expected_count: int) -> list[dict]:
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


def _detect_runtime(exec_cmd: str) -> Runtime:
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


class DiscoveryService:
    """Service discovery via systemctl with caching.

    Auto-discovers services on remote hosts by querying systemctl.
    Results are cached for 5 minutes to avoid repeated SSH queries.

    Example:
        >>> from slipp.models.host import AnsibleHost
        >>> host = AnsibleHost(ansible_host='192.0.2.1', ansible_user='root')
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
            if cached is not None:
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
            ssh.ensure_sudo("Service discovery")

            cmd_list = (
                "sudo systemctl list-units --type=service --all --no-pager --plain"
            )
            # systemctl list-units legitimately exits non-zero in some setups
            # while still returning usable stdout - only raise on sudo failures
            result_list = ssh.execute(cmd_list)
            ssh.check_sudo(result_list, "Service discovery")
            output_list = result_list.stdout
            unit_names, states = _parse_list_units(output_list)

            if not unit_names:
                return []

            services_arg = " ".join(unit_names)
            cmd_show = (
                f"sudo systemctl show {services_arg} "
                "-p ExecStart -p ActiveEnterTimestampMonotonic; "
                "echo __UPTIME__=$(cut -d' ' -f1 /proc/uptime)"
            )
            output_show = ssh.execute(cmd_show).stdout
            show_text, boot_uptime_seconds = _split_uptime_marker(output_show)
            metadata = _parse_show_output(show_text, len(unit_names))

            return self._build_services_from_batch(
                unit_names, states, metadata, host_config, boot_uptime_seconds
            )

    def _filter_system_services(self, services: list[Service]) -> list[Service]:
        """Filter out system/noise services.

        Args:
            services: List of all services

        Returns:
            Filtered list (excluding system services)
        """
        return [s for s in services if not _is_system_service(s.name)]

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

            runtime = _detect_runtime(meta["exec"])

            if active == "active":
                state = ServiceState.ACTIVE
            elif active == "failed":
                state = ServiceState.FAILED
            else:
                state = ServiceState.INACTIVE

            uptime = None
            if state == ServiceState.ACTIVE:
                uptime = _calculate_uptime_from_monotonic(
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
