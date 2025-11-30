"""Project registry services.

This package provides services for managing the global project registry.
"""

from slipp.services.registry.io import RegistryIO
from slipp.services.registry.projects import ProjectRegistry

__all__ = [
    "ProjectRegistry",
    "RegistryIO",
]
