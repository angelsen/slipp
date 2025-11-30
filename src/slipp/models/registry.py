"""Registry models for global project tracking.

This module provides Pydantic models for the global project registry
stored at ~/.config/slipp/config.json

The registry is a simple path index for cross-project access.
All project configuration is stored in the local slipp.yaml.
"""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


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
    project_path: Path
    registered_at: datetime = Field(default_factory=datetime.now)

    model_config = {"arbitrary_types_allowed": True}


class GlobalRegistry(BaseModel):
    """Global project registry structure.

    Attributes:
        version: Registry format version (for future migrations)
        projects: Map of project name → RegisteredProject

    The registry is now a simple path index. All configuration
    including hosts is stored in local slipp.yaml files.
    """

    version: str = Field(default="3.0")  # Bumped for local-first refactor
    projects: dict[str, RegisteredProject] = Field(default_factory=dict)

    def to_json_dict(self) -> dict:
        """Convert to JSON-serializable dict.

        Returns:
            Dictionary with all fields converted to JSON-compatible types
        """
        return {
            "version": self.version,
            "projects": {
                name: {
                    "name": proj.name,
                    "project_path": str(proj.project_path),
                    "registered_at": proj.registered_at.isoformat(),
                }
                for name, proj in self.projects.items()
            },
        }
