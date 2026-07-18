"""Service lookup - resolving a service name to the host it runs on.

Services are discovered dynamically - all services on a project's hosts
belong to that project. Hosts are loaded on-demand from local configs.
"""

from slipp.models.host import AnsibleHost
from slipp.utils.errors import AmbiguousServiceError


def lookup_host_by_service(
    service_name: str, host: str | None = None, project: str | None = None
) -> AnsibleHost | None:
    """Find host actually running a service, using discovery (cached).

    Args:
        service_name: Service name to lookup
        host: Optional host filter (inventory_hostname or ansible_host)
        project: Optional project filter

    Returns:
        AnsibleHost if unique match found, None otherwise

    Raises:
        AmbiguousServiceError: If the service runs on multiple matching hosts
    """
    # Must stay lazy: config/__init__ (hosts.py) top-imports
    # lookup_host_by_service from this package's __init__, so this executes
    # while config/__init__ is still mid-import -- HostResolver isn't bound
    # yet at that point. The one intentional lazy import on this boundary;
    # discover_across_hosts (pipeline.py) also depends on services.config,
    # so it has to stay lazy here too.
    from slipp.services.config import HostResolver
    from slipp.services.discovery.pipeline import discover_across_hosts

    resolver = HostResolver()

    candidates: list[tuple[str, AnsibleHost]] = []
    for project_name, ansible_host in resolver.all_hosts():
        if project and project_name != project:
            continue

        if host:
            if (
                ansible_host.inventory_hostname != host
                and ansible_host.ansible_host != host
            ):
                continue

        candidates.append((project_name, ansible_host))

    if not candidates:
        return None

    # Unreachable hosts land in the discarded errors list instead of raising
    # -- can't confirm the service runs there, so skip them, same as before.
    services, _errors = discover_across_hosts(candidates, include_system=True)

    # Keyed by ansible_host alone, not (ansible_host, inventory_hostname) --
    # a shared host has no single true label (each project names it
    # independently), so every candidate at this IP is a real owner and
    # must all surface as matches, not just whichever label discovery
    # happened to stamp on the service.
    candidates_by_ip: dict[str, list[tuple[str, AnsibleHost]]] = {}
    for project_name, ansible_host in candidates:
        candidates_by_ip.setdefault(ansible_host.ansible_host, []).append(
            (project_name, ansible_host)
        )

    matches: list[tuple[str, AnsibleHost]] = []
    for svc in services:
        if svc.name != service_name:
            continue
        matches.extend(candidates_by_ip.get(svc.host, []))

    if not matches:
        return None

    if len(matches) > 1:
        match_details = [
            (m[0], m[1].inventory_hostname, m[1].ansible_host) for m in matches
        ]
        raise AmbiguousServiceError(service_name, match_details)

    return matches[0][1]
