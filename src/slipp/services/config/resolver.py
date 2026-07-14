"""Config resolver - unified configuration resolution with precedence chain.

Resolution order:
1. CLI flags (highest priority)
2. Local config (./slipp.yaml)
3. Defaults (playbook.yml, inventory.yml)
"""

from dataclasses import dataclass
from pathlib import Path

from slipp.constants import (
    DEFAULT_ENV,
    DEFAULT_GALAXY_PATH,
    PLAYBOOK_FILENAME,
    get_inventory_filename,
)
from slipp.models.local_config import LocalConfig
from slipp.services.config.detection import (
    INVENTORY_PATTERNS,
    PLAYBOOK_PATTERNS,
    detect_path,
)
from slipp.services.config.local import LocalConfigService
from slipp.services.registry import ProjectRegistry
from slipp.utils.errors import ProjectNameRequiredError, ProjectNotFoundError


def _resolve_cli_path(value: str) -> Path:
    """Anchor a CLI flag path (-i/--playbook/--roles/--vault) to the actual
    process cwd, resolving it to an absolute path.

    CLI flags are relative-to-cwd by normal CLI convention, but the Ansible
    subprocess this eventually feeds runs with cwd=project_root (see
    services/ansible/ansible.py run_playbook), which can now differ from the
    process cwd once project_root is discovered by walking up from a
    subdirectory. Leaving the path relative would silently resolve it
    against the wrong directory.
    """
    return Path(value).resolve()


def _resolve_path(
    cli_value: str | None,
    local_value: str | None,
    project_root: Path,
    patterns: list[str],
    fallback: Path,
) -> tuple[Path, str]:
    """Resolve a single config path with precedence: CLI > local > detected/default."""
    if cli_value:
        return _resolve_cli_path(cli_value), "cli"
    if local_value:
        return project_root / local_value, "local"
    detected = detect_path(project_root, patterns)
    return detected or fallback, "default"


def resolve_project_name(cli_name: str | None = None) -> str:
    """Resolve project name with strict requirements - no cwd fallback.

    Priority:
    1. CLI --name flag (if provided)
    2. Local config name field (if exists)
    3. ERROR - no fallback to cwd().name

    Args:
        cli_name: Project name from CLI flag (highest priority)

    Returns:
        Resolved project name

    Raises:
        ProjectNameRequiredError: If no name configured anywhere
    """
    if cli_name:
        return cli_name

    config = LocalConfigService.load(LocalConfigService.find_root())
    if config and config.name:
        return config.name

    raise ProjectNameRequiredError()


def resolve_vault_target(target: str | None) -> tuple["ConfigResolver", Path | None]:
    """Resolve a vault target to (resolver, vault path).

    Resolution order:
    1. If target is an existing file path → that file directly (resolver bound to cwd)
    2. If target is a project name → that project's configured vault
    3. If target is None → cwd config's vault

    Args:
        target: Vault file path, project name, or None

    Returns:
        Tuple of (ConfigResolver for the project context, vault Path or None)

    Raises:
        ProjectNotFoundError: If target names an unregistered project
    """
    if target and Path(target).is_file():
        return ConfigResolver(), Path(target)

    resolver = ConfigResolver.for_project(target) if target else ConfigResolver()
    return resolver, resolver.resolve_vault()


@dataclass
class ResolvedConfig:
    """Resolved configuration with source tracking.

    Attributes:
        inventory: Resolved inventory path
        playbook: Resolved playbook path
        roles_path: Role directories (sets ANSIBLE_ROLES_PATH)
        galaxy_path: Resolved install path for ansible-galaxy
        vault: Resolved vault path (may be None)
        inventory_source: Where inventory was resolved from
        playbook_source: Where playbook was resolved from
    """

    inventory: Path
    playbook: Path
    roles_path: list[Path]
    galaxy_path: Path
    vault: Path | None
    inventory_source: str  # "cli", "local", "default"
    playbook_source: str


