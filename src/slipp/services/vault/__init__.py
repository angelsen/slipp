"""Vault and secrets management services.

This package provides services for Ansible vault encryption, decryption, and secret management.
"""

from slipp.services.vault.sync import SecretSynchronizer
from slipp.services.vault.vault import (
    VaultInfo,
    append_to_vault,
    decrypt_vault,
    decrypt_vault_to_env,
    encrypt_string,
    extract_vault_refs,
    generate_jwk,
    generate_secret,
    has_vault_content,
    list_keys,
    list_project_vaults,
    merge_vault_envs,
    vault_password_file,
    write_vault,
)

__all__ = [
    "VaultInfo",
    "append_to_vault",
    "decrypt_vault",
    "decrypt_vault_to_env",
    "encrypt_string",
    "extract_vault_refs",
    "generate_jwk",
    "generate_secret",
    "has_vault_content",
    "list_keys",
    "list_project_vaults",
    "merge_vault_envs",
    "vault_password_file",
    "write_vault",
    "SecretSynchronizer",
]
