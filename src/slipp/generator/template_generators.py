"""Single-template Ansible/Compose file generators for `slipp launch`.

Each function renders one Jinja2 template into a single file's content.
See `caddy_generator.generate_caddy_role` for the multi-file case.

Raises:
    TemplateGenerationError: If template rendering fails, for any function below.
"""

from slipp.generator.env import render_template
from slipp.models.compose import ComposeConfig
from slipp.models.deployment import InventoryConfig, ProvisionConfig
from slipp.models.service import Runtime


def generate_playbook(config: ProvisionConfig) -> str:
    """Generate Ansible playbook.yml content for docker/podman/systemd deployments."""
    return render_template(
        "playbook.yml.j2", config.to_dict(), label="Ansible playbook"
    )


def generate_requirements(runtime: Runtime) -> str:
    """Generate requirements.yml content for the given runtime.

    A systemd project needs neither container collection.
    """
    return render_template(
        "requirements.yml.j2", {"runtime": runtime.value}, label="requirements.yml"
    )


def generate_group_vars(config: ProvisionConfig) -> str:
    """Generate group_vars/all.yml content for the given provision config."""
    return render_template(
        "group_vars/all.yml.j2", config.to_dict(), label="group_vars/all.yml"
    )


def generate_inventory(config: InventoryConfig) -> str:
    """Generate inventory.yml content from configuration."""
    return render_template(
        "inventory.yml.j2", {"inventory": config}, label="Ansible inventory"
    )


def generate_compose(config: ComposeConfig) -> str:
    """Generate docker-compose.yml content for local development with Docker Desktop.

    Note: For local development only. Production uses Podman systemd.
    """
    return render_template(
        "docker-compose.yml.j2", config.to_dict(), label="docker-compose.yml"
    )
