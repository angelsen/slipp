"""Vault secret management commands."""

from pathlib import Path

import typer

from slipp import output
from slipp.output import format_path
from slipp.services.config import ConfigResolver
from slipp.services.vault import (
    SecretSynchronizer,
    append_to_vault,
    encrypt_string,
    generate_jwk,
    generate_secret,
    list_keys,
    vault_password_file,
)
from slipp.utils.errors import (
    ProjectNotFoundError,
    PullTimeoutError,
    SourceNotFoundError,
    VaultError,
    VaultNotFoundError,
    VaultSyncError,
)


secrets_app = typer.Typer(
    name="secrets",
    help="Manage vault secrets",
)


def _get_resolver(target: str | None) -> ConfigResolver:
    """Get ConfigResolver for the appropriate project context.

    Resolution order:
    1. If target is a file path that exists, use cwd as project root
    2. If target is a project name, use that project's root
    3. If target is None, use cwd as project root

    Args:
        target: Project name, path to vault file, or None

    Returns:
        ConfigResolver bound to the correct project root

    Raises:
        typer.Exit: If project not found
    """
    if target and Path(target).exists():
        return ConfigResolver()

    if target:
        try:
            return ConfigResolver.for_project(target)
        except ProjectNotFoundError:
            output.error(f"Project '{target}' not found")
            output.hint("Use 'slipp projects' to list registered projects")
            raise typer.Exit(1)

    return ConfigResolver()


def _list_available_vaults() -> None:
    """Show all registered projects that have vaults configured (discovery mode)."""
    from slipp.services.config import LocalConfigService
    from slipp.services.registry import ProjectRegistry
    from slipp.services.secrets import get_source, list_sources

    registry = ProjectRegistry()
    projects = registry.list_all()

    vaults_found: list[dict[str, str]] = []
    for project in projects:
        local_config = LocalConfigService.load(project.project_path)
        if local_config and local_config.vault:
            vault_path = project.project_path / local_config.vault
            if vault_path.exists():
                try:
                    keys = list_keys(vault_path)
                    count = str(len(keys))
                except Exception:
                    count = "?"
                vaults_found.append(
                    {
                        "project": project.name,
                        "vault": local_config.vault,
                        "secrets": count,
                    }
                )

    if vaults_found:
        output.info("Available vaults:")
        output.table(vaults_found)
    else:
        output.warning("No vaults found in any registered project")

    sources = list_sources()
    if sources:
        output.blank()
        output.info("Pull sources:")
        for name in sources:
            src = get_source(name)
            output.bullet(f"{name} - {src.get_description()}", indent=1)


@secrets_app.command(name="list")
def list_secrets(
    targets: list[str] = typer.Argument(
        None, help="Project name(s) or vault file path(s) (discovery mode if omitted)"
    ),
    secret_name: str = typer.Option(
        None, "--name", "-n", help="Secret name to get template string for"
    ),
) -> None:
    """List secrets in vault(s), or show available vaults."""
    if not targets:
        _list_available_vaults()
        return

    for i, target in enumerate(targets):
        if i > 0:
            output.blank()

        resolver = _get_resolver(target)
        cli_vault = target if Path(target).exists() else None
        vault_path = resolver.resolve_vault(cli_vault=cli_vault)

        if not vault_path:
            output.warning(f"No vault configured for '{target}'")
            continue

        try:
            keys = list_keys(vault_path)
        except FileNotFoundError:
            output.error(
                f"Vault file not found: {format_path(vault_path, resolver.project_root)}"
            )
            continue

        if secret_name:
            if secret_name not in keys:
                output.error(f"Secret '{secret_name}' not found in {target}")
                continue
            output.stdout(f"{{{{ {secret_name} }}}}")
            continue

        if not keys:
            output.info(f"No secrets found in {target}")
            continue

        output.info(f"Secrets in {format_path(vault_path, resolver.project_root)}:")
        for key in keys:
            output.bullet(key, indent=1)


