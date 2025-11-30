"""Scaffold context for creating inventory for existing Ansible projects.

This module defines the context object used during the scaffold pipeline,
which initializes inventory structures for Ansible projects that need to
be integrated with slipp.
"""

from dataclasses import dataclass
from pathlib import Path

from .base import BaseContext


@dataclass
class ScaffoldContext(BaseContext):
    """Context for scaffold pipeline: create inventory for existing project.

    Attributes:
        playbook_path: Path to the main Ansible playbook file.
        inventory_path: Path to the inventory file or directory.
        requirements_path: Path to requirements.yml for role dependencies.
        roles_path: Path to the roles directory.
        hostname: Target host name for the deployment.
        host_ip: IP address of the target host.
        inventory_dir: Path to the inventory directory being scaffolded.
    """

    playbook_path: Path | None = None
    inventory_path: Path | None = None
    requirements_path: Path | None = None
    roles_path: str | None = None
    hostname: str = ""
    host_ip: str = ""
    inventory_dir: Path | None = None
