"""Secrets pull flow: browser approval -> callback -> encrypted vault storage."""

import contextlib
import io
import secrets as stdlib_secrets
import webbrowser
from pathlib import Path

from slipp import output
from slipp.services.config import resolve_vault_target
from slipp.services.secrets.callback_server import CallbackServer
from slipp.services.secrets.nor_auth import (
    NorAuthSource,
    PullSession,
    find_available_port,
)
from slipp.services.vault import encrypt_secrets, write_missing_secrets
from slipp.utils.errors import (
    ProjectNotFoundError,
    PullError,
    PullTimeoutError,
    VaultError,
)


async def pull_secrets(
    source: NorAuthSource,
    target: str | None = None,
    timeout: int = 300,
) -> dict[str, str]:
    """Pull credentials from source via browser flow.

    Opens browser for user approval, receives credentials via callback
    server, and stores them encrypted in vault.

    Args:
        source: The secret source to pull from.
        target: Vault path, project name, or None for cwd config.
        timeout: Maximum seconds to wait for approval. Defaults to 300.

    Returns:
        Dictionary of variable names to decrypted values.

    Raises:
        PullTimeoutError: If approval not received within timeout.
        PullError: If approval was received but no resources were selected.
    """
    session = PullSession(
        session_secret=stdlib_secrets.token_urlsafe(32),
        port=find_available_port(),
        source=source.name,
    )

    auth_url = source.get_auth_url(session)

    output.info("Opening browser for approval...")
    output.hint(f"Select and approve the export in {source.name}")

    server = CallbackServer(session.port, session.session_secret)
    try:
        await server.start()
    except OSError as e:
        raise PullError(f"Failed to start callback server on port {session.port}: {e}") from e

    try:
        with output.spinner("Waiting for approval"):
            with contextlib.redirect_stdout(io.StringIO()):
                webbrowser.open(auth_url)
            try:
                raw_credentials = await server.wait_for_credentials(timeout)
            except TimeoutError:
                raise PullTimeoutError("Timed out waiting for credentials")

        if not raw_credentials:
            raise PullError("No resources were selected for export")

        variables = source.parse_credentials(raw_credentials)
        return _store_in_vault(variables, target)
    finally:
        await server.stop()


def _store_in_vault(
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
    vault_path = _resolve_vault_path(target)

    encrypted = encrypt_secrets(variables, confirm_password=not vault_path.exists())
    write_missing_secrets(vault_path, encrypted)

    return variables


def _resolve_vault_path(target: str | None) -> Path:
    """Resolve vault path (existing file → project vault → cwd config vault)."""
    try:
        _, vault_path = resolve_vault_target(target)
    except ProjectNotFoundError:
        raise VaultError(f"Project '{target}' not found")

    if not vault_path:
        raise VaultError("No vault configured")

    return vault_path
