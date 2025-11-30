"""Service registry - service lookups based on host ownership.

Services are discovered dynamically - all services on a project's hosts
belong to that project. Hosts are loaded on-demand from local configs.
"""

from slipp.models.host import AnsibleHost
from slipp.utils.errors import AmbiguousServiceError


class ServiceRegistry:
    """Manages service lookups based on host ownership.

    Services are discovered dynamically via systemctl queries.
    A service belongs to ALL projects that own the host it runs on.
    Hosts are loaded on-demand from local configs.
    """

    def lookup_host_by_service(
        self, service_name: str, host: str | None = None, project: str | None = None
    ) -> AnsibleHost | None:
        """Find host for a service using discovery cache.

        NOTE: This method now requires live discovery data to work.
        Use HostResolver.by_service() for most use cases, which handles
        discovery automatically.

        Args:
            service_name: Service name to lookup
            host: Optional host filter (inventory_hostname or ansible_host)
            project: Optional project filter

        Returns:
            AnsibleHost if unique match found, None otherwise

        Raises:
            AmbiguousServiceError: If multiple matches found
        """
        from slipp.services.config import HostResolver

        resolver = HostResolver()

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

            matches.append((project_name, ansible_host))

        if not matches:
            return None

        if len(matches) > 1:
            match_details = [
                (m[0], m[1].inventory_hostname, m[1].ansible_host) for m in matches
            ]
            raise AmbiguousServiceError(service_name, match_details)

        return matches[0][1]
