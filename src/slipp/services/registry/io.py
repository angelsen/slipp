"""Registry I/O operations - loading and saving the global registry.

This module handles all file system operations for the global project registry.
The registry is now a simple path index - hosts are loaded on-demand from local configs.
"""

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from slipp.models.registry import GlobalRegistry, RegisteredProject

logger = logging.getLogger(__name__)


class RegistryIO:
    """Handles loading and saving the global registry file.

    Responsibilities:
    - Config file path resolution (XDG spec)
    - Atomic file writes
    - JSON serialization/deserialization
    - Corruption recovery (backup)
    """

    @staticmethod
    def _get_config_path() -> Path:
        """Get config file path following XDG spec.

        Returns:
            Path to config.json file (e.g., ~/.config/slipp/config.json)
        """
        xdg_config = os.getenv("XDG_CONFIG_HOME")
        if xdg_config:
            config_dir = Path(xdg_config) / "slipp"
        else:
            config_dir = Path.home() / ".config" / "slipp"

        config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        return config_dir / "config.json"

    @staticmethod
    def load() -> GlobalRegistry:
        """Load registry from disk.

        Returns:
            GlobalRegistry instance (empty if file doesn't exist or corrupted)
        """
        config_file = RegistryIO._get_config_path()

        if not config_file.exists():
            return GlobalRegistry()

        try:
            data = json.loads(config_file.read_text())

            projects = {}
            for name, proj_data in data.get("projects", {}).items():
                projects[name] = RegisteredProject(
                    name=proj_data["name"],
                    project_path=Path(proj_data["project_path"]),
                    registered_at=datetime.fromisoformat(proj_data["registered_at"]),
                )

            return GlobalRegistry(projects=projects)

        except json.JSONDecodeError as e:
            # Backup corrupted file and recover with empty registry
            backup_path = config_file.with_suffix(".json.backup")
            shutil.copy(config_file, backup_path)
            logger.warning(f"Registry corrupted: {e}. Backed up to: {backup_path}")
            return GlobalRegistry()

        except Exception as e:
            logger.warning(f"Failed to load registry: {e}")
            return GlobalRegistry()

    @staticmethod
    def save(registry: GlobalRegistry) -> None:
        """Save registry with atomic write.

        Args:
            registry: GlobalRegistry instance to save

        Raises:
            Exception: If write fails (after cleanup)
        """
        config_file = RegistryIO._get_config_path()
        temp_file = config_file.with_suffix(".json.tmp")

        try:
            temp_file.write_text(
                json.dumps(registry.model_dump(mode="json"), indent=2),
                encoding="utf-8",
            )

            temp_file.replace(config_file)
            config_file.chmod(0o600)

        except Exception:
            if temp_file.exists():
                temp_file.unlink()
            raise
