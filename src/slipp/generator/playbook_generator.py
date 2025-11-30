"""Ansible playbook generator for Podman deployments."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateError

from slipp.generator.errors import TemplateGenerationError
from slipp.models.deployment import ProvisionConfig


class PlaybookGenerator:
    """Generate Ansible playbooks for Podman systemd deployments.

    Uses Jinja2 templates to render playbook.yml with role-based structure
    for provision and deploy phases.

    Example:
        >>> config = ProvisionConfig(services=services, inventory=inventory_config, ...)
        >>> generator = PlaybookGenerator()
        >>> playbook_content = generator.generate(config)
    """

    def __init__(self):
        """Initialize PlaybookGenerator with Jinja2 environment."""
        # Find templates directory relative to this module
        template_dir = Path(__file__).parent / "templates"

        # Setup Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

        # Add custom filter for path relativization
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

    def generate(self, config: ProvisionConfig) -> str:
        """Generate Ansible playbook from template.

        Args:
            config: Provision configuration with services, inventory, and Caddy config

        Returns:
            Rendered playbook YAML content

        Raises:
            TemplateGenerationError: If template rendering fails

        Example:
            >>> config = ProvisionConfig(...)
            >>> generator = PlaybookGenerator()
            >>> content = generator.generate(config)
            >>> Path("playbook.yml").write_text(content)
        """
        try:
            template = self.env.get_template("playbook.yml.j2")
            rendered = template.render(**config.to_dict())
            return rendered
        except TemplateError as e:
            raise TemplateGenerationError(
                f"Failed to render Ansible playbook: {e}"
            ) from e
        except Exception as e:
            raise TemplateGenerationError(
                f"Unexpected error generating playbook: {e}"
            ) from e
