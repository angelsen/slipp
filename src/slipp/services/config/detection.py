"""Auto-detection of Ansible project files (inventory, playbook, roles).

Single source of truth for the conventional paths slipp looks for when a
project doesn't explicitly specify them, shared by `slipp projects add`
(explicit registration) and `slipp deploy` (implicit registration).
"""

from pathlib import Path

INVENTORY_PATTERNS = ["inventory/hosts", "inventory.yml", "hosts"]
PLAYBOOK_PATTERNS = ["playbook.yml", "site.yml", "main.yml"]
ROLES_PATTERNS = ["roles"]


def detect_path(
    project_root: Path, patterns: list[str], is_dir: bool = False
) -> Path | None:
    """Return first existing path from patterns, or None.

    Args:
        project_root: Base directory paths are resolved relative to.
        patterns: Candidate relative paths to check, in priority order.
        is_dir: If True, check for a directory instead of a file.

    Returns:
        The first matching path, or None if none of the patterns exist.
    """
    for pattern in patterns:
        path = project_root / pattern
        if is_dir and path.is_dir():
            return path
        elif not is_dir and path.is_file():
            return path
    return None


def has_caddy_role(project_root: Path) -> bool:
    """True if this project's generated Ansible project has a Caddy role.

    Used to decide whether a project's public URL is Caddy-fronted
    (:443/https) or exposed directly on its app_port (:app_port/http).
    """
    return (project_root / "roles" / "caddy").exists()


def has_wg_manage_role(project_root: Path) -> bool:
    """True if this project's generated Ansible project has a wg-manage-exposure role."""
    return (project_root / "roles" / "wg-manage-exposure").exists()
