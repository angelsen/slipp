"""Docker Compose generation stage."""

from pathlib import Path

from slipp.generator.template_generators import generate_compose
from slipp.models.compose import ComposeConfig
from slipp.services.launch.context import FullContext
from slipp.services.launch.stages.common import FileGenerationStage, is_systemd_runtime


class ComposeGenerationStage(FileGenerationStage[FullContext]):
    """Generate docker-compose.yml file.

    A no-op when the project's runtime is systemd (native process, no
    containers to compose).
    """

    def __init__(self):
        super().__init__("Generating docker-compose.yml")

    def should_skip(self, context: FullContext) -> str | None:
        """Skip for a systemd runtime (no containers to compose)."""
        if is_systemd_runtime(context):
            return "Skipping docker-compose.yml (systemd runtime, no containers)"
        return None

    def generate_content(self, context: FullContext) -> dict[Path, str]:
        """Generate docker-compose.yml content from deployment context.

        Args:
            context: Deployment context containing services, project name,
                and output directory.

        Returns:
            Dictionary mapping docker-compose.yml path to generated YAML
            content.
        """
        compose_config = ComposeConfig(
            services=context.services,
            project_name=context.project_name,
            project_root=context.output_dir,
            host_ports=context.host_ports,
        )
        compose_content = generate_compose(compose_config)
        compose_path = context.output_dir / "docker-compose.yml"

        return {compose_path: compose_content}
