"""Provision state persistence — ~/.config/slipp/provisions/<name>.yaml."""

import logging
import os
import shutil
from pathlib import Path

import yaml

from slipp.models.provision import ProvisionState
from slipp.utils.files import atomic_write_text

logger = logging.getLogger(__name__)


class ProvisionStateService:
    """Handles load/save/delete of in-progress provision state files."""

    @staticmethod
    def _get_provisions_dir() -> Path:
        xdg_config = os.getenv("XDG_CONFIG_HOME")
        if xdg_config:
            config_dir = Path(xdg_config) / "slipp"
        else:
            config_dir = Path.home() / ".config" / "slipp"

        provisions_dir = config_dir / "provisions"
        provisions_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        return provisions_dir

    @staticmethod
    def save(state: ProvisionState) -> None:
        """Atomic YAML write with 0o600 permissions."""
        path = ProvisionStateService._get_provisions_dir() / f"{state.name}.yaml"
        data = state.model_dump(mode="json")
        content = yaml.dump(data, default_flow_style=False, sort_keys=False)
        atomic_write_text(path, content, mode=0o600)

    @staticmethod
    def load(name: str) -> ProvisionState | None:
        """Load by name. Returns None if missing, warns on corruption."""
        path = ProvisionStateService._get_provisions_dir() / f"{name}.yaml"
        if not path.exists():
            return None

        try:
            data = yaml.safe_load(path.read_text()) or {}
            return ProvisionState(**data)
        except yaml.YAMLError as e:
            backup_path = path.with_suffix(".yaml.backup")
            shutil.copy(path, backup_path)
            logger.warning(
                f"Provision state corrupted: {e}. Backed up to: {backup_path}"
            )
            return None
        except Exception as e:
            logger.warning(f"Failed to load provision state for '{name}': {e}")
            return None

    @staticmethod
    def delete(name: str) -> None:
        """Remove state file. No-op if already gone."""
        path = ProvisionStateService._get_provisions_dir() / f"{name}.yaml"
        path.unlink(missing_ok=True)
