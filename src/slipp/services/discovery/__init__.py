"""Service discovery and lookup services.

This package provides services for discovering and locating services on remote hosts.
"""

from slipp.services.discovery.discovery import (
    discover_and_enrich,
    filter_services,
    find_service,
)
from slipp.services.discovery.registry import ServiceRegistry

__all__ = [
    "discover_and_enrich",
    "filter_services",
    "find_service",
    "ServiceRegistry",
]
