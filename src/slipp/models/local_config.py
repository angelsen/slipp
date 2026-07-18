"""Local project configuration model (slipp.yaml).

This module provides the Pydantic model for the local project configuration
stored in slipp.yaml at the project root. This file is git-tracked.
"""

import re

from pydantic import BaseModel, Field, field_validator, model_validator

from slipp.models.service import LenientRuntime
from slipp.utils.identifiers import validate_config_name

_LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


class ExposeEntry(BaseModel):
    """One exposed service route in slipp.yaml's expose: block.

    Maps a detected service (the block's key) to the domain and path
    prefix it should be served on. Seeded by `slipp launch` from the
    default frontend/backend routing convention; edit and redeploy to
    change routing.
    """

    domain: str = Field(..., min_length=1, description="FQDN serving this service")
    path: str = Field(default="/", description="Path prefix on the domain")
    host: str | None = Field(
        default=None,
        description="Inventory host name this service deploys to. "
        "None resolves to the project's primary host.",
    )
    internal: bool = Field(
        default=False,
        description="Force wg-manage --internal-tls for this service, "
        "regardless of the project's --public launch flag. No public "
        "domain or DNS record needed -- wg-manage resolves it via its "
        "own internal CA + dnsmasq. --proxy wg-manage only.",
    )

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

    @model_validator(mode="after")
    def _validate_internal_domain(self) -> "ExposeEntry":
        """An internal service's domain is wg-manage's own DNS-safe label.

        Mirrors wg-deploy's validate_name()/LABEL_RE exactly (confirmed
        via wg-deploy/templates/wg-manage.py.j2:122 -- each dot-separated
        label: lowercase letters, digits, hyphens, can't start/end with a
        hyphen) -- catching a bad name here, at generation time, beats an
        opaque wg-manage CLI rejection mid-deploy.
        """
        if self.internal and not all(
            _LABEL_RE.match(label) for label in self.domain.split(".")
        ):
            raise ValueError(
                f"expose domain '{self.domain}' isn't a valid wg-manage "
                "service name (each dot-separated label: lowercase "
                "letters, digits, hyphens only, no leading/trailing "
                "hyphen) -- required when internal: true"
            )
        return self


def resolve_service_host(
    service_name: str, expose: dict[str, "ExposeEntry"] | None, primary_name: str
) -> str:
    """The inventory host name `service_name` deploys to.

    `expose[service_name].host` when explicitly assigned, otherwise
    `primary_name` -- the one fallback rule playbook generation
    (ProvisionConfig.hosts_with_services), wg-manage target resolution
    (WgManageRoleStage), and peer bootstrap (bootstrap_wg_manage_peers)
    all defer to, so it can't drift between them.
    """
    entry = (expose or {}).get(service_name)
    return entry.host if entry and entry.host else primary_name


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
