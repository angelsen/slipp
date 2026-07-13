"""Vault and secrets management services.

This package provides services for Ansible vault encryption, decryption, and secret management.
"""

from slipp.services.vault.crypto import (
    decrypt_vault,
    encrypt_secrets,
    encrypt_string,
    extract_vault_refs,
    has_vault_content,
    list_keys,
    vault_password_file,
    write_missing_secrets,
)
from slipp.services.vault.generate import generate_jwk, generate_secret
from slipp.services.vault.projects import (
    VaultInfo,
    decrypt_vault_to_env,
    list_project_vaults,
    merge_vault_envs,
)
from slipp.services.vault.sync import SecretSynchronizer

__all__ = [
    "VaultInfo",
    "decrypt_vault",
    "decrypt_vault_to_env",
    "encrypt_secrets",
    "encrypt_string",
    "extract_vault_refs",
    "generate_jwk",
    "generate_secret",
    "has_vault_content",
    "list_keys",
    "list_project_vaults",
    "merge_vault_envs",
    "vault_password_file",
    "write_missing_secrets",
    "SecretSynchronizer",
]
