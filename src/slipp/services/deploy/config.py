"""Local config persistence for the deploy command."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from slipp import output
from slipp.constants import PLAYBOOK_FILENAME
from slipp.models.service import Runtime
from slipp.services.config import LocalConfigService
from slipp.services.config.detection import PLAYBOOK_PATTERNS, detect_path
from slipp.services.registry import ProjectRegistry
from slipp.utils.errors import (
    ConfigError,
    ConfigParseError,
    RegistryCollisionError,
    SlippError,
)


@dataclass
class DeployOverrides:
    """CLI flag overrides for deploy config resolution and persistence.

    Every field mirrors a `slipp deploy`/`slipp up` CLI flag that can
    override the project's slipp.yaml. Grouped so run_deploy() and
    persist_config_updates() take one value instead of the same five
    flags threaded through both signatures by hand.
    """

    inventory: str | None = None
    playbook: str | None = None
    roles: list[str] | None = None
    vault: str | None = None
    galaxy_path: str | None = None
    runtime: str | None = None

    def any_set(self) -> bool:
        """Whether any override was actually given on the CLI."""
        return any(
            [
                self.inventory,
                self.playbook,
                self.roles,
                self.vault,
                self.galaxy_path,
                self.runtime,
            ]
        )


def ensure_local_config(
    name: str,
    inventory: str,
    playbook: str | None,
    roles: list[str],
    vault: str | None,
    project_root: Path,
    runtime: str | None = None,
    galaxy_path: str | None = None,
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
        galaxy_path: Install path for external roles from requirements.yml.

    Raises:
        ConfigError: If the inventory file doesn't exist or config creation fails.
    """
    inventory_path = Path(inventory)

    if not inventory_path.exists():
        raise ConfigError(
            f"Inventory file not found: {output.format_path(inventory_path, project_root)}"
        )

    if playbook:
        playbook_path = playbook
    else:
        detected = detect_path(project_root, PLAYBOOK_PATTERNS)
        playbook_path = (
            str(detected.relative_to(project_root)) if detected else PLAYBOOK_FILENAME
        )

    try:
        # On the update path (config already exists), only fields the caller
        # actually passed a flag for are touched -- playbook_path may be
        # auto-detected rather than explicit, so it's only persisted when
        # `playbook` itself was given, matching roles/vault/galaxy_path/runtime.
        changes: dict[str, str | Runtime | list[str]] = {
            "name": name,
            "inventory": inventory,
        }
        if playbook:
            changes["playbook"] = playbook
        if roles:
            changes["roles_path"] = roles
        if galaxy_path:
            changes["galaxy_path"] = galaxy_path
        if vault:
            changes["vault"] = vault
        if runtime:
            changes["runtime"] = Runtime.parse(runtime)

        LocalConfigService.create_or_update_and_report(
            lambda: LocalConfigService.build(
                name=name,
                inventory_path=inventory,
                playbook_path=playbook_path,
                roles_path=roles if roles else None,
                galaxy_path=galaxy_path,
                vault_path=vault,
                runtime=runtime,
                project_root=project_root,
            ),
            lambda c: changes,
            project_root=project_root,
            name=name,
        )
    except (ValueError, OSError) as e:
        # ValueError: bad --runtime value (invalid Runtime enum member).
        # OSError: config file couldn't be written (permissions, disk).
        # Anything else is a real bug -- let it propagate as a traceback
        # rather than mislabeling it as a config problem.
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


def _resolve_or_warn(value: str, description: str, project_root: Path) -> str | None:
    """Resolve a CLI flag path to project-root-relative, warning if outside root."""
    relative = _to_root_relative(value, project_root)
    if relative is None:
        output.warning(
            f"Not persisting {description}: path is outside project root {project_root}"
        )
    return relative


def persist_config_updates(overrides: DeployOverrides, project_root: Path) -> None:
    """Persist CLI flag overrides into slipp.yaml after a successful deploy.

    Args:
        overrides: CLI flag overrides (inventory/playbook/roles/vault/
            galaxy_path/runtime), if given.
        project_root: Root the deploy resolved against (cwd or a discovered
            enclosing project) -- flag paths are converted to be relative to
            this before persisting.
    """
    changes: dict[str, Any] = {}

    def _set(key: str, flag_value: str) -> None:
        relative = _resolve_or_warn(flag_value, f"{key}={flag_value}", project_root)
        if relative is not None:
            changes[key] = relative

    if overrides.inventory:
        _set("inventory", overrides.inventory)
    if overrides.playbook:
        _set("playbook", overrides.playbook)
    if overrides.roles:
        resolved_roles = [
            relative
            for role in overrides.roles
            if (
                relative := _resolve_or_warn(
                    role, f"roles_path entry {role}", project_root
                )
            )
            is not None
        ]
        if resolved_roles:
            changes["roles_path"] = resolved_roles
    if overrides.galaxy_path:
        _set("galaxy_path", overrides.galaxy_path)
    if overrides.vault:
        _set("vault", overrides.vault)
    if overrides.runtime:
        changes["runtime"] = Runtime.parse(overrides.runtime)

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
    """Register the project in the global registry.

    Best-effort for most registry failures, but a name collision (this name
    already registered to a different directory) must not be swallowed into
    a warning -- every other command (logs/ssh/secrets/vault) trusts the
    registry to resolve this name to the right checkout.

    Args:
        project_name: Name to register the project under.
        project_root: Root the deploy resolved against (cwd or a discovered
            enclosing project) -- registers this, not necessarily cwd.

    Raises:
        RegistryCollisionError: If project_name is already registered to a
            different directory.
    """
    try:
        ProjectRegistry().register(name=project_name, project_path=project_root)
    except RegistryCollisionError:
        raise
    except SlippError:
        output.warning("Could not register project in global registry")
