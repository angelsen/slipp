"""Presentation utilities for commands.

This module contains display/formatting functions shared across commands.
Business logic (filtering, discovery, lookups) is in services/discovery.py.
"""

from slipp import output
from slipp.models.service import Service
from slipp.services.discovery import extract_service_name


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

    print()

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


def show_service_not_found_error(
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
        >>> show_service_not_found_error("synapze", "83.143.80.248", services)
        # Displays:
        # ✗ Service 'synapze' not found on 83.143.80.248
        # ℹ Did you mean: matrix-synapse?
        # ⚠ Available services:
        #   • matrix-synapse (active)
        #   ...
    """
    from slipp.utils.matching import get_suggestions

    service_name = extract_service_name(service_identifier)
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
