"""Local project configuration model (slipp.yaml).

This module provides the Pydantic model for the local project configuration
stored in slipp.yaml at the project root. This file is git-tracked.
"""

from pydantic import BaseModel, Field, field_validator

from slipp.models.service import LenientRuntime
from slipp.utils.identifiers import validate_config_name


class ExposeEntry(BaseModel):
    """One exposed service route in slipp.yaml's expose: block.

    Maps a detected service (the block's key) to the domain and path
    prefix it should be served on. Seeded by `slipp launch` from the
    default frontend/backend routing convention; edit and redeploy to
    change routing.
    """

    domain: str = Field(..., min_length=1, description="FQDN serving this service")
    path: str = Field(default="/", description="Path prefix on the domain")

    @field_validator("path")
    @classmethod
    def _normalize_path(cls, value: str) -> str:
        """Require a leading slash (hand-edited YAML), drop trailing ones.

        A bare "api" or "" would render a malformed Caddy `handle api*`
        block or a wg-manage route colliding with the domain's root entry.
        """
        if not value.startswith("/"):
            raise ValueError(f"expose path must start with '/', got '{value}'")
        return value.rstrip("/") or "/"


class LocalConfig(BaseModel):
    """Local project configuration stored in slipp.yaml.

    This config is git-tracked and stores project-specific paths.
    The global registry (~/.config/slipp/config.json) stores
    a path index for cross-project access.

    Attributes:
        name: Project identifier (required, appears first in YAML)
        inventory: Path to inventory file (relative to project root)
        playbook: Path to playbook file (default: playbook.yml)
        roles_path: Role directories (sets ANSIBLE_ROLES_PATH)
        galaxy_path: Install destination for ansible-galaxy (from requirements.yml)
        vault: Optional path to vault file
        runtime: How the app runs (systemd/docker/podman); docker/podman are
            auto-detected if not set, systemd must be set explicitly
        managed_roles: Role names for service filtering (auto-populated from roles dirs)
        tag_presets: Named tag presets (name -> ansible args like "--tags setup-all")
        runs: Run profiles (name -> profile dict), see models.run.RunProfile
        project_dirs: The --dir values `slipp launch` scanned to produce
            this project (relative to project root when nested inside it,
            absolute otherwise), recorded so a later re-scan (e.g.
            wg-manage exposure sync) can reproduce the exact same declared
            set instead of falling back to auto-detection, which can
            diverge from an explicit multi-service --dir launch. None for
            projects launched before this was tracked.
    """

    name: str = Field(..., min_length=1, description="Project identifier")
    inventory: str | None = Field(default=None, description="Inventory file path")
    playbook: str = Field(default="playbook.yml", description="Playbook file path")
    roles_path: list[str] = Field(
        default_factory=list, description="Role directories (sets ANSIBLE_ROLES_PATH)"
    )
    galaxy_path: str | None = Field(
        default=None,
        description="Install path for ansible-galaxy (from requirements.yml)",
    )
    vault: str | None = Field(default=None, description="Vault file path")
    runtime: LenientRuntime | None = Field(
        default=None, description="How the app runs (systemd/docker/podman)"
    )
    managed_roles: list[str] = Field(
        default_factory=list, description="Role names for service filtering"
    )
    project_dirs: list[str] | None = Field(
        default=None, description="--dir values slipp launch scanned"
    )
    expose: dict[str, ExposeEntry] | None = Field(
        default=None,
        description="Service routing (service name -> domain/path), seeded by launch",
    )
    tag_presets: dict[str, str] = Field(
        default_factory=dict, description="Named tag presets (name -> ansible args)"
    )
    runs: dict[str, dict] = Field(
        default_factory=dict, description="Run profiles (name -> profile dict)"
    )

    # "allow", not "ignore": a hand-added key services/config/local.py
    # doesn't recognize would otherwise silently vanish from slipp.yaml the
    # next time anything calls save() -- warned about on load, but still
    # destroyed data the user typed in on purpose. save()'s model_dump()
    # round-trips __pydantic_extra__ automatically, so allowing it here is
    # enough to make unknown keys durable instead of one-save-away from lost.
    model_config = {"extra": "allow"}

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        """Project names become systemd units/paths/YAML -- see validator."""
        return validate_config_name(value, "project name")
