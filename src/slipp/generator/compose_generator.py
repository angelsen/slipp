"""Docker Compose generator for local development."""

from jinja2 import TemplateError

from slipp.generator.env import make_env
from slipp.generator.errors import TemplateGenerationError
from slipp.models.deployment import ComposeConfig


class ComposeGenerator:
    """Generate docker-compose.yml for local development with Docker Desktop.

    Uses Jinja2 templates to render multi-service compose files.
    Note: For local development only. Production uses Podman systemd.

    Example:
        >>> config = ComposeConfig(services=services, project_name="my-app", project_root=Path.cwd())
        >>> generator = ComposeGenerator()
        >>> compose_content = generator.generate(config)
    """

    def __init__(self):
        """Initialize ComposeGenerator with Jinja2 environment."""
        self.env = make_env()

    def generate(self, config: ComposeConfig) -> str:
        """Generate docker-compose.yml from template.

        Args:
            config: Compose configuration with services

        Returns:
            Rendered docker-compose.yml content

        Raises:
            TemplateGenerationError: If template rendering fails

        Example:
            >>> config = ComposeConfig(...)
            >>> generator = ComposeGenerator()
            >>> content = generator.generate(config)
            >>> Path("docker-compose.yml").write_text(content)
        """
        try:
            template = self.env.get_template("docker-compose.yml.j2")
            rendered = template.render(**config.to_dict())
            return rendered
        except TemplateError as e:
            raise TemplateGenerationError(
                f"Failed to render docker-compose.yml: {e}"
            ) from e
        except Exception as e:
            raise TemplateGenerationError(
                f"Unexpected error generating compose file: {e}"
            ) from e
