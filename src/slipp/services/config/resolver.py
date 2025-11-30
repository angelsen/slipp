"""Config resolver - unified configuration resolution with precedence chain.

Resolution order:
1. CLI flags (highest priority)
2. Local config (./slipp.yaml)
3. Defaults (playbook.yml, inventory.yml)
"""

from dataclasses import dataclass
from pathlib import Path

from slipp.constants import PLAYBOOK_FILENAME, get_inventory_filename
from slipp.models.local_config import LocalConfig
from slipp.services.config.local import LocalConfigService
from slipp.utils.errors import ProjectNameRequiredError, ProjectNotFoundError


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

    config = LocalConfigService.load()
    if config and config.name:
        return config.name

    raise ProjectNameRequiredError()


@dataclass
class ResolvedConfig:
    """Resolved configuration with source tracking.

    Attributes:
        inventory: Resolved inventory path
        playbook: Resolved playbook path
        roles: Resolved role directories
        vault: Resolved vault path (may be None)
        managed_roles: Role names for service filtering
        inventory_source: Where inventory was resolved from
        playbook_source: Where playbook was resolved from
        roles_source: Where roles was resolved from
    """

    inventory: Path
    playbook: Path
    roles: list[Path]
    vault: Path | None
    managed_roles: list[str]
    inventory_source: str  # "cli", "local", "default"
    playbook_source: str
    roles_source: str


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
        print(config.inventory)  # Path to inventory
        print(config.inventory_source)  # "cli" or "local" or "default"
    """

    def __init__(self, project_root: Path | None = None):
        """Initialize ConfigResolver.

        Args:
            project_root: Project root directory (defaults to cwd)
        """
        self.project_root = project_root or Path.cwd()
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
        from slipp.services.registry import ProjectRegistry

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
            return Path(cli_vault)
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
        environment: str = "production",
    ) -> ResolvedConfig:
        """Resolve all config values with precedence: CLI > local > default.

        Args:
            cli_inventory: Inventory from CLI flag
            cli_playbook: Playbook from CLI flag
            cli_roles: Roles from CLI flag
            cli_vault: Vault from CLI flag
            environment: Environment name for default inventory filename

        Returns:
            ResolvedConfig with all paths and source tracking
        """
        if cli_inventory:
            inventory = Path(cli_inventory)
            inv_source = "cli"
        elif self._local_config and self._local_config.inventory:
            inventory = self.project_root / self._local_config.inventory
            inv_source = "local"
        else:
            inventory = self.project_root / get_inventory_filename(environment)
            inv_source = "default"

        if cli_playbook:
            playbook = Path(cli_playbook)
            pb_source = "cli"
        elif self._local_config and self._local_config.playbook:
            playbook = self.project_root / self._local_config.playbook
            pb_source = "local"
        else:
            playbook = self.project_root / PLAYBOOK_FILENAME
            pb_source = "default"

        if cli_roles:
            roles = [Path(r) for r in cli_roles]
            roles_source = "cli"
        elif self._local_config and self._local_config.roles:
            roles = [self.project_root / r for r in self._local_config.roles]
            roles_source = "local"
        else:
            roles = []
            roles_source = "default"

        if cli_vault:
            vault = Path(cli_vault)
        elif self._local_config and self._local_config.vault:
            vault = self.project_root / self._local_config.vault
        else:
            vault = None

        managed_roles = self._local_config.managed_roles if self._local_config else []

        return ResolvedConfig(
            inventory=inventory,
            playbook=playbook,
            roles=roles,
            vault=vault,
            managed_roles=managed_roles,
            inventory_source=inv_source,
            playbook_source=pb_source,
            roles_source=roles_source,
        )
