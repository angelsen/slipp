"""Per-target vault key lookup with errors captured as data.

Used by listing commands that resolve multiple targets at once, where one
bad target (unknown project, missing file, fully encrypted) shouldn't abort
the others -- see `list_secrets` in commands/secrets.py.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from slipp.services.config import ConfigResolver, resolve_vault_target
from slipp.services.vault.crypto import list_keys
from slipp.utils.errors import (
    ProjectNotFoundError,
    VaultDecryptError,
    VaultFileNotFoundError,
    VaultFullyEncryptedError,
)

VaultLookupError = Literal[
    "no vault configured",
    "vault file not found",
    "vault fully encrypted",
    "vault invalid",
    "project not found",
]


@dataclass
class VaultLookup:
    """Result of resolving a target and listing its vault keys, if any."""

    target: str
    resolver: ConfigResolver
    vault_path: Path | None
    keys: list[str] | None
    error: VaultLookupError | None


def lookup_vault_keys(target: str) -> VaultLookup:
    """Resolve a target to its vault and list keys, capturing any error.

    Args:
        target: Project name, path to vault file

    Returns:
        VaultLookup with keys populated on success, error set otherwise
    """
    try:
        resolver, vault_path = resolve_vault_target(target)
    except ProjectNotFoundError:
        return VaultLookup(target, ConfigResolver(), None, None, "project not found")

    if not vault_path:
        return VaultLookup(target, resolver, None, None, "no vault configured")

    try:
        keys = list_keys(vault_path)
    except VaultFileNotFoundError:
        return VaultLookup(target, resolver, vault_path, None, "vault file not found")
    except VaultFullyEncryptedError:
        return VaultLookup(target, resolver, vault_path, None, "vault fully encrypted")
    except VaultDecryptError:
        return VaultLookup(target, resolver, vault_path, None, "vault invalid")

    return VaultLookup(target, resolver, vault_path, keys, None)
