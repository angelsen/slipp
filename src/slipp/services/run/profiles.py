"""Run profile persistence, inheritance, and lifecycle management.

Profiles are stored in slipp.yaml under `runs:` (git-tracked), with
personal overrides in `.slipp/runs.local.yaml` (untracked, not created
automatically) and read-only fallback support for the legacy
`.slipp/runs.yaml` (deprecated).
"""

from pathlib import Path
from typing import Any

import yaml

from slipp import output
from slipp.models.local_config import LocalConfig
from slipp.models.run import RunProfile
from slipp.services.config.local import LocalConfigService
from slipp.utils.errors import ConfigError, ProfileNotFoundError

LEGACY_RUNS_FILENAME = ".slipp/runs.yaml"
LOCAL_RUNS_FILENAME = ".slipp/runs.local.yaml"


def _load_raw_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file as a raw dict, tolerating a missing or invalid file."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


class RunProfileService:
    """Manage run profile persistence, inheritance, and queries."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self._raw_cache: dict[str, dict[str, Any]] | None = None

    def _legacy_path(self) -> Path:
        return self.project_root / LEGACY_RUNS_FILENAME

    def _local_path(self) -> Path:
        return self.project_root / LOCAL_RUNS_FILENAME

    def _raw_profiles(self) -> dict[str, dict[str, Any]]:
        """Union of all profile sources: local overrides tracked overrides legacy.

        Cached per instance so a single command invocation (which typically
        checks existence then fetches) only reads disk and warns once.
        """
        if self._raw_cache is not None:
            return self._raw_cache

        raw: dict[str, dict[str, Any]] = {}

        legacy = _load_raw_yaml(self._legacy_path())
        if legacy:
            output.warning(
                f"{LEGACY_RUNS_FILENAME} is deprecated — "
                "move profiles to slipp.yaml under 'runs:'"
            )
            raw.update(legacy)

        config = LocalConfigService.load(self.project_root)
        if config and config.runs:
            raw.update(config.runs)

        local = _load_raw_yaml(self._local_path())
        if local:
            raw.update(local)

        self._raw_cache = raw
        return raw

    def _resolve(self, name: str, raw: dict[str, dict[str, Any]]) -> RunProfile:
        """Resolve a profile's `extends` chain into a validated RunProfile."""
        chain: list[str] = []
        seen: set[str] = set()
        current = name

        while True:
            if current not in raw:
                if current == name:
                    raise ProfileNotFoundError(f"Profile '{name}' not found")
                raise ConfigError(
                    f"Profile '{name}' extends unknown profile '{current}'"
                )
            if current in seen:
                raise ConfigError(
                    f"Profile '{name}' has a cycle in 'extends' (via '{current}')"
                )
            seen.add(current)
            chain.append(current)

            parent = raw[current].get("extends")
            if not parent:
                break
            current = parent

        merged: dict[str, Any] = {}
        for profile_name in reversed(chain):
            merged.update(
                {k: v for k, v in raw[profile_name].items() if k != "extends"}
            )

        return RunProfile.model_validate(merged)

    def save_profile(self, name: str, profile: RunProfile) -> None:
        """Save or update a run profile in slipp.yaml."""
        config = LocalConfigService.load(self.project_root) or LocalConfig(
            name=self.project_root.name
        )
        runs = dict(config.runs)
        runs[name] = profile.model_dump(
            by_alias=True, exclude_none=True, exclude_defaults=True
        )
        updated = config.model_copy(update={"runs": runs})
        LocalConfigService.save(updated, self.project_root)
        self._raw_cache = None

    def get_profile(self, name: str) -> RunProfile:
        """Return a resolved run profile by name.

        Raises:
            ProfileNotFoundError: If the profile does not exist.
            ConfigError: If the profile's `extends` chain is broken.
        """
        return self._resolve(name, self._raw_profiles())

    def list_profiles(self) -> dict[str, RunProfile]:
        """Return all resolved run profiles, skipping ones with a broken chain."""
        raw = self._raw_profiles()
        resolved: dict[str, RunProfile] = {}
        for name in raw:
            try:
                resolved[name] = self._resolve(name, raw)
            except ConfigError as e:
                output.warning(f"Skipping profile '{name}': {e}")
        return resolved

    def delete_profile(self, name: str) -> None:
        """Delete a run profile from slipp.yaml.

        Raises:
            ProfileNotFoundError: If the profile isn't in slipp.yaml (it may
                still exist in a legacy or local override file).
        """
        config = LocalConfigService.load(self.project_root)
        if config and name in config.runs:
            runs = dict(config.runs)
            del runs[name]
            updated = config.model_copy(update={"runs": runs})
            LocalConfigService.save(updated, self.project_root)
            self._raw_cache = None
            return

        if name in _load_raw_yaml(self._legacy_path()):
            raise ProfileNotFoundError(
                f"Profile '{name}' is defined in the legacy {LEGACY_RUNS_FILENAME} — "
                "move it to slipp.yaml under 'runs:' to manage it here, "
                "or edit the file directly"
            )
        if name in _load_raw_yaml(self._local_path()):
            raise ProfileNotFoundError(
                f"Profile '{name}' is defined in {LOCAL_RUNS_FILENAME} — "
                "edit that file directly to remove it"
            )
        raise ProfileNotFoundError(f"Profile '{name}' not found")

    def profile_exists(self, name: str) -> bool:
        """Check whether a profile exists in any layer."""
        return name in self._raw_profiles()
