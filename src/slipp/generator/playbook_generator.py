"""Ansible playbook generator for docker/podman/systemd deployments."""

from slipp.generator.env import render_template
from slipp.models.deployment import ProvisionConfig


def generate_playbook(config: ProvisionConfig) -> str:
    """Generate Ansible playbook.yml content for docker/podman/systemd deployments.

    Args:
        config: Provision configuration with services, inventory, and Caddy config

    Returns:
        Rendered playbook YAML content

    Raises:
        TemplateGenerationError: If template rendering fails

    Example:
        >>> config = ProvisionConfig(services=services, inventory=inventory_config, ...)
        >>> content = generate_playbook(config)
        >>> Path("playbook.yml").write_text(content)
    """
    return render_template(
        "playbook.yml.j2", config.to_dict(), label="Ansible playbook"
    )
