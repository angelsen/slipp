"""Shared project-registration logic for launch and scaffold pipelines."""

from pathlib import Path

from slipp import output
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
    galaxy_path: str | None = None,
    vault_path: str | None = None,
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
        galaxy_path: Install path for ansible-galaxy, if any
        vault_path: Relative path to vault file, if any

    Raises:
        LaunchError: If config creation or registration fails
    """
    try:
        LocalConfigService.create(
            name=name,
            inventory_path=inventory_path,
            playbook_path=playbook_path,
            runtime=runtime,
            galaxy_path=galaxy_path,
            vault_path=vault_path,
            project_root=project_root,
        )
        output.success(f"Created slipp.yaml with name '{name}'")
    except Exception as e:
        raise LaunchError(f"Failed to create local config: {e}") from e

    registry = ProjectRegistry()
    existing = registry.get(name)
    if existing and existing.project_path != project_root.resolve():
        output.warning(
            f"'{name}' was registered at {existing.project_path}; "
            f"re-pointing to {project_root}"
        )

    try:
        registry.register(name=name, project_path=project_root)
        output.info(f"Registered '{name}' in global registry")
    except Exception as e:
        raise LaunchError(f"Failed to register project: {e}") from e
