"""Registry models for global project tracking.

This module provides Pydantic models for the global project registry
stored at ~/.config/slipp/config.json

The registry is a simple path index for cross-project access.
All project configuration is stored in the local slipp.yaml.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from slipp.models.types import PathStr


class RegisteredProject(BaseModel):
    """A registered project in the global registry.

    Minimal path index for cross-project lookup.
    All configuration is in local slipp.yaml - hosts are parsed on demand.

    Attributes:
        name: Project identifier (matches local config name)
        project_path: Absolute path to project directory
        registered_at: When project was registered (informational)
    """

    name: str = Field(..., min_length=1)
    project_path: PathStr
    registered_at: datetime = Field(default_factory=datetime.now)


class GlobalRegistry(BaseModel):
    """Global project registry structure.

    Attributes:
        projects: Map of project name → RegisteredProject

    The registry is now a simple path index. All configuration
    including hosts is stored in local slipp.yaml files.
    """

    projects: dict[str, RegisteredProject] = Field(default_factory=dict)
