"""Deploy orchestration services: config persistence, presets, and execution."""

from slipp.services.deploy.config import (
    ensure_local_config,
    persist_config_updates,
    register_project,
)
from slipp.services.deploy.preset import resolve_environment_and_tags
from slipp.services.deploy.runner import (
    execute_playbook,
    install_galaxy_requirements,
    validate_deploy_files,
)

__all__ = [
    "ensure_local_config",
    "execute_playbook",
    "install_galaxy_requirements",
    "persist_config_updates",
    "register_project",
    "resolve_environment_and_tags",
    "validate_deploy_files",
]
