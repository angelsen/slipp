"""Service discovery and lookup services.

This package provides services for discovering and locating services on remote hosts.
"""

from slipp.services.discovery.discovery import (
    discover_across_hosts,
    discover_and_enrich,
    extract_status_log_lines,
    filter_services,
    find_service,
    parse_systemctl_status,
)
from slipp.services.discovery.registry import ServiceRegistry

__all__ = [
    "discover_across_hosts",
    "discover_and_enrich",
    "extract_status_log_lines",
    "filter_services",
    "find_service",
    "parse_systemctl_status",
    "ServiceRegistry",
]
