"""Service identifier parsing shared by host resolution and discovery."""

import re

_CONFIG_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def validate_config_name(value: str, label: str) -> str:
    """Reject names that would break generated configs downstream.

    Project and service names are interpolated into systemd unit names,
    remote paths, rsync arguments, and YAML scalars across the generated
    Ansible roles -- a space, ':', or '#' breaks those in ways no quoting
    at the use sites can fix. Validating at ingestion (Pydantic validators
    on DetectedService.name / LocalConfig.name) turns all of that into one
    clear error at scan/config time.

    Raises:
        ValueError: If the name contains anything outside
            letters/digits/'.'/'_'/'-' or doesn't start alphanumeric.
    """
    if not _CONFIG_NAME_RE.match(value):
        raise ValueError(
            f"{label} '{value}' contains characters that would break generated "
            "configs (systemd units, YAML, remote paths) -- allowed: letters, "
            "digits, '.', '_', '-', starting with a letter or digit"
        )
    return value


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
