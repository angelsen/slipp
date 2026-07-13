"""Registry I/O operations - loading and saving the global registry.

This module handles all file system operations for the global project registry.
The registry is now a simple path index - hosts are loaded on-demand from local configs.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from slipp.models.registry import GlobalRegistry
from slipp.utils.config_store import (
    config_store_lock,
    load_model,
    save_model,
    slipp_config_dir,
)


class RegistryIO:
    """Handles loading and saving the global registry file."""

    @staticmethod
    def _get_config_path() -> Path:
        """Path to the registry file (e.g., ~/.config/slipp/config.json)."""
        return slipp_config_dir() / "config.json"

    @staticmethod
    @contextmanager
    def lock() -> Iterator[None]:
        """Exclusive lock guarding read-modify-write access to the registry."""
        with config_store_lock(RegistryIO._get_config_path()):
            yield

    @staticmethod
    def load() -> GlobalRegistry:
        """Load registry from disk (empty if missing or corrupted)."""
        return load_model(
            RegistryIO._get_config_path(),
            GlobalRegistry,
            default=GlobalRegistry(),
            label="Registry",
        )

    @staticmethod
    def save(registry: GlobalRegistry) -> None:
        """Save registry with atomic write."""
        save_model(RegistryIO._get_config_path(), registry)
