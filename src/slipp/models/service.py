"""Service data models with Pydantic v2 validation."""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field


class Runtime(StrEnum):
    """Service runtime type.

    Uses StrEnum (Python 3.11+) so str(Runtime.PODMAN) returns "podman".
    """

    SYSTEMD = "systemd"
    DOCKER = "docker"
    PODMAN = "podman"

    def is_container(self) -> bool:
        """Check if this is a container runtime."""
        return self in (Runtime.DOCKER, Runtime.PODMAN)

    @classmethod
    def parse(cls, value: str) -> "Runtime":
        """Parse a CLI flag or hand-edited YAML runtime value, tolerating mixed case."""
        return cls(value.lower())


def _lowercase_runtime(value: object) -> object:
    """Tolerate hand-edited YAML (slipp.yaml, inventory host_vars) with mixed-case runtime values."""
    return Runtime.parse(value) if isinstance(value, str) else value


LenientRuntime = Annotated[Runtime, BeforeValidator(_lowercase_runtime)]
"""A Runtime field that tolerates mixed-case hand-edited YAML input."""


class ServiceState(StrEnum):
    """Service runtime state.

    Uses StrEnum (Python 3.11+) so str(ServiceState.ACTIVE) returns "active".
    """

    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"


class Service(BaseModel):
    """Discovered service on an Ansible host (validated with Pydantic v2).

    Attributes:
        name: Service name (e.g., 'api')
        host: Host IP/hostname (e.g., '83.143.80.248') from ansible_host
        inventory_hostname: Ansible inventory host identifier (e.g., 'production', 'matrix-main')
        unit_name: Systemd unit name (e.g., 'api.service')
        runtime: Service runtime (systemd, docker, podman)
        state: Runtime state (active, inactive, failed)
        projects: List of project names that own this service (can be multiple if host is shared)
        uptime: Optional uptime string
    """

    name: str = Field(..., min_length=1, description="Service name (e.g., 'api')")
    host: str = Field(..., min_length=1, description="Host IP/hostname (ansible_host)")
    inventory_hostname: str = Field(
        ..., min_length=1, description="Ansible inventory host identifier"
    )
    unit_name: str = Field(..., pattern=r"^.+\.service$", description="Systemd unit")
    runtime: Runtime = Field(
        ..., description="Service runtime (systemd, docker, podman)"
    )
    state: ServiceState = Field(..., description="Runtime state")

    projects: list[str] = Field(
        default_factory=list, description="Project names that own this service"
    )

    uptime: str | None = None

    # NOTE: Do NOT set model_config = {"use_enum_values": True} - breaks Runtime.is_container()
