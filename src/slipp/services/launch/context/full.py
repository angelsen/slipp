"""Full launch context for complete Ansible project generation."""

from dataclasses import dataclass

from slipp.constants import DEFAULT_ENV
from slipp.models.deployment import ProvisionConfig
from slipp.services.launch.context.scan import ScanContext


@dataclass
class FullContext(ScanContext):
    """Context for full pipeline: scan codebase and generate Ansible project.

    Attributes:
        environment: Target environment name (e.g., 'dev', 'prod'). Only the
            full pipeline's inventory/registry stages read this.
        reconfigure: If True, regenerate existing configuration files.
        provision_config: Optional provisioning configuration.
    """

    environment: str = DEFAULT_ENV
    reconfigure: bool = False
    provision_config: ProvisionConfig | None = None
