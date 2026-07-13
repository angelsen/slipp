"""Runtime detection for Ansible projects (systemd, docker, or podman)."""

from pathlib import Path

from slipp.models.local_config import LocalConfig
from slipp.models.service import Runtime
from slipp.services.ansible import run_list_tasks
from slipp.services.config.local import LocalConfigService
from slipp.utils.errors import AnsibleError, RuntimeDetectionError


class RuntimeDetector:
    """Detect how a project's app runs from project configuration.

    Checks explicit runtime setting in slipp.yaml, then auto-detects
    from playbook tasks if needed. Auto-detection only recognizes docker/
    podman (it greps rendered task names for those substrings) -- a
    "systemd" project has no equivalent signal to grep for, so it must
    always be set explicitly in slipp.yaml.

    Attributes:
        project_root: Root directory of the Ansible project.
    """

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or LocalConfigService.resolve_root()

    def detect(self) -> Runtime:
        """Detect the project's runtime, error if unclear.

        Resolution order:
        1. Explicit runtime in slipp.yaml
        2. Auto-detect from playbook tasks (docker/podman only)
        3. Error if neither works

        Returns:
            The detected Runtime

        Raises:
            RuntimeDetectionError: If runtime cannot be determined
        """
        config = LocalConfigService.load(self.project_root)
        if config and config.runtime:
            return config.runtime

        detected = self._detect_from_playbook(config)
        if detected:
            return detected

        valid = ", ".join(r.value for r in Runtime)
        raise RuntimeDetectionError(
            "Could not detect runtime.\n"
            "Set in slipp.yaml:\n"
            f"  runtime: docker  # or one of: {valid}"
        )

    def _detect_from_playbook(self, config: LocalConfig | None) -> Runtime | None:
        """Detect docker/podman runtime from ansible-playbook --list-tasks output."""
        if not config or not config.inventory:
            return None

        playbook = self.project_root / config.playbook
        inventory = self.project_root / config.inventory

        if not playbook.exists() or not inventory.exists():
            return None

        try:
            output = run_list_tasks(playbook, inventory, config.roles_path).lower()

            has_docker = "docker" in output
            has_podman = "podman" in output

            if has_docker and not has_podman:
                return Runtime.DOCKER
            if has_podman and not has_docker:
                return Runtime.PODMAN

            return None

        except AnsibleError:
            return None
