"""Secret synchronization service.

Extracts vault sync logic from secret.py into a service.
Handles scanning YAML files for vault references and generating secrets.
"""

from pathlib import Path

from slipp.constants import SecretEncoding
from slipp.services.vault.crypto import (
    encrypt_secrets,
    extract_vault_refs,
    list_keys,
    write_missing_secrets,
)
from slipp.services.vault.generate import generate_secret
from slipp.utils.errors import (
    AnsibleVaultNotInstalledError,
    PasswordMismatchError,
    VaultError,
    VaultSyncError,
)


class SecretSynchronizer:
    """Synchronize vault secrets from YAML references.

    This service scans YAML files for {{ vault_* }} references
    and generates missing secrets in the vault file.
    """

    def __init__(
        self, num_bytes: int = 32, encoding: SecretEncoding = SecretEncoding.hex
    ):
        """Initialize synchronizer.

        Args:
            num_bytes: Number of bytes of entropy for generated secrets
            encoding: Output encoding (hex, base64, or ulid)
        """
        self.num_bytes = num_bytes
        self.encoding = encoding

    def scan(self, vars_file: Path) -> set[str]:
        """Read a YAML file and extract its {{ vault_* }} references.

        Args:
            vars_file: Path to YAML file to scan for references

        Returns:
            Set of vault variable names found

        Raises:
            VaultSyncError: If the file doesn't exist or isn't a file
        """
        if not vars_file.exists():
            raise VaultSyncError(f"File not found: {vars_file}")

        if not vars_file.is_file():
            raise VaultSyncError(f"Not a file: {vars_file}")

        return extract_vault_refs(vars_file.read_text())

    def sync(
        self,
        vault_path: Path,
        refs: set[str],
        force: bool = False,
    ) -> list[str]:
        """Generate secrets for missing references and add them to the vault.

        Existing vault content is preserved: only refs not already present
        as keys in the vault are generated, and they are appended rather
        than replacing the file.

        Args:
            vault_path: Path to vault file to write.
            refs: Vault variable names to generate secrets for (e.g. from scan()).
            force: Add to an existing vault file if True

        Returns:
            List of generated secret names

        Raises:
            VaultSyncError: If the vault file already exists (without force),
                or on encryption errors
        """
        vault_exists = vault_path.is_file()
        if vault_exists and not force:
            raise VaultSyncError(
                f"Vault file already exists: {vault_path}. "
                "Use --force-existing to add to it."
            )

        existing_keys = set(list_keys(vault_path)) if vault_exists else set()
        missing = refs - existing_keys

        if not missing:
            return []

        secrets = self._generate_secrets(
            sorted(missing), confirm_password=not vault_exists
        )

        return write_missing_secrets(vault_path, secrets)

    def _generate_secrets(
        self, names: list[str], confirm_password: bool = True
    ) -> dict[str, str]:
        """Generate and encrypt secrets for the given names.

        Args:
            names: List of secret names to generate
            confirm_password: Prompt twice and verify match (for a brand-new vault)

        Returns:
            Dict mapping secret names to encrypted values

        Raises:
            VaultSyncError: On password mismatch or encryption errors
        """
        plaintext = {
            name: generate_secret(self.num_bytes, self.encoding) for name in names
        }

        try:
            return encrypt_secrets(plaintext, confirm_password=confirm_password)
        except PasswordMismatchError as e:
            raise VaultSyncError("Passwords do not match") from e
        except AnsibleVaultNotInstalledError as e:
            raise VaultSyncError(str(e)) from e
        except VaultError as e:
            raise VaultSyncError(f"Encryption failed: {e}") from e
