"""Ansible inventory generator for deployment targets."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateError

from slipp.generator.errors import TemplateGenerationError
from slipp.models.deployment import InventoryConfig


class InventoryGenerator:
    """Generate Ansible inventory.yml from configuration.

    Uses Jinja2 template to render standard Ansible inventory format
    with production host configuration.

    Example:
        >>> config = InventoryConfig(hosts={"production": HostConfig(...)})
        >>> generator = InventoryGenerator()
        >>> inventory_content = generator.generate(config)
    """

    def __init__(self):
        """Initialize InventoryGenerator with Jinja2 environment."""
        # Find templates directory relative to this module
        template_dir = Path(__file__).parent / "templates"

        # Setup Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def generate(self, config: InventoryConfig) -> str:
        """Generate inventory.yml content from configuration.

        Args:
            config: Inventory configuration with host details

        Returns:
            Rendered inventory YAML content

        Raises:
            TemplateGenerationError: If template rendering fails

        Example:
            >>> config = InventoryConfig(...)
            >>> generator = InventoryGenerator()
            >>> content = generator.generate(config)
            >>> Path("inventory.yml").write_text(content)
        """
        try:
            template = self.env.get_template("inventory.yml.j2")
            rendered = template.render(inventory=config)
            return rendered
        except TemplateError as e:
            raise TemplateGenerationError(
                f"Failed to render Ansible inventory: {e}"
            ) from e
        except Exception as e:
            raise TemplateGenerationError(
                f"Unexpected error generating inventory: {e}"
            ) from e
