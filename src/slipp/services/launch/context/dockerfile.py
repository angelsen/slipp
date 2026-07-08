"""Context for Dockerfile-only generation pipeline.

This module provides context management for generating only Dockerfile
artifacts without full deployment configuration.
"""

from dataclasses import dataclass

from slipp.models.service import Runtime
from slipp.services.launch.context.scan import ScanContext


@dataclass
class DockerfileContext(ScanContext):
    """Configuration for Dockerfile generation without deployment.

    Attributes:
        container_runtime: Container runtime to target when inventory_config
            isn't available (this pipeline never loads one). Dockerfile
            generation is inherently container-only (docker/podman) --
            unlike DeploymentHostConfig.runtime, this is not widened to
            include "systemd".
    """

    container_runtime: str = Runtime.DOCKER.value
