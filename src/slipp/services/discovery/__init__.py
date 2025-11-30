"""Service discovery and lookup services.

This package provides services for discovering and locating services on remote hosts.
"""

from slipp.services.discovery.discovery import (
    DiscoveryService,
    discover_and_enrich,
    extract_service_name,
    filter_services,
    find_service,
)
from slipp.services.discovery.locator import ServiceLocator
from slipp.services.discovery.registry import ServiceRegistry

__all__ = [
    "DiscoveryService",
    "discover_and_enrich",
    "extract_service_name",
    "filter_services",
    "find_service",
    "ServiceLocator",
    "ServiceRegistry",
]
