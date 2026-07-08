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
    from slipp.services.config import HostResolver
    from slipp.services.discovery.discovery import DiscoveryService
    from slipp.utils.errors import SSHAuthenticationError, SSHConnectionError

    resolver = HostResolver()
    discovery = DiscoveryService()

    matches: list[tuple[str, AnsibleHost]] = []

    for project_name, ansible_host in resolver.all_hosts():
        if project and project_name != project:
            continue

        if host:
            if (
                ansible_host.inventory_hostname != host
                and ansible_host.ansible_host != host
            ):
                continue

        try:
            services = discovery.discover(ansible_host, include_system=True)
        except (SSHConnectionError, SSHAuthenticationError):
            # Host unreachable - can't confirm the service runs here, skip it
            continue

        if any(s.name == service_name for s in services):
            matches.append((project_name, ansible_host))

    if not matches:
        return None

    if len(matches) > 1:
        match_details = [
            (m[0], m[1].inventory_hostname, m[1].ansible_host) for m in matches
        ]
        raise AmbiguousServiceError(service_name, match_details)

    return matches[0][1]
