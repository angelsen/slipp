"""Services package for slipp.

This module provides a facade for commonly used services.
For full access to all exports, import from subpackages directly:
- slipp.services.ssh
- slipp.services.vault
- slipp.services.discovery
- slipp.services.config
- slipp.services.registry
- slipp.services.run
- slipp.services.ansible
"""

from slipp.services.ssh import SSHService, TunnelManager
from slipp.services.discovery import DiscoveryService, ServiceLocator
from slipp.services.config import HostResolver, LocalConfigService
from slipp.services.registry import ProjectRegistry
from slipp.services.run import RunProfileExecutor, RunProfileService

__all__ = [
    "SSHService",
    "TunnelManager",
    "DiscoveryService",
    "ServiceLocator",
    "HostResolver",
    "LocalConfigService",
    "ProjectRegistry",
    "RunProfileExecutor",
    "RunProfileService",
]
