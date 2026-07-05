"""Service data models with Pydantic v2 validation."""

from enum import StrEnum

from pydantic import BaseModel, Field


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


class ServiceState(StrEnum):
    """Service runtime state.

    Uses StrEnum (Python 3.11+) so str(ServiceState.ACTIVE) returns "active".
    """

    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"
    UNKNOWN = "unknown"


class Service(BaseModel):
    """Discovered service on an Ansible host (validated with Pydantic v2).

    Attributes:
        name: Service name (e.g., 'api')
        host: Host IP/hostname (e.g., '83.143.80.248') from ansible_host
        inventory_hostname: Ansible inventory host identifier (e.g., 'production', 'matrix-main')
        unit_name: Systemd unit name (e.g., 'api.service')
        runtime: Service runtime (systemd, docker, podman)
        state: Runtime state (active, inactive, failed, unknown)
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
    state: ServiceState = Field(
        default=ServiceState.UNKNOWN, description="Runtime state"
    )

    projects: list[str] = Field(
        default_factory=list, description="Project names that own this service"
    )

    uptime: str | None = None

    def __str__(self) -> str:
        """String representation of service."""
        return f"{self.name}@{self.host} ({self.runtime}) - {self.state}"

    # NOTE: Do NOT use use_enum_values=True - breaks Runtime.is_container()
    model_config = {}
