"""Secret synchronization service.

Extracts vault sync logic from secret.py into a service.
Handles scanning YAML files for vault references and generating secrets.
"""

from pathlib import Path

from slipp.services.vault.vault import (
    encrypt_string,
    extract_vault_refs,
    generate_secret,
    vault_password_file,
    write_vault,
)
from slipp.utils.errors import (
    PasswordMismatchError,
    VaultError,
    VaultNotFoundError,
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

    def find_vault_references(self, content: str) -> set[str]:
        """Extract vault_* variable names from YAML content.

        Args:
            content: YAML file content as string

        Returns:
            Set of vault variable names found
        """
        return extract_vault_refs(content)

    def sync(
        self,
        vars_file: Path,
        vault_path: Path | None = None,
        force: bool = False,
    ) -> list[str]:
        """Find {{ vault_* }} refs and generate missing secrets.

        Args:
            vars_file: Path to YAML file to scan for references
            vault_path: Path to vault file (default: vars_file.parent / vault.yml)
            force: Overwrite existing vault file if True

        Returns:
            List of generated secret names

        Raises:
            VaultSyncError: On file not found, already exists, or encryption errors
        """
        if not vars_file.exists():
            raise VaultSyncError(f"File not found: {vars_file}")

        if not vars_file.is_file():
            raise VaultSyncError(f"Not a file: {vars_file}")

        if vault_path is None:
            vault_path = vars_file.parent / "vault.yml"

        if vault_path.exists() and not force:
            raise VaultSyncError(
                f"Vault file already exists: {vault_path}. Use force=True to overwrite."
            )

        content = vars_file.read_text()
        refs = self.find_vault_references(content)

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
                    if self.encoding == "ulid":
                        secret = generate_secret(encoding="ulid")
                    else:
                        secret = generate_secret(self.num_bytes, self.encoding)
                    encrypted = encrypt_string(secret, name, password_file=pw_file)
                    secrets[name] = encrypted
        except PasswordMismatchError:
            raise VaultSyncError("Passwords do not match")
        except VaultNotFoundError as e:
            raise VaultSyncError(str(e))
        except VaultError as e:
            raise VaultSyncError(f"Encryption failed: {e}")

        return secrets
