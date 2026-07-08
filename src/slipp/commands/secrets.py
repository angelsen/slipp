"""Vault secret management commands."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.constants import OutputFormat, SecretEncoding
from slipp.output import format_path
from slipp.services.config import ConfigResolver, resolve_vault_target
from slipp.services.vault import (
    SecretSynchronizer,
    append_to_vault,
    encrypt_string,
    generate_jwk,
    generate_secret,
    list_keys,
    list_project_vaults,
    vault_password_file,
)
from slipp.utils.errors import (
    AnsibleVaultNotInstalledError,
    ProjectNotFoundError,
    PullError,
    PullTimeoutError,
    SourceNotFoundError,
    VaultError,
    VaultFileNotFoundError,
    VaultSyncError,
)


secrets_app = typer.Typer(
    name="secrets",
    help="Manage vault secrets",
)


def _resolve_vault_or_exit(target: str | None) -> tuple[ConfigResolver, Path | None]:
    """Resolve vault target (path, project, or cwd), exiting if project unknown.

    Args:
        target: Project name, path to vault file, or None

    Returns:
        Tuple of (ConfigResolver, vault Path or None)

    Raises:
        typer.Exit: If project not found
    """
    try:
        return resolve_vault_target(target)
    except ProjectNotFoundError:
        output.error(f"Project '{target}' not found")
        output.hint("Use 'slipp projects' to list registered projects")
        raise typer.Exit(1)


@dataclass
class _VaultLookup:
    """Result of resolving a target and listing its vault keys, if any."""

    target: str
    resolver: ConfigResolver
    vault_path: Path | None
    keys: list[str] | None
    error: str | None  # "no vault configured" | "vault file not found" | None


def _lookup_vault_keys(target: str) -> _VaultLookup:
    """Resolve a target to its vault and list keys, capturing any error.

    Args:
        target: Project name, path to vault file

    Returns:
        _VaultLookup with keys populated on success, error set otherwise
    """
    resolver, vault_path = _resolve_vault_or_exit(target)

    if not vault_path:
        return _VaultLookup(target, resolver, None, None, "no vault configured")

    try:
        keys = list_keys(vault_path)
    except VaultFileNotFoundError:
        return _VaultLookup(target, resolver, vault_path, None, "vault file not found")

    return _VaultLookup(target, resolver, vault_path, keys, None)


def _list_available_vaults() -> None:
    """Show all registered projects that have vaults configured (discovery mode)."""
    from slipp.services.secrets import get_source, list_sources

    vaults_found = [
        {
            "project": v.project,
            "vault": v.vault,
            "secrets": str(v.secret_count) if v.secret_count is not None else "?",
        }
        for v in list_project_vaults()
    ]

    sources = list_sources()

    if output.get_output_format() == OutputFormat.json:
        output.stdout(
            json.dumps(
                {
                    "vaults": vaults_found,
                    "sources": [
                        {
                            "name": name,
                            "description": get_source(name).get_description(),
                        }
                        for name in sources
                    ],
                },
                indent=2,
            )
        )
        return

    if vaults_found:
        output.info("Available vaults:")
        output.table(vaults_found)
    else:
        output.warning("No vaults found in any registered project")

    if sources:
        output.blank()
        output.info("Pull sources:")
        for name in sources:
            src = get_source(name)
            output.bullet(f"{name} - {src.get_description()}", indent=1)


@secrets_app.command(name="list")
def list_secrets(
    targets: Annotated[
        list[str] | None,
        typer.Argument(
            help="Project name(s) or vault file path(s) (discovery mode if omitted)"
        ),
    ] = None,
    secret_name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Secret name to get template string for"),
    ] = None,
) -> None:
    """List secrets in vault(s), or show available vaults."""
    if not targets:
        _list_available_vaults()
        return

    lookups = [_lookup_vault_keys(target) for target in targets]

    if output.get_output_format() == OutputFormat.json:
        results: list[dict[str, object]] = []
        for lookup in lookups:
            entry: dict[str, object] = {"target": lookup.target}

            if lookup.error:
                if lookup.vault_path:
                    entry["vault_path"] = str(lookup.vault_path)
                entry["error"] = lookup.error
                results.append(entry)
                continue

            assert lookup.vault_path is not None and lookup.keys is not None
            entry["vault_path"] = str(lookup.vault_path)
            if secret_name:
                entry["secret_name"] = secret_name
                entry["found"] = secret_name in lookup.keys
            else:
                entry["keys"] = lookup.keys
            results.append(entry)

        output.stdout(json.dumps(results, indent=2))
        return

    for i, lookup in enumerate(lookups):
        if i > 0:
            output.blank()

        if lookup.error == "no vault configured":
            output.warning(f"No vault configured for '{lookup.target}'")
            continue
        if lookup.error == "vault file not found":
            assert lookup.vault_path is not None
            output.error(
                f"Vault file not found: {format_path(lookup.vault_path, lookup.resolver.project_root)}"
            )
            continue

        assert lookup.vault_path is not None and lookup.keys is not None
        keys = lookup.keys

        if secret_name:
            if secret_name not in keys:
                output.error(f"Secret '{secret_name}' not found in {lookup.target}")
                continue
            output.stdout(f"{{{{ {secret_name} }}}}")
            continue

        if not keys:
            output.info(f"No secrets found in {lookup.target}")
            continue

        output.info(
            f"Secrets in {format_path(lookup.vault_path, lookup.resolver.project_root)}:"
        )
        for key in keys:
            output.bullet(key, indent=1)


@secrets_app.command(name="add")
def add_secret(
    name: Annotated[str, typer.Argument(help="Secret name (e.g., vault_db_password)")],
    target: Annotated[
        str | None,
        typer.Argument(
            help="Project name or vault file path (uses local config if omitted)"
        ),
    ] = None,
    num_bytes: Annotated[
        int,
        typer.Option("--bytes", "-b", help="Bytes of entropy (default: 32 = 256-bit)"),
    ] = 32,
    encoding: Annotated[
        SecretEncoding,
        typer.Option(
            "--encoding",
            "-e",
            help="Output encoding: hex (default), base64, or ulid",
        ),
    ] = SecretEncoding.hex,
    jwk: Annotated[
        bool, typer.Option("--jwk", help="Generate RSA JWK keypair")
    ] = False,
    bits: Annotated[
        int, typer.Option("--bits", help="RSA key size for --jwk (default: 2048)")
    ] = 2048,
) -> None:
    """Generate and add a secret to a vault."""
    resolver, vault_path = _resolve_vault_or_exit(target)

    if not vault_path:
        output.error("No vault configured")
        output.hint("Specify project: slipp secrets add <name> <project>")
        output.hint("Or configure vault in slipp.yaml")
        raise typer.Exit(1)

    if not vault_path.exists():
        output.error(
            f"Vault file not found: {format_path(vault_path, resolver.project_root)}"
        )
        raise typer.Exit(1)

    secret = generate_jwk(bits) if jwk else generate_secret(num_bytes, encoding.value)

    try:
        with vault_password_file(confirm=False) as pw_file:
            encrypted = encrypt_string(secret, name, password_file=pw_file)
    except AnsibleVaultNotInstalledError as e:
        output.error(str(e))
        raise typer.Exit(1)
    except VaultError as e:
        output.error(f"Encryption failed: {e}")
        raise typer.Exit(1)

    append_to_vault(vault_path, encrypted)

    output.success(
        f"Added '{name}' to {format_path(vault_path, resolver.project_root)}"
    )
    if jwk:
        output.hint(f"RSA-{bits} JWK keypair")
    elif encoding == "ulid":
        output.hint("ULID identifier (26 chars)")
    elif encoding == "base64":
        output.hint(f"Base64 encoded ({num_bytes} bytes)")
    output.hint(f"Use {{{{ {name} }}}} in templates")


@secrets_app.command(name="sync")
def sync_secrets(
    path: Annotated[Path, typer.Argument(help="Path to vars.yml file")],
    num_bytes: Annotated[
        int,
        typer.Option("--bytes", "-b", help="Bytes of entropy (default: 32 = 256-bit)"),
    ] = 32,
    encoding: Annotated[
        SecretEncoding,
        typer.Option(
            "--encoding",
            "-e",
            help="Output encoding: hex (default), base64, or ulid",
        ),
    ] = SecretEncoding.hex,
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Overwrite existing vault.yml")
    ] = False,
) -> None:
    """Scan YAML for vault references and auto-generate secrets."""
    project_root = Path.cwd()
    vault_path = path.parent / "vault.yml"

    synchronizer = SecretSynchronizer(num_bytes=num_bytes, encoding=encoding)

    try:
        refs = synchronizer.scan(path)
    except VaultSyncError as e:
        output.error(str(e))
        raise typer.Exit(1)
    except OSError as e:
        output.error(f"Cannot read {format_path(path, project_root)}: {e}")
        raise typer.Exit(1)

    if not refs:
        output.info("No vault references found")
        output.hint("Vault references use pattern: {{ vault_variable_name }}")
        return

    output.info(f"Found {len(refs)} vault reference(s):")
    for ref in sorted(refs):
        output.bullet(ref, indent=1)

    try:
        synchronizer.sync(vault_path, refs, force=force)
    except VaultSyncError as e:
        output.error(str(e))
        if vault_path.exists():
            output.hint("Use --force to overwrite")
        raise typer.Exit(1)

    output.success(f"Created {format_path(vault_path, project_root)}")
    output.hint(
        f"Encrypt with: ansible-vault encrypt {format_path(vault_path, project_root)}"
    )


@secrets_app.command(name="pull")
def pull_secrets(
    source: Annotated[str, typer.Argument(help="Secret source (e.g., nor-auth)")],
    target: Annotated[
        str | None,
        typer.Argument(
            help="Target vault (project name or path, uses local config if omitted)"
        ),
    ] = None,
    timeout: Annotated[
        int, typer.Option("--timeout", "-t", help="Timeout in seconds")
    ] = 300,
) -> None:
    """Pull credentials from external source to vault."""
    import asyncio

    from slipp.services.secrets import get_source

    try:
        secret_source = get_source(source)
    except SourceNotFoundError as e:
        output.error(str(e))
        output.hint("Use 'slipp secrets list' to see available sources")
        raise typer.Exit(1)

    from slipp.services.secrets.pull import PullService

    service = PullService(secret_source)
    try:
        credentials = asyncio.run(service.pull(target=target, timeout=timeout))
        output.success("Credentials stored in vault")
        output.blank()
        for var_name in credentials.keys():
            output.bullet(var_name, indent=1)
    except PullTimeoutError:
        output.error(f"Timed out waiting for approval ({timeout}s)")
        output.hint("Make sure to approve the export in your browser")
        raise typer.Exit(1)
    except PullError as e:
        output.error(str(e))
        raise typer.Exit(1)
    except VaultError as e:
        output.error(f"Failed to store credentials: {e}")
        raise typer.Exit(1)
