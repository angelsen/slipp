"""Project registry - CRUD operations for registered projects.

This module handles project registration as a simple path index.
Configuration and hosts are stored in local slipp.yaml files,
parsed on-demand when needed.
"""

from datetime import datetime
from pathlib import Path

from slipp.models.registry import RegisteredProject
from slipp.services.registry.io import RegistryIO


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

        Args:
            name: Project identifier (matches name in slipp.yaml)
            project_path: Absolute path to project directory

        Returns:
            RegisteredProject
        """
        with RegistryIO.lock():
            registry = RegistryIO.load()
            existing = registry.projects.get(name)

            project = RegisteredProject(
                name=name,
                project_path=project_path.resolve(),
                registered_at=existing.registered_at if existing else datetime.now(),
            )

            registry.projects[name] = project
            RegistryIO.save(registry)
        return project

    def unregister(self, name: str) -> bool:
        """Remove a project from the registry.

        Args:
            name: Project name to remove

        Returns:
            True if project was removed, False if not found
        """
        with RegistryIO.lock():
            registry = RegistryIO.load()

            if name in registry.projects:
                del registry.projects[name]
                RegistryIO.save(registry)
                return True

            return False

    def get(self, name: str) -> RegisteredProject | None:
        """Lookup a project by name.

        Args:
            name: Project name to lookup

        Returns:
            RegisteredProject if found, None otherwise
        """
        registry = RegistryIO.load()
        return registry.projects.get(name)

    def list_all(self) -> list[RegisteredProject]:
        """List all registered projects.

        Returns:
            Sorted list of all registered projects
        """
        registry = RegistryIO.load()
        return sorted(registry.projects.values(), key=lambda p: p.name)
