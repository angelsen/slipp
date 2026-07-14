"""Deploy orchestration services: config persistence, presets, and execution."""

from slipp.services.deploy.config import DeployOverrides, ensure_local_config
from slipp.services.deploy.preset import resolve_environment_and_tags
from slipp.services.deploy.runner import DeployResult, run_deploy

__all__ = [
    "DeployOverrides",
    "DeployResult",
    "ensure_local_config",
    "resolve_environment_and_tags",
    "run_deploy",
]
