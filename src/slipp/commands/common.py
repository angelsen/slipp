"""Presentation utilities for commands.

This module contains display/formatting functions shared across commands.
Business logic (filtering, discovery, lookups) is in services/discovery.py.
"""

from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.models.host import AnsibleHost
from slipp.models.service import Runtime, Service
from slipp.services.discovery import discover_and_enrich, filter_services, find_service
from slipp.utils.errors import AmbiguousServiceError, HostNotFoundError
from slipp.utils.identifiers import parse_service_identifier

DryRunOption = Annotated[
    bool,
    typer.Option("--dry-run", help="Show what would be done without making changes"),
]


def resolve_host_or_exit(
    service: str | None = None,
    project: str | None = None,
    *,
    command: str = "exec",
) -> AnsibleHost:
    """Resolve host (service → project → cwd), printing errors and exiting on failure.

    Args:
        service: Optional service identifier
        project: Optional project name
        command: Command name used in disambiguation suggestions

    Returns:
        Resolved AnsibleHost

    Raises:
        typer.Exit: If resolution fails or is ambiguous
    """
    from slipp.services.config import HostResolver

    try:
        return HostResolver().resolve(service=service, project=project)
    except HostNotFoundError as e:
        output.error(str(e))
        raise typer.Exit(1)
    except AmbiguousServiceError as e:
        output.error(str(e))
        output.suggestions("Specify target:", e.get_suggestions(command=command))
        raise typer.Exit(1)


def find_service_or_exit(
    ssh_config: AnsibleHost, identifier: str, *, include_system: bool = False
) -> Service:
    """Find a service on a host, showing available services and exiting if not found.

    Args:
        ssh_config: Host to discover services on
        identifier: Service identifier to look up
        include_system: Include system services (systemd-*, getty@, etc.)

    Returns:
        Matched Service

    Raises:
        typer.Exit: If the service is not found
    """
    services = discover_and_enrich(ssh_config, include_system=include_system)
    filtered = filter_services(services, show_all=include_system)

    service = find_service(filtered, identifier)
    if not service:
        _show_service_not_found_error(
            identifier,
            ssh_config.ansible_host,
            filter_services(services, show_all=True),
        )
        raise typer.Exit(1)

    return service


def _get_project_root(project_name: str) -> Path:
    """Get project root path from registry, falling back to discovery.

    Args:
        project_name: Name of the project to look up

    Returns:
        Project root path from registry, or the enclosing project found by
        walking up from cwd (or cwd itself) if not found
    """
    from slipp.services.config import LocalConfigService
    from slipp.services.registry import ProjectRegistry

    project = ProjectRegistry().get(project_name)
    if project:
        return project.project_path
    return LocalConfigService.resolve_root()


def _resolve_runtime(host: str | None) -> Runtime:
    """Resolve project root and detect its runtime.

    Args:
        host: Optional project name (defaults to cwd if not given)

    Returns:
        The detected Runtime

    Raises:
        RuntimeDetectionError: If runtime detection fails
    """
    from slipp.services.config import LocalConfigService, RuntimeDetector

    project_root = (
        _get_project_root(host) if host else LocalConfigService.resolve_root()
    )
    return RuntimeDetector(project_root).detect()


def require_container_runtime(project: str | None, *, action: str) -> Runtime:
    """Resolve the project's runtime, exiting with an error if it's not a container.

    Args:
        project: Optional project name (defaults to cwd if not given)
        action: Verb phrase for the error message, e.g. "list" or "push to"

    Returns:
        The resolved container Runtime (docker/podman)

    Raises:
        typer.Exit: If the project runtime isn't a container runtime
    """
    runtime = _resolve_runtime(project)
    if not runtime.is_container():
        output.error(
            f"Project runtime is '{runtime}' -- no container images to {action}"
        )
        raise typer.Exit(1)
    return runtime


def display_services_table(
    services: list[Service],
    *,
    include_project: bool = True,
    include_ip: bool = True,
    include_host: bool = True,
) -> None:
    """Consistent table formatting across all commands.

    Displays services in a table format with configurable columns.
    Always includes: service, runtime, state, uptime
    Optional columns: project, host (inventory_hostname), ip (ansible_host)

    Args:
        services: List of services to display
        include_project: Include project column (default: True)
        include_ip: Include IP address column (default: True)
        include_host: Include inventory hostname column (default: True)

    Example:
        >>> # Full table with all columns
        >>> display_services_table(services)
        >>>
        >>> # Minimal table (no project or IP)
        >>> display_services_table(services, include_project=False, include_ip=False)
    """
    if not services:
        output.info("No services found")
        return

    service_dicts = []
    for s in services:
        row = {}

        if include_project:
            row["project"] = ", ".join(s.projects) if s.projects else "-"

        row["service"] = s.name

        if include_host:
            row["host"] = s.inventory_hostname
        if include_ip:
            row["ip"] = s.host

        row["runtime"] = s.runtime.value
        row["state"] = s.state.value
        row["uptime"] = s.uptime or "-"

        service_dicts.append(row)

    output.table(service_dicts)


def _show_service_not_found_error(
    service_identifier: str,
    host: str,
    available_services: list[Service],
) -> None:
    """Display service not found error with available services list.

    Shows an error message, suggests similar services, and lists available
    services to help the user find the correct service name.

    Args:
        service_identifier: Service identifier that was not found
        host: Host where the service was searched
        available_services: List of available services on the host

    Example:
        >>> _show_service_not_found_error("synapze", "83.143.80.248", services)
        # Displays:
        # ✗ Service 'synapze' not found on 83.143.80.248
        # ℹ Did you mean: matrix-synapse?
        # ⚠ Available services:
        #   • matrix-synapse (active)
        #   ...
    """
    from slipp.utils.matching import get_suggestions

    service_name, _, _ = parse_service_identifier(service_identifier)
    output.error(f"Service '{service_name}' not found on {host}")

    service_names = [s.name for s in available_services]
    suggestions = get_suggestions(service_name, service_names)
    if suggestions:
        output.hint(f"Did you mean: {', '.join(suggestions)}?")

    output.warning("Available services:")

    output.list_items([f"{s.name} ({s.state.value})" for s in available_services[:20]])

    if len(available_services) > 20:
        output.info(
            f"... and {len(available_services) - 20} more (use --all to see system services)"
        )
