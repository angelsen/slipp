"""Filtering and lookup over already-discovered services.

Single source of truth for service filtering/lookup logic that was
previously duplicated across commands. See services/discovery/discovery.py
for the discovery pipeline that produces the `Service` lists these operate on.
"""

from slipp.models.service import Service
from slipp.utils.identifiers import parse_service_identifier
from slipp.utils.matching import fuzzy_match


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
        service_names = [s.name for s in services]
        best_match = fuzzy_match(service_name, service_names)
        if best_match:
            matches = [s for s in services if s.name == best_match]

    if host_filter:
        matches = [s for s in matches if s.inventory_hostname == host_filter]
    if project_filter:
        matches = [s for s in matches if project_filter in s.projects]

    return matches[0] if matches else None
