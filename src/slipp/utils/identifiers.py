"""Service identifier parsing shared by host resolution and discovery."""


def parse_service_identifier(service: str) -> tuple[str, str | None, str | None]:
    """Parse service identifier into components.

    Supports syntax:
    - "service" → (service, None, None)
    - "service@host" → (service, host, None)
    - "project:service" → (service, None, project)
    - "project:service@host" → (service, host, project)

    Args:
        service: Service identifier string

    Returns:
        Tuple of (service_name, host_filter, project_filter)
    """
    project_filter = None
    host_filter = None
    service_name = service

    if ":" in service:
        project_filter, service_name = service.split(":", 1)

    if "@" in service_name:
        service_name, host_filter = service_name.split("@", 1)

    return service_name, host_filter, project_filter
