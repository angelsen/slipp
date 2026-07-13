"""Full launch context for complete Ansible project generation."""

from dataclasses import dataclass

from slipp.constants import DEFAULT_ENV
from slipp.models.deployment import ProvisionConfig
from slipp.models.local_config import ExposeEntry
from slipp.services.launch.context.scan import ScanContext


@dataclass
class FullContext(ScanContext):
    """Context for full pipeline: scan codebase and generate Ansible project.

    Attributes:
        environment: Target environment name (e.g., 'dev', 'prod'). Only the
            full pipeline's inventory/registry stages read this.
        reconfigure: If True, regenerate existing configuration files.
        provision_config: Optional provisioning configuration.
        python_extra: uv sync --extra group name (Python systemd deploys).
        exec_args: Extra ExecStart arguments (Python systemd deploys).
        health_check: HTTP path polled after restart; rolls back to the
            previous deployment on failure (systemd deploys only).
        public: Expose via Let's Encrypt instead of internal CA
            (--proxy wg-manage only).
        expose: Resolved service routing (existing slipp.yaml block, or
            the seeded default) -- set lazily by resolve_expose(), then
            persisted by RegistrationStage.
    """

    environment: str = DEFAULT_ENV
    reconfigure: bool = False
    provision_config: ProvisionConfig | None = None
    expose: dict[str, ExposeEntry] | None = None
    python_extra: str | None = None
    exec_args: str | None = None
    health_check: str | None = None
    public: bool = False
