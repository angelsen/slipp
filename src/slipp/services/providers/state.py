"""Provision state persistence — ~/.config/slipp/provisions/<name>.yaml."""

from pathlib import Path

from slipp.models.provision import ProvisionState
from slipp.utils.config_store import load_model, save_model, slipp_config_dir


class ProvisionStateService:
    """Handles load/save/delete of in-progress provision state files."""

    @staticmethod
    def _path(name: str) -> Path:
        return slipp_config_dir("provisions") / f"{name}.yaml"

    @staticmethod
    def save(state: ProvisionState) -> None:
        """Atomic YAML write with 0o600 permissions."""
        save_model(ProvisionStateService._path(state.name), state)

    @staticmethod
    def load(name: str) -> ProvisionState | None:
        """Load by name. Returns None if missing, warns on corruption."""
        return load_model(
            ProvisionStateService._path(name),
            ProvisionState,
            default=None,
            label=f"Provision state '{name}'",
        )

    @staticmethod
    def delete(name: str) -> None:
        """Remove state file. No-op if already gone."""
        ProvisionStateService._path(name).unlink(missing_ok=True)
