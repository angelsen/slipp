"""Ansible playbook generator for Podman deployments."""

from jinja2 import TemplateError

from slipp.generator.env import make_env
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
        self.env = make_env()

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
