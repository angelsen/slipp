"""Context for Dockerfile-only generation pipeline.

This module provides context management for generating only Dockerfile
artifacts without full deployment configuration.
"""

from dataclasses import dataclass, field
from pathlib import Path

from slipp.models.deployment import DetectedService, InventoryConfig

from .base import BaseContext


@dataclass
class DockerfileContext(BaseContext):
    """Configuration for Dockerfile generation without deployment.

    Holds project structure, service detection, and proxy configuration
    for generating Dockerfiles in isolation.

    Attributes:
        project_dirs: Directories containing project sources.
        proxy: HTTP reverse proxy type (default: caddy).
        services: Detected container services from project analysis.
        inventory_config: Optional Ansible inventory configuration.
        skip_caddy: If True, exclude Caddy proxy setup.
    """

    project_dirs: list[Path] = field(default_factory=list)
    proxy: str = "caddy"
    services: list[DetectedService] = field(default_factory=list)
    inventory_config: InventoryConfig | None = None
    skip_caddy: bool = False
