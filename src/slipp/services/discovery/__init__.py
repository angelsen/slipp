"""Service discovery and lookup services.

This package provides services for discovering and locating services on remote hosts.
"""

from slipp.services.discovery.discovery import (
    discover_across_hosts,
    discover_and_enrich,
)
from slipp.services.discovery.filtering import filter_services, find_service
from slipp.services.discovery.lookup import lookup_host_by_service

__all__ = [
    "discover_across_hosts",
    "discover_and_enrich",
    "filter_services",
    "find_service",
    "lookup_host_by_service",
]
