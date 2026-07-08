"""Ansible Galaxy requirements generator for generated deployment projects."""

from slipp.generator.env import render_template
from slipp.models.service import Runtime


def generate_requirements(runtime: Runtime) -> str:
    """Generate requirements.yml content for the given runtime.

    Args:
        runtime: How the app runs (systemd, docker, or podman) -- a
            systemd project needs neither container collection

    Returns:
        Rendered requirements.yml content

    Raises:
        TemplateGenerationError: If template rendering fails

    Example:
        >>> content = generate_requirements(Runtime.DOCKER)
    """
    return render_template(
        "requirements.yml.j2", {"runtime": runtime.value}, label="requirements.yml"
    )
