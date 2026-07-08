"""Shared scan+generate context for the full and dockerfile-only pipelines."""

from dataclasses import dataclass, field
from pathlib import Path

from slipp.models.deployment import DetectedService, InventoryConfig
from slipp.services.launch.context.base import BaseContext


@dataclass
class ScanContext(BaseContext):
    """Fields shared by the full and dockerfile-only pipelines.

    Both pipelines scan project directories for services, then generate
    artifacts from what was detected -- this holds the scan/detect state
    common to both, ahead of where they diverge (full generates a complete
    Ansible project; dockerfile-only stops after Dockerfiles).

    Attributes:
        project_dirs: Directories containing project sources to scan.
        proxy: HTTP reverse proxy type (default: caddy).
        services: Detected container services from project analysis.
        inventory_config: Optional Ansible inventory configuration. When set,
            its first host's runtime takes precedence over a subclass's own
            runtime field (e.g. DockerfileContext.container_runtime).
        skip_caddy: If True, exclude Caddy proxy setup.
    """

    project_dirs: list[Path] = field(default_factory=list)
    proxy: str = "caddy"
    services: list[DetectedService] = field(default_factory=list)
    inventory_config: InventoryConfig | None = None
    skip_caddy: bool = False
