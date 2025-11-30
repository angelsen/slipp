"""Full launch context for complete Ansible project generation."""

from dataclasses import dataclass, field
from pathlib import Path

from slipp.models.deployment import DetectedService, InventoryConfig, ProvisionConfig

from .base import BaseContext


@dataclass
class FullContext(BaseContext):
    """Context for full pipeline: scan codebase and generate Ansible project.

    Attributes:
        project_dirs: Directories containing project sources to scan.
        reconfigure: If True, regenerate existing configuration files.
        proxy: HTTP reverse proxy type (default: caddy).
        services: Detected container services from project analysis.
        inventory_config: Optional Ansible inventory configuration.
        provision_config: Optional provisioning configuration.
        skip_caddy: If True, exclude Caddy proxy setup.
    """

    project_dirs: list[Path] = field(default_factory=list)
    reconfigure: bool = False
    proxy: str = "caddy"
    services: list[DetectedService] = field(default_factory=list)
    inventory_config: InventoryConfig | None = None
    provision_config: ProvisionConfig | None = None
    skip_caddy: bool = False
