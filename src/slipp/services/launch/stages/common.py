"""Common stages and base classes for launch workflow.

Provides reusable base classes for implementing launch pipeline stages,
including file generation with dry-run support and configuration validation.
"""

from pathlib import Path
from typing import Any

from slipp import output
from slipp.constants import VALID_PROXIES
from slipp.models.service import Runtime
from slipp.utils.errors import LaunchError


class FileGenerationStage:
    """Base class for stages that generate files."""

    def __init__(self, description: str):
        self.description = description

    def generate_content(self, context: Any) -> dict[Path, str]:
        """Generate file content for this stage.

        Args:
            context: Stage execution context containing configuration.

        Returns:
            Dictionary mapping file paths to their content strings.

        Raises:
            NotImplementedError: Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement generate_content()")

    def execute(self, context: Any) -> None:
        """Execute file generation stage.

        Generates files from context, creates parent directories,
        and logs output. Supports dry-run mode for preview.

        Args:
            context: Stage execution context with output_dir, dry_run flags.
        """
        output.info(f"{self.description}...")

        try:
            files = self.generate_content(context)

            for file_path, content in files.items():
                display_path = (
                    str(file_path.relative_to(context.output_dir))
                    if hasattr(context, "output_dir")
                    else str(file_path)
                )

                if context.dry_run:
                    output.hint(f"  Would create: {display_path}")
                else:
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    is_new_file = not file_path.exists()
                    file_path.write_text(content)
                    icon = output.ICON_CHECK if is_new_file else output.ICON_REFRESH
                    output.list_items([display_path], bullet=icon)
                    context.generated_files.append(file_path)

        except Exception as e:
            raise LaunchError(f"Failed to {self.description.lower()}: {e}") from e


class ValidationStage:
    """Validate proxy choice, runtime, and set skip_caddy flag."""

    def execute(self, context: Any) -> None:
        """Validate proxy and runtime configuration.

        Checks that proxy choice is in VALID_PROXIES list and sets
        skip_caddy flag to True when proxy is "none". Also validates
        context.container_runtime when the context carries that field
        (only DockerfileContext does - contexts with a loaded inventory
        get their runtime from there instead).

        Args:
            context: Stage execution context with proxy setting.

        Raises:
            LaunchError: If proxy or runtime choice is invalid.
        """
        if context.proxy not in VALID_PROXIES:
            raise LaunchError(
                f"Invalid proxy: {context.proxy}\n"
                f"Valid options: {', '.join(VALID_PROXIES)}"
            )

        context.skip_caddy = context.proxy == "none"

        # Only DockerfileContext carries this field, and it's inherently
        # container-only (no Dockerfile to generate for a systemd deploy) --
        # so this deliberately doesn't accept the full Runtime enum.
        container_runtime = getattr(context, "container_runtime", None)
        valid_runtimes = [Runtime.DOCKER.value, Runtime.PODMAN.value]
        if container_runtime is not None and container_runtime not in valid_runtimes:
            raise LaunchError(
                f"Invalid container runtime: {container_runtime}\n"
                f"Valid options: {', '.join(valid_runtimes)}"
            )
