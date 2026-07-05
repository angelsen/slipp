"""Custom exception hierarchy for slipp.

All slipp operations raise subclasses of SlippError for consistent
error handling across the CLI, services, and commands.
"""


class SlippError(Exception):
    """Base exception for slipp."""

    pass


class SSHConnectionError(SlippError):
    """Failed to establish SSH connection."""

    pass


class SSHAuthenticationError(SlippError):
    """SSH authentication failed."""

    pass


class TunnelError(SlippError):
    """SSH tunnel operation failed."""

    pass


class VaultError(SlippError):
    """Vault operation failed."""

    pass


class VaultNotFoundError(VaultError):
    """Vault file not found."""

    pass


class VaultDecryptError(VaultError):
    """Failed to decrypt vault."""

    pass


class VaultSyncError(VaultError):
    """Vault synchronization failed."""

    pass


class PasswordMismatchError(VaultError):
    """Vault passwords do not match."""

    pass


class DuplicateEnvVarError(VaultError):
    """Duplicate environment variable found across vaults."""

    pass


class ServiceNotFoundError(SlippError):
    """Requested service not found."""

    pass


class HostNotFoundError(SlippError):
    """Requested host not found."""

    pass


class AmbiguousServiceError(SlippError):
    """Multiple services match the query.

    Carries match information for helpful error messages.
    """

    def __init__(self, service: str, matches: list[tuple[str, str, str]]):
        """Initialize with service and match details.

        Args:
            service: Original service identifier
            matches: List of (project, host, ip) tuples
        """
        self.service = service
        self.matches = matches
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format error message grouped by project."""
        by_project: dict[str, list[tuple[str, str]]] = {}
        for project, host, ip in self.matches:
            by_project.setdefault(project, []).append((host, ip))

        lines = [f"Service '{self.service}' found in {len(self.matches)} locations:"]
        for project, hosts in by_project.items():
            lines.append(f"\n  {project}:")
            for host, ip in hosts:
                lines.append(f"    • {self.service}@{host}  ({ip})")

        return "\n".join(lines)

    def get_suggestions(self, command: str = "exec") -> list[str]:
        """Get disambiguation command suggestions.

        Args:
            command: Command name for suggestions (exec, ssh, logs, etc.)

        Returns:
            List of suggested commands
        """
        suggestions = []
        for proj, host, _ in self.matches:
            suggestions.append(f"slipp {command} {proj}:{self.service}@{host}")
        return suggestions


class ConfigError(SlippError):
    """Invalid configuration."""

    pass


class ConfigParseError(ConfigError):
    """Configuration file parse error."""

    pass


class ProjectNameRequiredError(ConfigError):
    """No project name configured."""

    def __init__(self) -> None:
        super().__init__(
            "No project name configured. "
            "Use --name flag or run 'slipp projects add <name> -i <inventory>'"
        )


class InventoryParseError(ConfigError):
    """Inventory file parse error."""

    pass


class PresetNotFoundError(ConfigError):
    """Tag preset not found."""

    pass


class ProjectNotFoundError(SlippError):
    """Requested project not found in registry."""

    pass


class ProfileNotFoundError(SlippError):
    """Run profile not found."""

    pass


class ProfileExecutionError(SlippError):
    """Profile execution failed."""

    pass


class AnsibleError(SlippError):
    """Ansible operation failed."""

    pass


class AnsibleNotFoundError(AnsibleError):
    """Ansible executable not found."""

    pass


class CaddyProxyError(SlippError):
    """Caddy proxy operation failed."""

    pass


class ProxyRouteError(SlippError):
    """Proxy route operation failed."""

    pass


class SourceNotFoundError(SlippError):
    """Secret source not found."""

    pass


class PullTimeoutError(SlippError):
    """Timed out waiting for credentials."""

    pass
