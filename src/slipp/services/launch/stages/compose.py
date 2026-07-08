"""Docker Compose generation stage."""

from pathlib import Path

from slipp.generator.compose_generator import generate_compose
from slipp.models.deployment import ComposeConfig
from slipp.models.service import Runtime
from slipp.services.launch.context import FullContext
from slipp.services.launch.stages.common import FileGenerationStage


class ComposeGenerationStage(FileGenerationStage[FullContext]):
    """Generate docker-compose.yml file.

    A no-op when the project's runtime is systemd (native process, no
    containers to compose).
    """

    def __init__(self):
        super().__init__("Generating docker-compose.yml")

    def generate_content(self, context: FullContext) -> dict[Path, str]:
        """Generate docker-compose.yml content from deployment context.

        Args:
            context: Deployment context containing services, project name,
                and output directory.

        Returns:
            Dictionary mapping docker-compose.yml path to generated YAML
            content, or empty if the runtime is systemd.
        """
        if context.inventory_config is not None:
            first_host = context.inventory_config.first_host
            if first_host.runtime == Runtime.SYSTEMD:
                return {}

        compose_config = ComposeConfig(
            services=context.services,
            project_name=context.project_name,
            project_root=context.output_dir,
        )
        compose_content = generate_compose(compose_config)
        compose_path = context.output_dir / "docker-compose.yml"

        return {compose_path: compose_content}
