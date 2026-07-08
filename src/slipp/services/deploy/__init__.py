"""Deploy orchestration services: config persistence, presets, and execution."""

from slipp.services.deploy.config import (
    ensure_local_config,
    ensure_project_registered,
    persist_config_updates,
)
from slipp.services.deploy.preset import resolve_environment_and_tags
from slipp.services.deploy.runner import (
    execute_playbook,
    install_galaxy_requirements,
    validate_deploy_files,
)

__all__ = [
    "ensure_local_config",
    "ensure_project_registered",
    "execute_playbook",
    "install_galaxy_requirements",
    "persist_config_updates",
    "resolve_environment_and_tags",
    "validate_deploy_files",
]
