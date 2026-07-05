"""Container runtime detection for Ansible projects."""

from pathlib import Path

from slipp.services.ansible import run_list_tasks
from slipp.services.config.local import LocalConfigService
from slipp.utils.errors import AnsibleError


class RuntimeDetector:
    """Detect container runtime from project configuration.

    Checks explicit runtime setting in slipp.yaml, then auto-detects
    from playbook tasks if needed.

    Attributes:
        project_root: Root directory of the Ansible project.
    """

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def detect(self) -> str:
        """Detect container runtime, error if unclear.

        Resolution order:
        1. Explicit runtime in slipp.yaml
        2. Auto-detect from playbook tasks
        3. Error if neither works

        Returns:
            "docker" or "podman"

        Raises:
            RuntimeDetectionError: If runtime cannot be determined
        """
        config = LocalConfigService.load(self.project_root)
        if config and config.runtime:
            runtime = config.runtime.lower()
            if runtime in ("docker", "podman"):
                return runtime
            raise RuntimeDetectionError(
                f"Invalid runtime '{config.runtime}' in slipp.yaml (use: docker, podman)"
            )

        detected = self._detect_from_playbook()
        if detected:
            return detected

        raise RuntimeDetectionError(
            "Could not detect container runtime.\n"
            "Set in slipp.yaml:\n"
            "  runtime: docker  # or podman"
        )

    def _detect_from_playbook(self) -> str | None:
        """Detect runtime from ansible-playbook --list-tasks output.

        Returns:
            "docker" or "podman" if detected unambiguously, None otherwise.
        """
        config = LocalConfigService.load(self.project_root)
        if not config or not config.inventory:
            return None

        playbook = self.project_root / config.playbook
        inventory = self.project_root / config.inventory

        if not playbook.exists() or not inventory.exists():
            return None

        try:
            output = run_list_tasks(playbook, inventory).lower()

            has_docker = "docker" in output
            has_podman = "podman" in output

            if has_docker and not has_podman:
                return "docker"
            if has_podman and not has_docker:
                return "podman"

            return None

        except AnsibleError:
            return None


class RuntimeDetectionError(Exception):
    """Container runtime could not be determined."""

    pass
