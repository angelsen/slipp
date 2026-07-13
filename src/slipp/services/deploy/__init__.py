"""Deploy orchestration services: config persistence, presets, and execution."""

from slipp.services.deploy.config import ensure_local_config
from slipp.services.deploy.preset import resolve_environment_and_tags
from slipp.services.deploy.runner import run_deploy

__all__ = [
    "ensure_local_config",
    "resolve_environment_and_tags",
    "run_deploy",
]
