"""Ansible vault subprocess wrapper.

Provides functions for:
- Secret generation (cryptographically secure)
- Encrypting values for inline vault format
- Listing keys from vault files
- Extracting vault references from YAML
"""

import base64
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import yaml

from slipp.utils.cli_tools import check_tool_installed, run_checked
from slipp.utils.errors import (
    AnsibleVaultNotInstalledError,
    DuplicateEnvVarError,
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


def generate_secret(num_bytes: int = 32, encoding: str = "hex") -> str:
    """Generate cryptographically secure secret.

    Args:
        num_bytes: Number of bytes of entropy (default: 32 = 256-bit)
        encoding: Output encoding - "hex", "base64", or "ulid"

    Returns:
        Secret string in specified encoding

    Examples:
        >>> generate_secret()  # 64 hex chars (256-bit)
        >>> generate_secret(16)  # 32 hex chars (128-bit)
        >>> generate_secret(32, "base64")  # 43 base64 chars (256-bit)
        >>> generate_secret(encoding="ulid")  # 26 char ULID
    """
    if encoding == "ulid":
        from ulid import ULID

        return str(ULID())

    raw_bytes = os.urandom(num_bytes)

    if encoding == "base64":
        return base64.b64encode(raw_bytes).decode("ascii")
    else:
        return raw_bytes.hex()


def generate_jwk(bits: int = 2048) -> str:
    """Generate RSA keypair as JWK JSON.

    Args:
        bits: RSA key size (default: 2048)

    Returns:
        JSON string containing private JWK (includes public components)

    Examples:
        >>> generate_jwk()  # 2048-bit RSA
        >>> generate_jwk(4096)  # 4096-bit RSA
    """
    from jwcrypto import jwk

    key = jwk.JWK.generate(
        kty="RSA",
        size=bits,
        alg="RS256",
        use="sig",
        kid=f"key-{generate_secret(4, 'hex')}",
    )
    return key.export_private()


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
