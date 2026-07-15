"""Ansible vault subprocess wrapper.

Encrypt/decrypt operations, vault file IO, and vault-format introspection
(listing keys, scanning for encrypted content and vault_* references).
"""

import re
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any

import yaml

from slipp.utils.cli_tools import check_tool_installed, run_checked
from slipp.utils.config_store import config_store_lock
from slipp.utils.errors import (
    AnsibleVaultNotInstalledError,
    VaultDecryptError,
    VaultError,
    VaultFileNotFoundError,
    VaultFullyEncryptedError,
)
from slipp.utils.files import atomic_write_text, prompted_secret_file, temp_secret_file


class _VaultLoader(yaml.SafeLoader):
    """YAML loader that handles !vault tags by returning the encrypted value as-is."""

    pass


def _vault_constructor(loader: yaml.Loader, node: yaml.Node) -> str:
    """Handle !vault tag - just return the encrypted value string."""
    return loader.construct_scalar(node)  # type: ignore


_VaultLoader.add_constructor("!vault", _vault_constructor)


@contextmanager
def vault_password_file(confirm: bool = True) -> Iterator[Path]:
    """Context manager that prompts for password and creates temp file.

    Args:
        confirm: If True, prompt twice and verify match

    Yields:
        Path to temporary password file (deleted on exit)

    Raises:
        PasswordMismatchError: If confirm=True and passwords don't match

    Example:
        with vault_password_file() as pw_file:
            encrypt_string("secret", "name", password_file=pw_file)
    """
    with prompted_secret_file(
        "Vault password", prefix="vault_pass_", confirm=confirm
    ) as path:
        yield path


def encrypt_string(
    value: str,
    name: str,
    *,
    password_file: Path | None = None,
) -> str:
    """Encrypt a value for inline vault format.

    Uses ansible-vault encrypt_string to produce YAML-ready encrypted output.

    Args:
        value: Secret value to encrypt
        name: Variable name (e.g., "vault_db_password")
        password_file: Path to vault password file (if None, will prompt)

    Returns:
        Encrypted YAML snippet ready to append to vault file

    Raises:
        AnsibleVaultNotInstalledError: If ansible-vault not installed
        VaultError: If encryption fails

    Example:
        >>> encrypt_string("mysecret", "vault_db_password")
        vault_db_password: !vault |
          $ANSIBLE_VAULT;1.1;AES256
          61626364...
    """
    check_tool_installed("ansible-vault", AnsibleVaultNotInstalledError)

    cmd = ["ansible-vault", "encrypt_string", "--stdin-name", name]
    if password_file:
        cmd.extend(["--vault-password-file", str(password_file)])

    result = run_checked(cmd, VaultError, input=value)

    return result.stdout


def encrypt_secrets(
    secrets: dict[str, str], *, confirm_password: bool = False
) -> dict[str, str]:
    """Encrypt a batch of name -> plaintext pairs under one password prompt.

    Args:
        secrets: Mapping of secret name to plaintext value.
        confirm_password: Prompt twice and verify match (for a brand-new vault).

    Returns:
        Dict mapping name to encrypted YAML snippet (encrypt_string() output).

    Raises:
        AnsibleVaultNotInstalledError: If ansible-vault not installed.
        VaultError: If encryption fails.
        PasswordMismatchError: If confirm_password=True and passwords don't match.
    """
    with vault_password_file(confirm=confirm_password) as pw_file:
        return {
            name: encrypt_string(value, name, password_file=pw_file)
            for name, value in secrets.items()
        }


def _require_mapping(
    data: object, path: Path, *, fully_encrypted: bool
) -> dict[str, Any]:
    """Raise VaultDecryptError unless a loaded YAML document is a mapping."""
    if not isinstance(data, dict):
        if fully_encrypted:
            raise VaultFullyEncryptedError(f"Vault is fully encrypted: {path}")
        raise VaultDecryptError(
            f"Expected YAML mapping in {path}, got {type(data).__name__}"
        )
    return data


def list_keys(vault_path: Path) -> list[str]:
    """List variable names from an inline vault file.

    For inline vault format, keys are plaintext (only values encrypted).
    No decryption needed.

    Args:
        vault_path: Path to vault.yml file

    Returns:
        List of variable names (e.g., ["vault_db_password", "vault_api_key"])

    Raises:
        VaultFileNotFoundError: If vault file doesn't exist
        VaultDecryptError: If the file isn't valid YAML or isn't a mapping
    """
    if not vault_path.is_file():
        raise VaultFileNotFoundError(f"Vault file not found: {vault_path}")

    content = vault_path.read_text()
    fully_encrypted = content.strip().startswith("$ANSIBLE_VAULT")

    try:
        data = yaml.load(content, Loader=_VaultLoader)
    except yaml.YAMLError as e:
        raise VaultDecryptError(f"Invalid YAML in vault: {e}") from e

    if data is None:
        return []

    return list(
        _require_mapping(data, vault_path, fully_encrypted=fully_encrypted).keys()
    )


