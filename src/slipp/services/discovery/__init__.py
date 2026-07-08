"""Service discovery and lookup services.

This package provides services for discovering and locating services on remote hosts.

Note: pipeline.py (discover_across_hosts, discover_and_enrich, etc.) is
intentionally NOT re-exported here. It depends on services.config
(HostResolver), and this package is imported by services.config.hosts
(lookup_host_by_service) -- re-exporting pipeline from this __init__ would
reintroduce that cycle. Import pipeline functions directly from
slipp.services.discovery.pipeline.
"""

from slipp.services.discovery.filtering import filter_services, find_service
from slipp.services.discovery.lookup import lookup_host_by_service

__all__ = [
    "filter_services",
    "find_service",
    "lookup_host_by_service",
]
