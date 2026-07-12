"""Ansible vault subprocess wrapper.

Encrypt/decrypt operations, vault file IO, and vault-format introspection
(listing keys, scanning for encrypted content and vault_* references).
"""

import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import yaml

from slipp.utils.cli_tools import check_tool_installed, run_checked
from slipp.utils.errors import (
    AnsibleVaultNotInstalledError,
    VaultDecryptError,
    VaultError,
    VaultFileNotFoundError,
)


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
    from slipp import output

    password = output.prompt_password("Vault password", confirm=confirm)

    # mkstemp already creates the file 0600; no extra chmod needed.
    fd, path = tempfile.mkstemp(prefix="vault_pass_", text=True)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(password)
        yield Path(path)
    finally:
        Path(path).unlink(missing_ok=True)


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
    """
    if not vault_path.exists():
        raise VaultFileNotFoundError(f"Vault file not found: {vault_path}")

    with open(vault_path) as f:
        data = yaml.load(f, Loader=_VaultLoader)

    if data is None:
        return []

    return list(data.keys())


def append_to_vault(vault_path: Path, encrypted_yaml: str) -> None:
    """Append encrypted YAML to vault file.

    Args:
        vault_path: Path to vault.yml file
        encrypted_yaml: Output from encrypt_string()
    """
    vault_path.parent.mkdir(parents=True, exist_ok=True)

    with open(vault_path, "a") as f:
        f.write(encrypted_yaml)


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
        files = list(path.rglob("*.yml"))

    for f in files:
        try:
            if "$ANSIBLE_VAULT" in f.read_text():
                return True
        except Exception:
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


def write_vault(vault_path: Path, secrets: dict[str, str]) -> None:
    """Write encrypted vault file (overwrites existing).

    Args:
        vault_path: Path to vault.yml file
        secrets: Dict of {name: encrypted_yaml} from encrypt_string()

    Note:
        Each value should be the full output from encrypt_string(),
        which includes the variable name and !vault tag.
    """
    vault_path.parent.mkdir(parents=True, exist_ok=True)

    with open(vault_path, "w") as f:
        for encrypted_yaml in secrets.values():
            f.write(encrypted_yaml)


def _decrypt_inline_value(encrypted_value: str, password_file: Path) -> str:
    """Decrypt a single inline vault value.

    Args:
        encrypted_value: The encrypted string (starting with $ANSIBLE_VAULT)
        password_file: Path to vault password file

    Returns:
        Decrypted string value

    Raises:
        VaultDecryptError: If decryption fails
    """
    fd, temp_path = tempfile.mkstemp(prefix="vault_val_", suffix=".yml", text=True)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(encrypted_value)

        result = run_checked(
            [
                "ansible-vault",
                "decrypt",
                temp_path,
                "--vault-password-file",
                str(password_file),
                "--output",
                "-",
            ],
            VaultDecryptError,
            context="Failed to decrypt value",
        )

        return result.stdout.strip()
    finally:
        Path(temp_path).unlink(missing_ok=True)


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

    if not vault_path.exists():
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
            return {k: str(v) for k, v in secrets.items()}
        except yaml.YAMLError as e:
            raise VaultDecryptError(f"Invalid YAML in vault: {e}")

    else:
        try:
            data = yaml.load(content, Loader=_VaultLoader)
            if data is None:
                return {}

            secrets: dict[str, str] = {}
            for key, value in data.items():
                if isinstance(value, str) and "$ANSIBLE_VAULT" in value:
                    secrets[key] = _decrypt_inline_value(value, password_file)
                else:
                    secrets[key] = str(value)

            return secrets
        except yaml.YAMLError as e:
            raise VaultDecryptError(f"Invalid YAML in vault: {e}")
