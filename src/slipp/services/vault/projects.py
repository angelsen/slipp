"""Registry-aware vault orchestration.

Operations that span the project registry: listing every registered
project's vault, and decrypting/merging vaults into environment variables.
"""

from dataclasses import dataclass
from pathlib import Path

from slipp.services.vault.crypto import decrypt_vault, list_keys
from slipp.utils.errors import DuplicateEnvVarError, VaultDecryptError


@dataclass(frozen=True)
class VaultInfo:
    """A registered project's configured vault, for discovery listings."""

    project: str
    vault: str  # relative path from slipp.yaml
    secret_count: int | None  # None = unreadable/malformed


def list_project_vaults() -> list[VaultInfo]:
    """List every registered project with an existing, configured vault file.

    Args:
        (none)

    Returns:
        VaultInfo for each registered project whose slipp.yaml configures a
        vault path that exists on disk. secret_count is None if the vault
        file couldn't be parsed (malformed) rather than aborting the listing.
    """
    from slipp.services.config import LocalConfigService
    from slipp.services.registry import ProjectRegistry

    vaults: list[VaultInfo] = []
    for project in ProjectRegistry().list_all():
        local_config = LocalConfigService.load(project.project_path)
        if not (local_config and local_config.vault):
            continue

        vault_path = project.project_path / local_config.vault
        if not vault_path.exists():
            continue

        try:
            secret_count = len(list_keys(vault_path))
        except Exception:
            # list_keys can raise VaultFileNotFoundError/YAMLError/AttributeError
            # for a malformed vault - degrade to unknown rather than aborting
            # the whole listing over one bad vault file.
            secret_count = None

        vaults.append(
            VaultInfo(
                project=project.name,
                vault=local_config.vault,
                secret_count=secret_count,
            )
        )

    return vaults


def decrypt_vault_to_env(
    project_name: str,
    password_file: Path,
) -> dict[str, str]:
    """Decrypt a project's vault and return as environment variables.

    Converts vault_* keys to uppercase env vars (strips vault_ prefix).
    E.g., vault_db_password -> DB_PASSWORD

    Args:
        project_name: Name of registered project
        password_file: Path to vault password file

    Returns:
        Dict of {ENV_VAR: value} pairs

    Raises:
        VaultDecryptError: If project not found or decryption fails
    """
    from slipp.services.config import LocalConfigService
    from slipp.services.registry import ProjectRegistry

    registry = ProjectRegistry()
    project = registry.get(project_name)

    if not project:
        raise VaultDecryptError(f"Project '{project_name}' not found in registry")

    local_config = LocalConfigService.load(project.project_path)
    if not local_config or not local_config.vault:
        raise VaultDecryptError(f"Project '{project_name}' has no vault configured")

    vault_path = project.project_path / local_config.vault

    secrets = decrypt_vault(vault_path, password_file)

    env: dict[str, str] = {}
    for key, value in secrets.items():
        if key.startswith("vault_"):
            env_key = key[6:].upper()
        else:
            env_key = key.upper()
        env[env_key] = value

    return env


def merge_vault_envs(
    vault_names: list[str],
    password_file: Path,
) -> dict[str, str]:
    """Merge environment variables from multiple vaults.

    Fails fast on duplicate keys across vaults.

    Args:
        vault_names: List of project names with vaults
        password_file: Path to vault password file

    Returns:
        Merged dict of {ENV_VAR: value} pairs

    Raises:
        DuplicateEnvVarError: If same key found in multiple vaults
        VaultDecryptError: If decryption fails
    """
    merged: dict[str, str] = {}
    sources: dict[str, str] = {}  # Track which vault each key came from

    for vault_name in vault_names:
        env = decrypt_vault_to_env(vault_name, password_file)

        for key, value in env.items():
            if key in merged:
                raise DuplicateEnvVarError(
                    f"Duplicate env var '{key}' found in vaults: {sources[key]}, {vault_name}\n"
                    f"Hint: Remove one vault or rename the secret"
                )
            merged[key] = value
            sources[key] = vault_name

    return merged
