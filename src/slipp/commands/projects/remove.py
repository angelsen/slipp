"""Unregister a project from the global registry."""

import typer

from slipp import output
from slipp.services.registry import ProjectRegistry


def remove_command(
    ctx: typer.Context,
    project_name: str = typer.Argument(..., help="Project name to unregister"),
):
    """Unregister a project from the global registry.

    Args:
        project_name: Name of the project to unregister.
    """
    project_registry = ProjectRegistry()
    removed = project_registry.unregister(project_name)

    if removed:
        output.success(f"Unregistered project '{project_name}'")
    else:
        output.warning(f"Project '{project_name}' not found in registry")
        output.hint("Run 'ac projects list' to see registered projects")
