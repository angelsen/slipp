"""Configuration management services.

This package provides services for managing configuration, inventory, and host resolution.
"""

from slipp.services.config.hosts import HostResolver
from slipp.services.config.inventory import InventoryService, load_project_hosts
from slipp.services.config.local import LocalConfigService, collect_managed_roles
from slipp.services.config.presets import PresetResolver, parse_preset_args
from slipp.services.config.resolver import (
    ConfigResolver,
    ResolvedConfig,
    resolve_project_name,
    resolve_vault_target,
)
from slipp.services.config.runtime import RuntimeDetectionError, RuntimeDetector

__all__ = [
    "LocalConfigService",
    "collect_managed_roles",
    "InventoryService",
    "load_project_hosts",
    "ConfigResolver",
    "ResolvedConfig",
    "resolve_project_name",
    "resolve_vault_target",
    "PresetResolver",
    "parse_preset_args",
    "HostResolver",
    "RuntimeDetector",
    "RuntimeDetectionError",
]
