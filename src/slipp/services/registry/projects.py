"""Project registry - CRUD operations for registered projects.

This module handles project registration as a simple path index.
Configuration and hosts are stored in local slipp.yaml files,
parsed on-demand when needed.
"""

from datetime import datetime
from pathlib import Path

from slipp.models.registry import RegisteredProject
from slipp.services.registry.io import RegistryService
from slipp.utils.errors import RegistryCollisionError


class ProjectRegistry:
    """Manages project registration and lookup.

    The registry is a simple path index - all configuration including
    hosts is stored in local slipp.yaml files and parsed on-demand.

    Responsibilities:
    - Register/unregister projects (name → path mapping)
    - Lookup projects by name
    - List all projects
    """

    def register(self, name: str, project_path: Path) -> RegisteredProject:
        """Register a project in the global registry.

        Creates a name → path mapping. All configuration is stored
        in the project's local slipp.yaml file.

        A name is an identity binding, not a version to overwrite - if it's
        already registered to a different directory, that's almost always
        either a stale leftover or two checkouts accidentally sharing a
        name, and every other command (logs/ssh/secrets/vault) would then
        silently target the wrong one. Callers that genuinely want to
        re-point a name must say so explicitly via `slipp projects remove`
        first, same as `git remote`/`docker run --name` refuse to silently
        rebind an existing name.

        Args:
            name: Project identifier (matches name in slipp.yaml)
            project_path: Absolute path to project directory

        Returns:
            RegisteredProject

        Raises:
            RegistryCollisionError: If `name` is already registered to a
                different directory.
        """
        with RegistryService.lock():
            registry = RegistryService.load()
            existing = registry.projects.get(name)
            resolved = project_path.resolve()

            if existing and existing.project_path != resolved:
                raise RegistryCollisionError(
                    f"'{name}' is already registered at {existing.project_path}. "
                    f"Run 'slipp projects remove {name}' first to re-point it."
                )

            project = RegisteredProject(
                name=name,
                project_path=resolved,
                registered_at=existing.registered_at if existing else datetime.now(),
            )

            registry.projects[name] = project
            RegistryService.save(registry)
        return project

    def unregister(self, name: str) -> bool:
        """Remove a project from the registry.

        Args:
            name: Project name to remove

        Returns:
            True if project was removed, False if not found
        """
        with RegistryService.lock():
            registry = RegistryService.load()

            if name in registry.projects:
                del registry.projects[name]
                RegistryService.save(registry)
                return True

            return False

    def get(self, name: str) -> RegisteredProject | None:
        """Lookup a project by name.

        Args:
            name: Project name to lookup

        Returns:
            RegisteredProject if found, None otherwise
        """
        registry = RegistryService.load()
        return registry.projects.get(name)

    def list_all(self) -> list[RegisteredProject]:
        """List all registered projects.

        Returns:
            Sorted list of all registered projects
        """
        registry = RegistryService.load()
        return sorted(registry.projects.values(), key=lambda p: p.name)
