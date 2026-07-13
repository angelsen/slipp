"""Local config persistence for the deploy command."""

import os
from pathlib import Path
from typing import Any

from slipp import output
from slipp.models.service import Runtime
from slipp.output import format_path
from slipp.services.config import LocalConfigService
from slipp.services.config.detection import PLAYBOOK_PATTERNS, detect_path
from slipp.services.registry import ProjectRegistry
from slipp.utils.errors import ConfigError, ConfigParseError, SlippError


def ensure_local_config(
    name: str,
    inventory: str,
    playbook: str | None,
    roles: list[str],
    vault: str | None,
    project_root: Path,
    runtime: str | None = None,
) -> None:
    """Create or update slipp.yaml when --name and --inventory are both given.

    Args:
        name: Project name.
        inventory: Inventory file path (relative to project_root).
        playbook: Playbook file path. Auto-detected (same patterns as
            `slipp projects add`) when not given, falling back to
            "playbook.yml" if nothing is found.
        roles: Role search directories.
        vault: Vault file path.
        project_root: Project root directory.
        runtime: How the app runs (systemd/docker/podman), if known. Without
            this, external projects have no runtime in slipp.yaml and every
            operational command (ssh/exec/logs/ps/status) falls back to
            RuntimeDetector's docker/podman-only playbook grep.

    Raises:
        ConfigError: If the inventory file doesn't exist or config creation fails.
    """
    inventory_path = Path(inventory)

    if not inventory_path.exists():
        raise ConfigError(
            f"Inventory file not found: {format_path(inventory_path, project_root)}"
        )

    if playbook:
        playbook_path = playbook
    else:
        detected = detect_path(project_root, PLAYBOOK_PATTERNS)
        playbook_path = (
            str(detected.relative_to(project_root)) if detected else "playbook.yml"
        )

    try:
        if LocalConfigService.exists(project_root):
            changes: dict[str, str | Runtime] = {"name": name, "inventory": inventory}
            if runtime:
                changes["runtime"] = Runtime(runtime.lower())
            LocalConfigService.update(changes, project_root=project_root)
            output.info(f"Updated slipp.yaml with name '{name}'")
        else:
            LocalConfigService.create(
                name=name,
                inventory_path=inventory,
                playbook_path=playbook_path,
                roles_path=roles if roles else None,
                vault_path=vault,
                runtime=runtime,
                project_root=project_root,
            )
            output.info(f"Created slipp.yaml with name '{name}'")
    except Exception as e:
        raise ConfigError(f"Failed to create config: {e}") from e


def _to_root_relative(flag_value: str, project_root: Path) -> str | None:
    """Convert a cwd-relative CLI flag path to project_root-relative.

    slipp.yaml paths are always interpreted relative to project_root
    (see ConfigResolver.resolve), but CLI flags like -i/-p/--vault are
    resolved relative to the process cwd, standard CLI semantics. When
    project_root is a discovered enclosing project (cwd is a subdirectory
    of it), persisting the flag verbatim would silently mean something
    different on the next run. Absolute paths need no conversion.

    Returns None (and the caller should skip persisting this key) if the
    path falls outside project_root -- there is no root-relative path to
    write.
    """
    path = Path(flag_value)
    if path.is_absolute():
        return flag_value

    relative = os.path.relpath((Path.cwd() / path).resolve(), project_root)
    if relative.startswith(".."):
        return None
    return relative


def persist_config_updates(
    inventory: str | None,
    playbook: str | None,
    roles_list: list[str] | None,
    galaxy_path_flag: str | None,
    vault: str | None,
    project_root: Path,
    runtime: str | None = None,
) -> None:
    """Persist CLI flag overrides into slipp.yaml after a successful deploy.

    Args:
        inventory: Inventory path CLI override, if given.
        playbook: Playbook path CLI override, if given.
        roles_list: Role search directories CLI override, if given.
        galaxy_path_flag: Galaxy install path CLI override, if given.
        vault: Vault path CLI override, if given.
        project_root: Root the deploy resolved against (cwd or a discovered
            enclosing project) -- flag paths are converted to be relative to
            this before persisting.
        runtime: Runtime CLI override, if given.
    """
    changes: dict[str, Any] = {}

    def _set(key: str, flag_value: str) -> None:
        relative = _to_root_relative(flag_value, project_root)
        if relative is None:
            output.warning(
                f"Not persisting {key}={flag_value}: path is outside "
                f"project root {project_root}"
            )
            return
        changes[key] = relative

    if inventory:
        _set("inventory", inventory)
    if playbook:
        _set("playbook", playbook)
    if roles_list:
        merged_roles = list(roles_list)
        if galaxy_path_flag and galaxy_path_flag not in merged_roles:
            merged_roles.append(galaxy_path_flag)
        resolved_roles = []
        for role in merged_roles:
            relative = _to_root_relative(role, project_root)
            if relative is None:
                output.warning(
                    f"Not persisting roles_path entry {role}: path is outside "
                    f"project root {project_root}"
                )
                continue
            resolved_roles.append(relative)
        if resolved_roles:
            changes["roles_path"] = resolved_roles
    if galaxy_path_flag:
        _set("galaxy_path", galaxy_path_flag)
    if vault:
        _set("vault", vault)
    if runtime:
        changes["runtime"] = Runtime(runtime.lower())

    if not changes:
        return

    try:
        LocalConfigService.update(changes, project_root=project_root)
        output.info("Updated slipp.yaml")
    except ConfigParseError:
        output.warning("Config flags ignored - no slipp.yaml exists")
        output.hint(
            "Use --name to create config: slipp deploy --name <name> -i <inventory>"
        )


def ensure_project_registered(project_name: str, project_root: Path) -> None:
    """Best-effort registration of the project in the global registry.

    Args:
        project_name: Name to register the project under.
        project_root: Root the deploy resolved against (cwd or a discovered
            enclosing project) -- registers this, not necessarily cwd.
    """
    try:
        ProjectRegistry().register(name=project_name, project_path=project_root)
    except SlippError:
        output.warning("Could not register project in global registry")
