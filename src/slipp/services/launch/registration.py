"""Shared project-registration logic for launch and scaffold pipelines."""

from pathlib import Path
from typing import Any

from slipp import output
from slipp.models.local_config import ExposeEntry, LocalConfig
from slipp.models.service import Runtime
from slipp.services.config import LocalConfigService
from slipp.services.registry import ProjectRegistry
from slipp.utils.errors import LaunchError


def register_project(
    *,
    name: str,
    project_root: Path,
    inventory_path: str,
    playbook_path: str,
    runtime: str | None = None,
    roles_path: list[str] | None = None,
    galaxy_path: str | None = None,
    vault_path: str | None = None,
    project_dirs: list[str] | None = None,
    expose: dict[str, ExposeEntry] | None = None,
) -> None:
    """Create slipp.yaml and register the project in the global registry.

    Raises on failure rather than warning and continuing, so a broken
    registration can't be masked by a false "complete!" summary at the end
    of the pipeline.

    Args:
        name: Project identifier
        project_root: Project root directory
        inventory_path: Relative path to inventory
        playbook_path: Relative path to playbook
        runtime: How the app runs (systemd/docker/podman), if known
        roles_path: Relative roles directories (drives managed_roles scanning)
        galaxy_path: Install path for ansible-galaxy, if any
        vault_path: Relative path to vault file, if any
        project_dirs: --dir values slipp launch scanned, see
            LocalConfig.project_dirs
        expose: Service routing block, see LocalConfig.expose

    Raises:
        LaunchError: If config creation or registration fails
    """
    config_path = LocalConfigService.get_config_path(project_root)
    config_preexisted = config_path.is_file()

    def build_new() -> LocalConfig:
        return LocalConfigService.build(
            name=name,
            inventory_path=inventory_path,
            playbook_path=playbook_path,
            runtime=runtime,
            roles_path=roles_path,
            galaxy_path=galaxy_path,
            vault_path=vault_path,
            project_root=project_root,
            project_dirs=project_dirs,
            expose=expose,
        )

    def mutate(_config: LocalConfig) -> dict[str, Any]:
        # Only set fields this call was given explicit values for, so
        # re-registering an existing project (e.g. re-running `slipp
        # projects add`) doesn't clobber tag_presets/runs/expose that
        # a full-config rebuild would silently drop.
        changes: dict[str, Any] = {
            "name": name,
            "inventory": inventory_path,
            "playbook": playbook_path,
        }
        if runtime is not None:
            changes["runtime"] = Runtime.parse(runtime)
        if roles_path is not None:
            changes["roles_path"] = roles_path
        if galaxy_path is not None:
            changes["galaxy_path"] = galaxy_path
        if vault_path is not None:
            changes["vault"] = vault_path
        if project_dirs is not None:
            changes["project_dirs"] = project_dirs
        if expose is not None:
            changes["expose"] = expose
        return changes

    try:
        LocalConfigService.create_or_update_and_report(
            build_new, mutate, project_root=project_root, name=name
        )
    except Exception as e:
        raise LaunchError(f"Failed to create local config: {e}") from e

    registry = ProjectRegistry()
    try:
        registry.register(name=name, project_path=project_root)
        output.info(f"Registered '{name}' in global registry")
    except Exception as e:
        # Only clean up slipp.yaml if this call created it fresh -- if one
        # already existed, it was merge-updated in place and we have no
        # snapshot of the prior content to restore, so leave it as-is
        # rather than deleting a file we didn't create.
        if not config_preexisted:
            config_path.unlink(missing_ok=True)
        raise LaunchError(f"Failed to register project: {e}") from e
