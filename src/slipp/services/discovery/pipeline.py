"""Discover → enrich pipeline (single-host and multi-host), used by commands.

Split out from discovery.py so that services/config (HostResolver) and
services/discovery can import each other's leaf pieces without a cycle:
DiscoveryService (discovery.py) has no config dependency, while this module
depends on config and is never imported by services/discovery/__init__.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from slipp.models.host import AnsibleHost
from slipp.models.service import Service
from slipp.services.config import HostResolver
from slipp.services.discovery.discovery import DiscoveryService


def build_host_project_map() -> dict[str, list[str]]:
    """Build ansible_host → [project_names] across every registered project.

    Loads and parses every registered project's inventory. Prefer passing an
    already-known map to enrich_with_projects()/discover_and_enrich() when
    the caller already has (project, host) pairs, to avoid repeating this
    full registry scan.

    Returns:
        Reverse lookup of ansible_host → list of owning project names
    """
    host_to_projects: dict[str, list[str]] = {}
    for project_name, host in HostResolver().all_hosts():
        host_to_projects.setdefault(host.ansible_host, []).append(project_name)

    return host_to_projects


def enrich_with_projects(
    services: list[Service],
    host_to_projects: dict[str, list[str]] | None = None,
) -> list[Service]:
    """Enrich services with project names based on host ownership.

    All services on a host belong to ALL projects that own that host.
    This supports multi-project hosts (e.g., same VPS shared by 'myapp' and 'staging').

    Args:
        services: List of discovered services
        host_to_projects: Pre-built ansible_host → [project_names] map.
            Callers that already know host ownership (e.g.
            discover_across_hosts) should pass this to avoid re-scanning
            every project's inventory. Built from the full registry when
            omitted.

    Returns:
        Same list with projects field populated based on host ownership
    """
    if host_to_projects is None:
        host_to_projects = build_host_project_map()

    # Enrich services - all services on a host belong to that host's projects
    for service in services:
        service.projects = host_to_projects.get(service.host, [])

    return services


def discover_and_enrich(
    ssh_config: AnsibleHost,
    include_system: bool = False,
    force: bool = False,
    host_to_projects: dict[str, list[str]] | None = None,
) -> list[Service]:
    """Standard discovery pipeline: discover → enrich with project names.

    Args:
        ssh_config: Host configuration to discover services on
        include_system: Include system services (systemd-*, getty@, etc.)
        force: Skip cache, force re-discovery
        host_to_projects: Pre-built ansible_host → [project_names] map, see
            enrich_with_projects(). Built from the full registry when omitted.

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
        ssh_config,
        include_system=include_system,
        force=force,
    )
    services = enrich_with_projects(services, host_to_projects)
    return services


def _discover_on_host(
    project: str,
    host: AnsibleHost,
    include_system: bool,
    force: bool,
    host_to_projects: dict[str, list[str]],
) -> tuple[str, list[Service], str | None]:
    """Discover services on a single host.

    Args:
        project: Project name
        host: Host to query
        include_system: Include system services
        force: Force re-discovery
        host_to_projects: Pre-built ansible_host → [project_names] map

    Returns:
        Tuple of (project_name, services, error_message)
    """
    try:
        services = discover_and_enrich(
            host,
            include_system=include_system,
            force=force,
            host_to_projects=host_to_projects,
        )
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

    # Ownership is already known from `hosts` -- build the reverse map once
    # instead of each parallel worker re-scanning the full project registry.
    host_to_projects: dict[str, list[str]] = {}
    for project, host in hosts:
        host_to_projects.setdefault(host.ansible_host, []).append(project)

    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures = {
        executor.submit(
            _discover_on_host,
            project,
            host,
            include_system,
            force,
            host_to_projects,
        ): (
            project,
            host,
        )
        for project, host in hosts
    }

    try:
        # as_completed() only ever yields futures that are already done, so a
        # per-future result(timeout=...) here would never actually block --
        # the timeout has to be on as_completed() itself to bound the total
        # wall-clock time for the batch.
        for future in as_completed(futures, timeout=30):
            project, host = futures[future]
            try:
                _, services, error = future.result()
                if error:
                    errors.append(f"{project} ({host.ansible_host}): {error}")
                else:
                    all_services.extend(services)
            except Exception as e:
                # One host's failure shouldn't abort discovery of the others.
                errors.append(f"{project} ({host.ansible_host}): {e}")
    except TimeoutError:
        for future, (project, host) in futures.items():
            if not future.done():
                errors.append(f"{project} ({host.ansible_host}): discovery timed out")
    finally:
        # wait=False so we don't block returning on threads still stuck in a
        # blocking SSH call; cancel_futures drops any not yet started.
        executor.shutdown(wait=False, cancel_futures=True)

    return all_services, errors
