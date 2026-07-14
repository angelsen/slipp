"""Dockerfile generation stage."""

from pathlib import Path

from slipp.generator import TemplateGenerator
from slipp.models.service import Runtime
from slipp.services.launch.context import ScanContext
from slipp.services.launch.stages.common import FileGenerationStage, resolve_runtime
from slipp.utils.errors import LaunchError


class DockerfileGenerationStage(FileGenerationStage[ScanContext]):
    """Generate Dockerfiles for all services.

    Generates Dockerfile templates for each service in the configuration
    and writes them to disk, respecting customized files marked by the
    slipp generation marker. A no-op when the project's runtime is systemd
    (native process, no container image).

    Attributes:
        generator: TemplateGenerator instance for rendering Dockerfile templates.
    """

    def __init__(self, template_generator: TemplateGenerator):
        super().__init__("Generating Dockerfiles")
        self.generator = template_generator

    def should_skip(self, context: ScanContext) -> str | None:
        """Skip for a systemd runtime (no container image to build).

        Raises:
            LaunchError: If no runtime is resolvable at all (pipeline bug).
        """
        runtime = resolve_runtime(context)
        if runtime is None:
            raise LaunchError(
                "No inventory config loaded and no container_runtime available"
            )

        if runtime == Runtime.SYSTEMD:
            return "Skipping Dockerfiles (systemd runtime, no container image)"
        return None

    def generate_content(self, context: ScanContext) -> dict[Path, str]:
        """Generate Dockerfile content for every service.

        Args:
            context: Launch context containing services and generation options.

        Returns:
            Dictionary mapping each generated Dockerfile path to its content.
        """
        # execute() already validated resolve_runtime(context) is not None
        # before generate_content() can be reached.
        runtime = resolve_runtime(context)
        assert runtime is not None

        content: dict[Path, str] = {}
        for service in context.services:
            content.update(
                self.generator.generate(
                    service=service,
                    output_dir=service.path,
                    container_runtime=runtime,
                )
            )

        return content
