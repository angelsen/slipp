"""Custom exception hierarchy for slipp.

All slipp operations raise subclasses of SlippError for consistent
error handling across the CLI, services, and commands.
"""

from pathlib import Path


class SlippError(Exception):
    """Base exception for slipp."""

    pass


class SSHConnectionError(SlippError):
    """Failed to establish SSH connection."""

    pass


class SSHAuthenticationError(SSHConnectionError):
    """SSH authentication failed."""

    pass


class SSHCommandError(SlippError):
    """A remote command exited non-zero."""

    pass


class SudoPasswordError(SSHCommandError):
    """A remote sudo command failed because a password is required."""

    pass


class TunnelError(SlippError):
    """SSH tunnel operation failed."""

    pass


class VaultError(SlippError):
    """Vault operation failed."""

    pass


class AnsibleVaultNotInstalledError(VaultError):
    """The 'ansible-vault' executable is not installed or not on PATH."""

    pass


class VaultDecryptError(VaultError):
    """Failed to decrypt vault."""

    pass


class VaultFileNotFoundError(VaultError):
    """Vault file does not exist on disk."""

    pass


class VaultSyncError(VaultError):
    """Vault synchronization failed."""

    pass


class PasswordMismatchError(VaultError):
    """Vault passwords do not match."""

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


class RuntimeDetectionError(ConfigError):
    """Runtime (systemd/docker/podman) could not be determined."""

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


class DeployError(SlippError):
    """Deploy orchestration failed before or without a playbook exit code.

    Carries the log directory so the CLI layer can print a "review log"
    hint without recomputing it.
    """

    def __init__(self, message: str, *, log_dir: Path | None = None):
        self.log_dir = log_dir
        super().__init__(message)


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


class PullError(SlippError):
    """Secrets pull flow failed."""

    pass


class PullTimeoutError(PullError):
    """Timed out waiting for credentials."""

    pass


class LaunchError(SlippError):
    """Project launch/generation pipeline stage failed."""

    pass


class BootstrapError(SlippError):
    """Account/host bootstrap provisioning failed."""

    pass


class ImageTransferError(SlippError):
    """Container image transfer to remote host failed."""

    pass


class ProviderError(SlippError):
    """Provider operation failed."""

    pass


class ProvisionError(ProviderError):
    """Server provisioning failed."""

    pass


class DomainRegistrationError(ProviderError):
    """Domain registration failed."""

    pass


class WgManageError(SlippError):
    """A wg-manage SSH operation or exposure sync failed."""

    pass
