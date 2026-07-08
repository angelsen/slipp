"""Ansible inventory generator for deployment targets."""

from slipp.generator.env import render_template
from slipp.models.deployment import InventoryConfig


def generate_inventory(config: InventoryConfig) -> str:
    """Generate inventory.yml content from configuration.

    Args:
        config: Inventory configuration with host details

    Returns:
        Rendered inventory YAML content

    Raises:
        TemplateGenerationError: If template rendering fails

    Example:
        >>> config = InventoryConfig(hosts={"production": HostConfig(...)})
        >>> content = generate_inventory(config)
        >>> Path("inventory.yml").write_text(content)
    """
    return render_template(
        "inventory.yml.j2", {"inventory": config}, label="Ansible inventory"
    )
