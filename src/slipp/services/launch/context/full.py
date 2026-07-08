"""Full launch context for complete Ansible project generation."""

from dataclasses import dataclass

from slipp.models.deployment import ProvisionConfig
from slipp.services.launch.context.scan import ScanContext


@dataclass
class FullContext(ScanContext):
    """Context for full pipeline: scan codebase and generate Ansible project.

    Attributes:
        reconfigure: If True, regenerate existing configuration files.
        provision_config: Optional provisioning configuration.
    """

    reconfigure: bool = False
    provision_config: ProvisionConfig | None = None
