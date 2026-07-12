"""Dockerfile generation stage."""

from slipp import output
from slipp.generator import TemplateGenerator
from slipp.models.service import Runtime
from slipp.services.launch.context import DockerfileContext, ScanContext
from slipp.services.launch.stages.common import write_generated_file
from slipp.utils.errors import LaunchError


class DockerfileGenerationStage:
    """Generate Dockerfiles for all services.

    Generates Dockerfile templates for each service in the configuration
    and writes them to disk, respecting customized files marked by the
    slipp generation marker. A no-op when the project's runtime is systemd
    (native process, no container image).

    Attributes:
        generator: TemplateGenerator instance for rendering Dockerfile templates.
    """

    def __init__(self, template_generator: TemplateGenerator):
        self.generator = template_generator

    def execute(self, context: ScanContext) -> None:
        """Generate and write Dockerfiles for all services.

        Iterates through services, generates their Dockerfiles based on
        the first host's runtime, and writes them to disk unless in
        dry-run mode. Skips overwriting customized files.

        Args:
            context: Launch context containing services, inventory config,
                and generation options.
        """
        if context.inventory_config is not None:
            first_host = context.inventory_config.first_host
            runtime = first_host.runtime
        elif isinstance(context, DockerfileContext):
            runtime = Runtime(context.container_runtime)
        else:
            raise LaunchError(
                "No inventory config loaded and no container_runtime available"
            )

        if runtime == Runtime.SYSTEMD:
            output.info("Skipping Dockerfiles (systemd runtime, no container image)")
            return

        output.info("Generating Dockerfiles...")

        for service in context.services:
            try:
                files = self.generator.generate(
                    service=service,
                    output_dir=service.path,
                    container_runtime=runtime.value,
                )

                for file in files:
                    write_generated_file(
                        file.path, file.content, context, respect_customized=True
                    )

            except Exception as e:
                raise LaunchError(f"Failed to generate {service.name}: {e}") from e
