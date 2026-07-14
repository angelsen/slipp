"""Scaffold context for creating inventory for existing Ansible projects.

This module defines the context object used during the scaffold pipeline,
which initializes inventory structures for Ansible projects that need to
be integrated with slipp.
"""

from dataclasses import dataclass
from pathlib import Path

from slipp.services.launch.context.base import BaseContext


@dataclass
class ScaffoldContext(BaseContext):
    """Context for scaffold pipeline: create inventory for existing project.

    Attributes:
        playbook_path: Path to the main Ansible playbook file.
        inventory_path: Path to the inventory file or directory.
        requirements_path: Path to requirements.yml for role dependencies.
        galaxy_roles_path: Path to the external Ansible Galaxy roles
            directory (--roles-path). Unrelated to registration.py's
            roles_path, which tracks slipp's own generated role
            directories for managed_roles scanning -- this project has
            none of those, since it's a pre-existing Ansible project.
        hostname: Target host name for the deployment.
        host_ip: IP address of the target host.
        inventory_dir: Path to the inventory directory being scaffolded.
        host_group: Ansible inventory group name, detected from the
            existing playbook by ScaffoldValidationStage.
    """

    playbook_path: Path | None = None
    inventory_path: Path | None = None
    requirements_path: Path | None = None
    galaxy_roles_path: str | None = None
    hostname: str = ""
    host_ip: str = ""
    inventory_dir: Path | None = None
    host_group: str = "servers"
