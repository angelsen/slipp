"""Secret synchronization service.

Extracts vault sync logic from secret.py into a service.
Handles scanning YAML files for vault references and generating secrets.
"""

from pathlib import Path

from slipp.services.vault.crypto import (
    encrypt_string,
    extract_vault_refs,
    vault_password_file,
    write_vault,
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

    def __init__(self, num_bytes: int = 32, encoding: str = "hex"):
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
        """Generate and write missing secrets for the given references.

        Args:
            vault_path: Path to vault file to write.
            refs: Vault variable names to generate secrets for (e.g. from scan()).
            force: Overwrite existing vault file if True

        Returns:
            List of generated secret names

        Raises:
            VaultSyncError: If the vault file already exists (without force),
                or on encryption errors
        """
        if vault_path.exists() and not force:
            raise VaultSyncError(
                f"Vault file already exists: {vault_path}. Use force=True to overwrite."
            )

        if not refs:
            return []

        secrets = self._generate_secrets(sorted(refs))

        write_vault(vault_path, secrets)

        return list(secrets.keys())

    def _generate_secrets(self, names: list[str]) -> dict[str, str]:
        """Generate and encrypt secrets for the given names.

        Args:
            names: List of secret names to generate

        Returns:
            Dict mapping secret names to encrypted values

        Raises:
            VaultSyncError: On password mismatch or encryption errors
        """
        secrets: dict[str, str] = {}

        try:
            with vault_password_file() as pw_file:
                for name in names:
                    secret = generate_secret(self.num_bytes, self.encoding)
                    encrypted = encrypt_string(secret, name, password_file=pw_file)
                    secrets[name] = encrypted
        except PasswordMismatchError:
            raise VaultSyncError("Passwords do not match")
        except AnsibleVaultNotInstalledError as e:
            raise VaultSyncError(str(e))
        except VaultError as e:
            raise VaultSyncError(f"Encryption failed: {e}")

        return secrets
