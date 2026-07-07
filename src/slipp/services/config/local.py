"""Local config service - loading and saving slipp.yaml files.

This module handles all file system operations for local project configuration.
Similar to RegistryIO but for local slipp.yaml files.
"""

from pathlib import Path
from typing import Any

import yaml

from slipp import output
from slipp.models.local_config import LocalConfig
from slipp.utils.errors import ConfigParseError
from slipp.utils.files import atomic_write_text

CONFIG_FILENAME = "slipp.yaml"


class LocalConfigService:
    """Handles loading and saving local slipp.yaml files.

    Responsibilities:
    - Load config from project root
    - Save config with YAML formatting
    - Check if config exists
    - Auto-create .gitignore for logs directory
    """

    @staticmethod
    def get_config_path(project_root: Path | None = None) -> Path:
        """Get path to slipp.yaml.

        Exact-dir semantics only -- never walks up. Use find_root()/
        resolve_root() at the caller for subdirectory discovery.

        Args:
            project_root: Project root directory (defaults to cwd)

        Returns:
            Path to slipp.yaml file
        """
        root = project_root or Path.cwd()
        return root / CONFIG_FILENAME

    @staticmethod
    def find_root(start: Path | None = None) -> Path | None:
        """Walk upward from start looking for a directory with slipp.yaml.

        Checks the file's presence only, never its parseability -- a corrupt
        slipp.yaml in the starting directory binds to that directory rather
        than silently falling through to a parent's config.

        This is opt-in discovery for read/resolution call sites. Anything
        that creates or gates on "is a project already configured here"
        (projects add, ensure_local_config's create-vs-update check, scaffold/
        launch registration) must NOT use this -- it must bind to an explicit
        directory (typically cwd), or a walk could silently write into an
        enclosing project's slipp.yaml.

        Args:
            start: Directory to start searching from (defaults to cwd)

        Returns:
            First ancestor (inclusive) containing slipp.yaml, or None if not
            found before the filesystem root.
        """
        current = (start or Path.cwd()).resolve()
        for candidate in (current, *current.parents):
            if (candidate / CONFIG_FILENAME).is_file():
                return candidate
        return None

    @staticmethod
    def resolve_root(start: Path | None = None) -> Path:
        """Find the enclosing project root, falling back to start/cwd.

        Convenience wrapper around find_root() for the common case: read
        resolution should walk up when possible, but behave exactly like
        today (bind to cwd) when no slipp.yaml exists anywhere above it.

        Args:
            start: Directory to start searching from (defaults to cwd)

        Returns:
            Discovered project root, or start/cwd if none found
        """
        return LocalConfigService.find_root(start) or (start or Path.cwd())

    @staticmethod
    def exists(project_root: Path | None = None) -> bool:
        """Check if local config exists.

        Args:
            project_root: Project root directory (defaults to cwd)

        Returns:
            True if slipp.yaml exists
        """
        return LocalConfigService.get_config_path(project_root).exists()

    @staticmethod
    def load(project_root: Path | None = None) -> LocalConfig | None:
        """Load config from slipp.yaml if it exists.

        Args:
            project_root: Project root directory (defaults to cwd)

        Returns:
            LocalConfig if file exists and is valid, None otherwise
        """
        config_path = LocalConfigService.get_config_path(project_root)

        if not config_path.exists():
            return None

        try:
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            return LocalConfig(**data)
        except Exception as e:
            output.warning(f"Ignoring invalid {config_path}: {e}")
            return None

    @staticmethod
    def create(
        name: str,
        inventory_path: str,
        playbook_path: str = "playbook.yml",
        roles_path: list[str] | None = None,
        galaxy_path: str | None = None,
        vault_path: str | None = None,
        project_root: Path | None = None,
    ) -> LocalConfig:
        """Create a new local config.

        Never discovers a root -- callers creating a config must pass an
        explicit project_root (or intend cwd). Using resolve_root() here
        could silently overwrite an enclosing project's slipp.yaml.

        Args:
            name: Project identifier (required)
            inventory_path: Relative path to inventory
            playbook_path: Relative path to playbook
            roles_path: Role directories for ansible --roles-path
            galaxy_path: Install path for ansible-galaxy
            vault_path: Optional vault file path
            project_root: Project root (defaults to cwd)

        Returns:
            Created LocalConfig
        """
        from slipp.services.config.inventory import InventoryService

        root = project_root or Path.cwd()

        managed_roles: list[str] = []
        roles_list = roles_path or []
        if roles_list:
            managed_roles = InventoryService.scan_roles_from_directories(
                roles_list, root
            )

        config = LocalConfig(
            name=name,
            inventory=inventory_path,
            playbook=playbook_path,
            roles_path=roles_list,
            galaxy_path=galaxy_path,
            vault=vault_path,
            managed_roles=managed_roles,
        )

        LocalConfigService.save(config, root)
        return config

    @staticmethod
    def update(
        changes: dict[str, Any],
        project_root: Path | None = None,
    ) -> LocalConfig:
        """Update existing local config.

        Args:
            changes: Dict of field -> value to update
            project_root: Project root (defaults to cwd)

        Returns:
            Updated LocalConfig

        Raises:
            ConfigParseError: If config doesn't exist or is invalid
        """
        from slipp.services.config.inventory import InventoryService

        root = project_root or Path.cwd()
        config = LocalConfigService.load(root)

        if config is None:
            raise ConfigParseError(f"No slipp.yaml found in {root}")

        updated = config.model_copy(update=changes)

        if "roles_path" in changes and changes["roles_path"]:
            updated.managed_roles = InventoryService.scan_roles_from_directories(
                changes["roles_path"], root
            )

        LocalConfigService.save(updated, root)
        return updated

    @staticmethod
    def save(config: LocalConfig, project_root: Path | None = None) -> Path:
        """Save config to slipp.yaml.

        Args:
            config: LocalConfig to save
            project_root: Project root directory (defaults to cwd)

        Returns:
            Path to saved file
        """
        config_path = LocalConfigService.get_config_path(project_root)

        data = config.model_dump(exclude_none=True)

        if not data.get("roles_path"):
            data.pop("roles_path", None)
        if not data.get("galaxy_path"):
            data.pop("galaxy_path", None)
        if not data.get("managed_roles"):
            data.pop("managed_roles", None)
        if not data.get("tag_presets"):
            data.pop("tag_presets", None)
        if not data.get("runtime"):
            data.pop("runtime", None)
        if not data.get("runs"):
            data.pop("runs", None)

        ordered_data: dict[str, Any] = {}
        field_order = [
            "name",
            "inventory",
            "playbook",
            "roles_path",
            "galaxy_path",
            "vault",
            "runtime",
            "managed_roles",
            "tag_presets",
            "runs",
        ]
        for field in field_order:
            if field in data:
                ordered_data[field] = data[field]

        content = (
            "# slipp.yaml - Project configuration (git-tracked)\n"
            "# Generated by slipp. Edit manually or use flags.\n\n"
            + yaml.dump(ordered_data, default_flow_style=False, sort_keys=False)
        )
        atomic_write_text(config_path, content)

        return config_path

    @staticmethod
    def ensure_logs_gitignore(project_root: Path | None = None) -> None:
        """Ensure .slipp/logs/.gitignore exists.

        Creates the .gitignore file if the logs directory exists.
        Content: ignore all files except .gitignore itself.

        Args:
            project_root: Project root directory (defaults to cwd)
        """
        root = project_root or Path.cwd()
        logs_dir = root / ".slipp" / "logs"
        gitignore = logs_dir / ".gitignore"

        if logs_dir.exists() and not gitignore.exists():
            gitignore.write_text("*\n!.gitignore\n")
