"""Ansible Galaxy requirements generator for generated deployment projects."""

from jinja2 import TemplateError

from slipp.generator.env import make_env
from slipp.generator.errors import TemplateGenerationError
from slipp.models.service import Runtime


class RequirementsGenerator:
    """Generate requirements.yml listing the Galaxy collections a generated project needs.

    Example:
        >>> generator = RequirementsGenerator()
        >>> content = generator.generate(Runtime.DOCKER)
    """

    def __init__(self):
        """Initialize RequirementsGenerator with Jinja2 environment."""
        self.env = make_env()

    def generate(self, runtime: Runtime) -> str:
        """Generate requirements.yml content for the given runtime.

        Args:
            runtime: How the app runs (systemd, docker, or podman) -- a
                systemd project needs neither container collection

        Returns:
            Rendered requirements.yml content

        Raises:
            TemplateGenerationError: If template rendering fails
        """
        try:
            template = self.env.get_template("requirements.yml.j2")
            return template.render(runtime=runtime.value)
        except TemplateError as e:
            raise TemplateGenerationError(
                f"Failed to render requirements.yml: {e}"
            ) from e
        except Exception as e:
            raise TemplateGenerationError(
                f"Unexpected error generating requirements.yml: {e}"
            ) from e
