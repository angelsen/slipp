"""Register Ansible projects with slipp.

Handles project registration by detecting or validating Ansible
project files (inventory, playbooks, roles) and storing configuration
for later use.
"""

from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.output import format_path
from slipp.services.config import LocalConfigService
from slipp.services.registry import ProjectRegistry
from slipp.utils.errors import ConfigError

INVENTORY_PATTERNS = ["inventory/hosts", "inventory.yml", "hosts"]
PLAYBOOK_PATTERNS = ["playbook.yml", "site.yml", "main.yml"]
ROLES_PATTERNS = ["roles"]


def _detect_path(
    project_root: Path, patterns: list[str], is_dir: bool = False
) -> Path | None:
    """Return first existing path from patterns, or None."""
    for pattern in patterns:
        path = project_root / pattern
        if is_dir and path.is_dir():
            return path
        elif not is_dir and path.is_file():
            return path
    return None


def _resolve_required(
    project_root: Path,
    cli_value: str | None,
    patterns: list[str],
    kind: str,
    flag_hint: str,
    *,
    is_dir: bool = False,
) -> Path:
    """Resolve a required file/dir: explicit CLI value, else auto-detect, else exit.

    Args:
        project_root: Base directory paths are resolved relative to.
        cli_value: Explicit path from a CLI flag, if given.
        patterns: Candidate relative paths to auto-detect when cli_value is None.
        kind: Human name for error messages (e.g. "inventory", "playbook").
        flag_hint: Flag to suggest in the "specify with" hint.
        is_dir: If True, resolve/validate as a directory instead of a file.

    Returns:
        The resolved, existing path.

    Raises:
        typer.Exit: If no candidate is found, or the resolved path doesn't exist.
    """
    path = (
        project_root / cli_value
        if cli_value
        else _detect_path(project_root, patterns, is_dir=is_dir)
    )

    if not path:
        output.error(f"No {kind} found (tried: {', '.join(patterns)})")
        output.hint(f"Specify with: {flag_hint}")
        raise typer.Exit(1)

    exists = path.is_dir() if is_dir else path.exists()
    if not exists:
        output.error(
            f"{kind.capitalize()} not found: {format_path(path, project_root)}"
        )
        raise typer.Exit(1)

    return path


def add_command(
    name: Annotated[str, typer.Argument(help="Project name")],
    inventory: Annotated[
        str | None,
        typer.Option(
            "-i",
            "--inventory",
            help="Inventory file path (auto-detected if not specified)",
        ),
    ] = None,
    playbook: Annotated[
        str | None,
        typer.Option(
            "--playbook", help="Playbook file path (auto-detected if not specified)"
        ),
    ] = None,
    roles: Annotated[
        list[str] | None,
        typer.Option(
            "--roles",
            help="Role search directories (auto-detected if not specified)",
        ),
    ] = None,
    galaxy_path: Annotated[
        str | None,
        typer.Option(
            "--galaxy-path",
            help="Install path for external roles from requirements.yml",
        ),
    ] = None,
    vault: Annotated[
        str | None,
        typer.Option("--vault", help="Path to vault.yml for secret management"),
    ] = None,
) -> None:
    """Register an Ansible project with slipp."""
    # Intentionally no root discovery: this command creates/claims THIS
    # directory as a project root. Walking up would risk overwriting an
    # enclosing project's slipp.yaml.
    project_root = Path.cwd()

    inventory_path = _resolve_required(
        project_root, inventory, INVENTORY_PATTERNS, "inventory", "--inventory <path>"
    )
    playbook_path = _resolve_required(
        project_root, playbook, PLAYBOOK_PATTERNS, "playbook", "--playbook <path>"
    )

    if roles:
        roles_paths = [project_root / r for r in roles]
        for rp in roles_paths:
            if not rp.is_dir():
                output.error(
                    f"Roles directory not found: {format_path(rp, project_root)}"
                )
                raise typer.Exit(1)
    else:
        roles_paths = [
            _resolve_required(
                project_root,
                None,
                ROLES_PATTERNS,
                "roles directory",
                "--roles <path>",
                is_dir=True,
            )
        ]

    inventory_rel = str(inventory_path.relative_to(project_root))
    playbook_rel = str(playbook_path.relative_to(project_root))
    roles_rel = [str(rp.relative_to(project_root)) for rp in roles_paths]

    if galaxy_path and galaxy_path not in roles_rel:
        roles_rel.append(galaxy_path)

    try:
        LocalConfigService.create(
            name=name,
            inventory_path=inventory_rel,
            playbook_path=playbook_rel,
            roles_path=roles_rel,
            galaxy_path=galaxy_path,
            vault_path=vault,
            project_root=project_root,
        )
    except OSError as e:
        raise ConfigError(f"Failed to create config: {e}") from e

    try:
        ProjectRegistry().register(name=name, project_path=project_root)
    except OSError as e:
        raise ConfigError(f"Failed to register project: {e}") from e

    output.success(f"Registered '{name}'")
    output.kv("inventory", inventory_rel, indent=1)
    output.kv("playbook", playbook_rel, indent=1)
    output.kv("roles_path", ", ".join(roles_rel), indent=1)
    if galaxy_path:
        output.kv("galaxy_path", galaxy_path, indent=1)
    if vault:
        output.kv("vault", vault, indent=1)

    LocalConfigService.ensure_logs_gitignore(project_root)