class ConfigResolver:
    """Resolve configuration from CLI flags, local config, or defaults.

    Usage:
        resolver = ConfigResolver()
        config = resolver.resolve(
            cli_inventory="inventory/hosts",
            cli_playbook=None,
            cli_roles=["roles/custom"],
            cli_vault=None,
        )
        config.inventory       # Path to inventory
        config.inventory_source  # "cli" or "local" or "default"
    """

    def __init__(self, project_root: Path | None = None):
        """Initialize ConfigResolver.

        Args:
            project_root: Project root directory (defaults to the enclosing
                project found by walking up from cwd, or cwd itself if none)
        """
        self.project_root = project_root or LocalConfigService.resolve_root()
        self._local_config = LocalConfigService.load(self.project_root)

    @classmethod
    def for_project(cls, project_name: str) -> "ConfigResolver":
        """Create resolver for a registered project.

        Looks up project in global registry and creates a ConfigResolver
        bound to that project's root directory.

        Args:
            project_name: Name of registered project

        Returns:
            ConfigResolver bound to project's root

        Raises:
            ProjectNotFoundError: If project not in registry
        """
        registry = ProjectRegistry()
        project = registry.get(project_name)
        if not project:
            raise ProjectNotFoundError(f"Project '{project_name}' not found")
        return cls(project.project_path)

    def resolve_vault(self, cli_vault: str | None = None) -> Path | None:
        """Resolve vault path with precedence: CLI > local config.

        Args:
            cli_vault: Vault path from CLI flag (overrides config)

        Returns:
            Resolved vault Path or None if not configured
        """
        if cli_vault:
            return _resolve_cli_path(cli_vault)
        if self._local_config and self._local_config.vault:
            return self.project_root / self._local_config.vault
        return None

    @property
    def has_local_config(self) -> bool:
        """Check if local slipp.yaml exists."""
        return self._local_config is not None

    @property
    def local_config(self) -> LocalConfig | None:
        """Get local config if it exists."""
        return self._local_config

    def resolve(
        self,
        cli_inventory: str | None = None,
        cli_playbook: str | None = None,
        cli_roles: list[str] | None = None,
        cli_vault: str | None = None,
        cli_galaxy_path: str | None = None,
        environment: str = DEFAULT_ENV,
    ) -> ResolvedConfig:
        """Resolve all config values with precedence: CLI > local > default.

        Args:
            cli_inventory: Inventory from CLI flag
            cli_playbook: Playbook from CLI flag
            cli_roles: Roles from CLI flag
            cli_vault: Vault from CLI flag
            cli_galaxy_path: Galaxy install path from CLI flag
            environment: Environment name for default inventory filename

        Returns:
            ResolvedConfig with all paths and source tracking
        """
        inventory, inv_source = _resolve_path(
            cli_inventory,
            self._local_config.inventory if self._local_config else None,
            self.project_root,
            INVENTORY_PATTERNS,
            self.project_root / get_inventory_filename(environment),
        )

        playbook, pb_source = _resolve_path(
            cli_playbook,
            self._local_config.playbook if self._local_config else None,
            self.project_root,
            PLAYBOOK_PATTERNS,
            self.project_root / PLAYBOOK_FILENAME,
        )

        # roles_path/galaxy_path don't go through _resolve_path: that helper's
        # detect_path step exists to auto-discover a *file* by name pattern
        # (playbook.yml, inventory.yml), which doesn't apply here -- roles_path
        # is a list rather than a single value, and galaxy_path's fallback is
        # a fixed conventional directory, not something to search for. Neither
        # gets source tracking either, since nothing currently consumes it
        # (unlike inventory/playbook, logged in deploy/runner.py).
        if cli_roles:
            roles_path = [_resolve_cli_path(r) for r in cli_roles]
        elif self._local_config and self._local_config.roles_path:
            roles_path = [self.project_root / r for r in self._local_config.roles_path]
        else:
            roles_path = []

        if cli_galaxy_path:
            galaxy_path = _resolve_cli_path(cli_galaxy_path)
        elif self._local_config and self._local_config.galaxy_path:
            galaxy_path = self.project_root / self._local_config.galaxy_path
        else:
            galaxy_path = self.project_root / DEFAULT_GALAXY_PATH

        vault = self.resolve_vault(cli_vault)

        return ResolvedConfig(
            inventory=inventory,
            playbook=playbook,
            roles_path=roles_path,
            galaxy_path=galaxy_path,
            vault=vault,
            inventory_source=inv_source,
            playbook_source=pb_source,
        )
