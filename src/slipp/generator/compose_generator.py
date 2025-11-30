"""Docker Compose generator for local development."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateError

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
        # Find templates directory relative to this module
        template_dir = Path(__file__).parent / "templates"

        # Setup Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

        # Add custom filter for path relativization (shared with PlaybookGenerator)
        self.env.filters["relative_to"] = self._relative_to

    def _relative_to(self, path: str, base: str) -> str:
        """Jinja2 filter to make path relative to base.

        Args:
            path: Absolute path to make relative
            base: Base path to relativize against

        Returns:
            Relative path string
        """
        try:
            path_obj = Path(path)
            base_obj = Path(base)
            return str(path_obj.relative_to(base_obj))
        except (ValueError, TypeError):
            # If not relative or invalid, return original
            return path

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
