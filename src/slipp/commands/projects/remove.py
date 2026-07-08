"""Unregister a project from the global registry."""

from typing import Annotated

import typer

from slipp import output
from slipp.services.registry import ProjectRegistry


def remove_command(
    project_name: Annotated[str, typer.Argument(help="Project name to unregister")],
) -> None:
    """Unregister a project from the global registry."""
    project_registry = ProjectRegistry()
    removed = project_registry.unregister(project_name)

    if removed:
        output.success(f"Unregistered project '{project_name}'")
    else:
        output.warning(f"Project '{project_name}' not found in registry")
        output.hint("Run 'slipp projects list' to see registered projects")
