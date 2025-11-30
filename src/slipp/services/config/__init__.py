"""Configuration management services.

This package provides services for managing configuration, inventory, and host resolution.
"""

from slipp.services.config.hosts import HostResolver
from slipp.services.config.inventory import InventoryService
from slipp.services.config.local import LocalConfigService
from slipp.services.config.presets import PresetResolver, parse_preset_args
from slipp.services.config.resolver import ConfigResolver, resolve_project_name

__all__ = [
    "LocalConfigService",
    "InventoryService",
    "ConfigResolver",
    "resolve_project_name",
    "PresetResolver",
    "parse_preset_args",
    "HostResolver",
]