@secrets_app.command(name="add")
def add_secret(
    name: str = typer.Argument(..., help="Secret name (e.g., vault_db_password)"),
    target: str = typer.Argument(
        None, help="Project name or vault file path (uses local config if omitted)"
    ),
    num_bytes: int = typer.Option(
        32, "--bytes", "-b", help="Bytes of entropy (default: 32 = 256-bit)"
    ),
    encoding: str = typer.Option(
        "hex",
        "--encoding",
        "-e",
        help="Output encoding: hex (default), base64, or ulid",
    ),
    jwk: bool = typer.Option(False, "--jwk", help="Generate RSA JWK keypair"),
    bits: int = typer.Option(
        2048, "--bits", help="RSA key size for --jwk (default: 2048)"
    ),
) -> None:
    """Generate and add a secret to a vault."""
    if encoding not in ("hex", "base64", "ulid"):
        output.error(f"Invalid encoding '{encoding}'. Use: hex, base64, or ulid")
        raise typer.Exit(1)

    resolver = _get_resolver(target)

    cli_vault = target if target and Path(target).exists() else None
    vault_path = resolver.resolve_vault(cli_vault=cli_vault)

    if not vault_path:
        output.error("No vault configured")
        output.hint("Specify project: ac secrets add <name> <project>")
        output.hint("Or configure vault in slipp.yaml")
        raise typer.Exit(1)

    if not vault_path.exists():
        output.error(
            f"Vault file not found: {format_path(vault_path, resolver.project_root)}"
        )
        raise typer.Exit(1)

    if jwk:
        secret = generate_jwk(bits)
    elif encoding == "ulid":
        secret = generate_secret(encoding="ulid")
    else:
        secret = generate_secret(num_bytes, encoding)

    try:
        with vault_password_file(confirm=False) as pw_file:
            encrypted = encrypt_string(secret, name, password_file=pw_file)
    except VaultNotFoundError as e:
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
    path: Path = typer.Argument(..., help="Path to vars.yml file"),
    num_bytes: int = typer.Option(
        32, "--bytes", "-b", help="Bytes of entropy (default: 32 = 256-bit)"
    ),
    encoding: str = typer.Option(
        "hex",
        "--encoding",
        "-e",
        help="Output encoding: hex (default), base64, or ulid",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing vault.yml"
    ),
) -> None:
    """Scan YAML for vault references and auto-generate secrets."""
    if encoding not in ("hex", "base64", "ulid"):
        output.error(f"Invalid encoding '{encoding}'. Use: hex, base64, or ulid")
        raise typer.Exit(1)

    project_root = Path.cwd()
    vault_path = path.parent / "vault.yml"

    if not path.exists():
        output.error(f"File not found: {format_path(path, project_root)}")
        raise typer.Exit(1)

    if not path.is_file():
        output.error(f"Not a file: {format_path(path, project_root)}")
        raise typer.Exit(1)

    if vault_path.exists() and not force:
        output.error(
            f"Vault file already exists: {format_path(vault_path, project_root)}"
        )
        output.hint("Use --force to overwrite")
        raise typer.Exit(1)

    content = path.read_text()
    synchronizer = SecretSynchronizer(num_bytes=num_bytes, encoding=encoding)
    refs = synchronizer.find_vault_references(content)

    if not refs:
        output.info("No vault references found")
        output.hint("Vault references use pattern: {{ vault_variable_name }}")
        return

    output.info(f"Found {len(refs)} vault reference(s):")
    for ref in sorted(refs):
        output.bullet(ref, indent=1)

    try:
        synchronizer.sync(path, vault_path, force=force)
    except VaultSyncError as e:
        output.error(str(e))
        raise typer.Exit(1)

    output.success(f"Created {format_path(vault_path, project_root)}")
    output.hint(
        f"Encrypt with: ansible-vault encrypt {format_path(vault_path, project_root)}"
    )


@secrets_app.command(name="pull")
def pull_secrets(
    source: str = typer.Argument(..., help="Secret source (e.g., nor-auth)"),
    target: str = typer.Argument(
        None, help="Target vault (project name or path, uses local config if omitted)"
    ),
    timeout: int = typer.Option(300, "--timeout", "-t", help="Timeout in seconds"),
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
        output.error("Timed out waiting for approval (5 minutes)")
        output.hint("Make sure to approve the export in your browser")
        raise typer.Exit(1)
    except VaultError as e:
        output.error(f"Failed to store credentials: {e}")
        raise typer.Exit(1)
