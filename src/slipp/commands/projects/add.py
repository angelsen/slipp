"""Register Ansible projects with slipp.

Handles project registration by detecting or validating Ansible
project files (inventory, playbooks, roles) and storing configuration
for later use.
"""

from pathlib import Path

import typer

from slipp import output
from slipp.output import format_path
from slipp.services.config import LocalConfigService
from slipp.services.registry import ProjectRegistry

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


def add_command(
    name: str = typer.Argument(..., help="Project name"),
    inventory: str | None = typer.Option(
        None,
        "-i",
        "--inventory",
        help="Inventory file path (auto-detected if not specified)",
    ),
    playbook: str | None = typer.Option(
        None, "--playbook", help="Playbook file path (auto-detected if not specified)"
    ),
    roles: list[str] | None = typer.Option(
        None,
        "--roles",
        help="Role search directories (auto-detected if not specified)",
    ),
    galaxy_path: str | None = typer.Option(
        None,
        "--galaxy-path",
        help="Install path for external roles from requirements.yml",
    ),
    vault: str | None = typer.Option(
        None, "--vault", help="Path to vault.yml for secret management"
    ),
) -> None:
    """Register an Ansible project with slipp."""
    project_root = Path.cwd()

    if inventory:
        inventory_path = project_root / inventory
    else:
        inventory_path = _detect_path(project_root, INVENTORY_PATTERNS)

    if not inventory_path:
        output.error(f"No inventory found (tried: {', '.join(INVENTORY_PATTERNS)})")
        output.hint("Specify with: --inventory <path>")
        raise typer.Exit(1)

    if not inventory_path.exists():
        output.error(
            f"Inventory not found: {format_path(inventory_path, project_root)}"
        )
        raise typer.Exit(1)

    if playbook:
        playbook_path = project_root / playbook
    else:
        playbook_path = _detect_path(project_root, PLAYBOOK_PATTERNS)

    if not playbook_path:
        output.error(f"No playbook found (tried: {', '.join(PLAYBOOK_PATTERNS)})")
        output.hint("Specify with: --playbook <path>")
        raise typer.Exit(1)

    if not playbook_path.exists():
        output.error(f"Playbook not found: {format_path(playbook_path, project_root)}")
        raise typer.Exit(1)

    if roles:
        roles_paths = [project_root / r for r in roles]
    else:
        detected_roles = _detect_path(project_root, ROLES_PATTERNS, is_dir=True)
        roles_paths = [detected_roles] if detected_roles else None

    if not roles_paths:
        output.error(f"No roles directory found (tried: {', '.join(ROLES_PATTERNS)})")
        output.hint("Specify with: --roles <path>")
        raise typer.Exit(1)

    for rp in roles_paths:
        if not rp.is_dir():
            output.error(f"Roles directory not found: {format_path(rp, project_root)}")
            raise typer.Exit(1)

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
    except Exception as e:
        output.error(f"Failed to create config: {e}")
        raise typer.Exit(1)

    try:
        ProjectRegistry().register(name=name, project_path=project_root)
    except Exception as e:
        output.error(f"Failed to register project: {e}")
        raise typer.Exit(1)

    output.success(f"Registered '{name}'")
    output.kv("inventory", inventory_rel, indent=1)
    output.kv("playbook", playbook_rel, indent=1)
    output.kv("roles_path", ", ".join(roles_rel), indent=1)
    if galaxy_path:
        output.kv("galaxy_path", galaxy_path, indent=1)
    if vault:
        output.kv("vault", vault, indent=1)

    LocalConfigService.ensure_logs_gitignore(project_root)
