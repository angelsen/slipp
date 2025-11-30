"""Launch context types for different pipeline modes.

Provides context dataclasses for each slipp launch pipeline:
- BaseContext: Common fields shared by all launch modes
- DockerfileContext: Dockerfile-only generation
- FullContext: Complete Ansible project generation
- ScaffoldContext: Inventory scaffolding for existing projects
"""

from .base import BaseContext
from .dockerfile import DockerfileContext
from .full import FullContext
from .scaffold import ScaffoldContext

__all__ = ["BaseContext", "DockerfileContext", "FullContext", "ScaffoldContext"]
