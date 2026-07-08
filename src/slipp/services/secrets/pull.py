"""Pull service for orchestrating secrets pull flow."""

import contextlib
import io
import secrets as stdlib_secrets
import webbrowser
from pathlib import Path

from slipp import output
from slipp.services.secrets.callback_server import CallbackServer
from slipp.services.secrets.sources.base import (
    PullSession,
    SecretSource,
    find_available_port,
)
from slipp.services.vault import append_to_vault, encrypt_string, vault_password_file
from slipp.utils.errors import ProjectNotFoundError, PullTimeoutError, VaultError


class PullService:
    """Orchestrates the secrets pull flow for any source."""

    def __init__(self, source: SecretSource):
        self.source = source

    async def pull(
        self,
        target: str | None = None,
        timeout: int = 300,
    ) -> dict[str, str]:
        """Pull credentials from source via browser flow.

        Opens browser for user approval, receives credentials via callback
        server, and stores them encrypted in vault.

        Args:
            target: Vault path, project name, or None for cwd config.
            timeout: Maximum seconds to wait for approval. Defaults to 300.

        Returns:
            Dictionary of variable names to decrypted values.

        Raises:
            PullTimeoutError: If approval not received within timeout.
        """
        session = PullSession(
            session_secret=stdlib_secrets.token_urlsafe(32),
            port=find_available_port(),
            source=self.source.name,
        )

        auth_url = self.source.get_auth_url(session)

        output.info("Opening browser for approval...")
        output.hint(f"Select and approve the export in {self.source.name}")

        async with CallbackServer(session.port, session.session_secret) as server:
            with output.spinner("Waiting for approval"):
                with contextlib.redirect_stdout(io.StringIO()):
                    webbrowser.open(auth_url)
                raw_credentials = await server.wait_for_credentials(timeout)

            if not raw_credentials:
                raise PullTimeoutError("Timed out waiting for credentials")

            variables = self.source.parse_credentials(raw_credentials)
            return await self._store_in_vault(variables, target)

    async def _store_in_vault(
        self,
        variables: dict[str, str],
        target: str | None = None,
    ) -> dict[str, str]:
        """Encrypt and store variables in vault.

        Args:
            variables: Variable names and values to encrypt.
            target: Vault path, project name, or None for cwd config.

        Returns:
            The input variables (for chaining).

        Raises:
            VaultError: If vault path cannot be resolved.
        """
        vault_path = self._resolve_vault_path(target)

        with vault_password_file(confirm=False) as pw_file:
            for var_name, value in variables.items():
                encrypted = encrypt_string(value, var_name, password_file=pw_file)
                append_to_vault(vault_path, encrypted)

        return variables

    def _resolve_vault_path(self, target: str | None) -> Path:
        """Resolve vault path (existing file → project vault → cwd config vault)."""
        from slipp.services.config import resolve_vault_target

        try:
            _, vault_path = resolve_vault_target(target)
        except ProjectNotFoundError:
            raise VaultError(f"Project '{target}' not found")

        if not vault_path:
            raise VaultError("No vault configured")

        return vault_path
