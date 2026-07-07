"""Launch context types for different pipeline modes.

Provides context dataclasses for each slipp launch pipeline:
- BaseContext: Common fields shared by all launch modes
- DockerfileContext: Dockerfile-only generation
- FullContext: Complete Ansible project generation
- ScaffoldContext: Inventory scaffolding for existing projects
"""

from slipp.services.launch.context.base import BaseContext
from slipp.services.launch.context.dockerfile import DockerfileContext
from slipp.services.launch.context.full import FullContext
from slipp.services.launch.context.scaffold import ScaffoldContext

__all__ = ["BaseContext", "DockerfileContext", "FullContext", "ScaffoldContext"]