def write_missing_secrets(vault_path: Path, secrets: dict[str, str]) -> list[str]:
    """Add secrets for keys not already in the vault, creating it if needed.

    Re-checks existing keys under the vault lock immediately before writing,
    closing the gap between an earlier unlocked "what's missing" check (e.g.
    in `SecretSynchronizer.sync()`) and the actual write - without this, two
    concurrent syncs that both decided the same key was missing would both
    append/overwrite, leaving a duplicate or clobbered entry.

    Args:
        vault_path: Path to vault.yml file
        secrets: Dict of {name: encrypted_yaml} for keys believed missing

    Returns:
        Keys actually written (a subset of `secrets` if another process
        already added some of them first)
    """
    with config_store_lock(vault_path):
        vault_exists = vault_path.is_file()
        existing_keys = set(list_keys(vault_path)) if vault_exists else set()
        to_add = {k: v for k, v in secrets.items() if k not in existing_keys}
        if not to_add:
            return []

        existing = vault_path.read_text() if vault_exists else ""
        atomic_write_text(vault_path, existing + "".join(to_add.values()))
        return list(to_add.keys())


def has_vault_content(path: Path) -> bool:
    """Check if path contains ansible-vault encrypted content.

    Args:
        path: File or directory to scan

    Returns:
        True if any .yml file contains $ANSIBLE_VAULT header
    """
    if path.is_file():
        files = [path]
    else:
        files = list(path.rglob("*.yml")) + list(path.rglob("*.yaml"))

    for f in files:
        try:
            if "$ANSIBLE_VAULT" in f.read_text():
                return True
        except (OSError, UnicodeDecodeError):
            continue
    return False


def extract_vault_refs(yaml_content: str) -> set[str]:
    """Extract vault variable references from YAML content.

    Scans raw content for {{ vault_* }} patterns.

    Args:
        yaml_content: Raw YAML file content

    Returns:
        Set of vault variable names (e.g., {"vault_db_password", "vault_api_key"})

    Example:
        >>> extract_vault_refs('password: "{{ vault_db_password }}"')
        {'vault_db_password'}
    """
    pattern = r"\{\{\s*(vault_\w+)\s*\}\}"
    matches = re.findall(pattern, yaml_content)
    return set(matches)


def _decrypt_inline_values(
    encrypted_values: dict[str, str], password_file: Path
) -> dict[str, str]:
    """Decrypt multiple inline vault values in a single ansible-vault call.

    `ansible-vault decrypt --output -` only accepts one input file, so
    batching means decrypting each value's temp file in place (no
    --output) in one subprocess invocation, then reading the results back.

    Args:
        encrypted_values: Mapping of key -> encrypted string (starting with
            $ANSIBLE_VAULT)
        password_file: Path to vault password file

    Returns:
        Dict of key -> decrypted string value

    Raises:
        VaultDecryptError: If decryption fails
    """
    with ExitStack() as stack:
        temp_paths = {
            key: stack.enter_context(
                temp_secret_file(value, prefix="vault_val_", suffix=".yml")
            )
            for key, value in encrypted_values.items()
        }

        run_checked(
            [
                "ansible-vault",
                "decrypt",
                *(str(p) for p in temp_paths.values()),
                "--vault-password-file",
                str(password_file),
            ],
            VaultDecryptError,
            context="Failed to decrypt vault values",
        )

        return {key: path.read_text().strip() for key, path in temp_paths.items()}


def decrypt_vault(vault_path: Path, password_file: Path) -> dict[str, str]:
    """Decrypt a vault file and return key-value pairs.

    Supports both:
    - Inline vault format (individual values encrypted with !vault tag)
    - Fully encrypted vault files

    Args:
        vault_path: Path to vault.yml file
        password_file: Path to vault password file

    Returns:
        Dict of decrypted {key: value} pairs

    Raises:
        VaultDecryptError: If decryption fails
        VaultFileNotFoundError: If vault file doesn't exist
    """
    check_tool_installed("ansible-vault", AnsibleVaultNotInstalledError)

    if not vault_path.is_file():
        raise VaultFileNotFoundError(f"Vault file not found: {vault_path}")

    content = vault_path.read_text()

    if content.strip().startswith("$ANSIBLE_VAULT"):
        result = run_checked(
            [
                "ansible-vault",
                "view",
                str(vault_path),
                "--vault-password-file",
                str(password_file),
            ],
            VaultDecryptError,
            context="Failed to decrypt vault",
        )

        try:
            secrets = yaml.safe_load(result.stdout)
            if secrets is None:
                return {}
            return {
                k: str(v)
                for k, v in _require_mapping(
                    secrets, vault_path, fully_encrypted=False
                ).items()
            }
        except yaml.YAMLError as e:
            raise VaultDecryptError(f"Invalid YAML in vault: {e}") from e

    else:
        try:
            data = yaml.load(content, Loader=_VaultLoader)
            if data is None:
                return {}
            data = _require_mapping(data, vault_path, fully_encrypted=False)

            encrypted = {
                key: value
                for key, value in data.items()
                if isinstance(value, str) and "$ANSIBLE_VAULT" in value
            }
            secrets: dict[str, str] = {
                key: str(value) for key, value in data.items() if key not in encrypted
            }
            if encrypted:
                secrets.update(_decrypt_inline_values(encrypted, password_file))

            return secrets
        except yaml.YAMLError as e:
            raise VaultDecryptError(f"Invalid YAML in vault: {e}") from e
