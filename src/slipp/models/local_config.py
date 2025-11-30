"""Local project configuration model (slipp.yaml).

This module provides the Pydantic model for the local project configuration
stored in slipp.yaml at the project root. This file is git-tracked.
"""

from pydantic import BaseModel, Field


class LocalConfig(BaseModel):
    """Local project configuration stored in slipp.yaml.

    This config is git-tracked and stores project-specific paths.
    The global registry (~/.config/slipp/config.json) stores
    a path index for cross-project access.

    Attributes:
        name: Project identifier (required, appears first in YAML)
        inventory: Path to inventory file (relative to project root)
        playbook: Path to playbook file (default: playbook.yml)
        roles: Role directories to scan for service filtering
        vault: Optional path to vault file
        managed_roles: Role names for service filtering (auto-populated from roles dirs)
        tag_presets: Named tag presets (name -> ansible args like "--tags setup-all")
    """

    name: str = Field(..., min_length=1, description="Project identifier")
    inventory: str = Field(..., description="Inventory file path")
    playbook: str = Field(default="playbook.yml", description="Playbook file path")
    roles: list[str] = Field(default_factory=list, description="Role directories")
    vault: str | None = Field(default=None, description="Vault file path")
    managed_roles: list[str] = Field(
        default_factory=list, description="Role names for service filtering"
    )
    tag_presets: dict[str, str] = Field(
        default_factory=dict, description="Named tag presets (name -> ansible args)"
    )

    model_config = {"extra": "ignore"}
