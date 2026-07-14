"""Docker Compose generator for local development."""

from slipp.generator.env import render_template
from slipp.models.compose import ComposeConfig


def generate_compose(config: ComposeConfig) -> str:
    """Generate docker-compose.yml content for local development with Docker Desktop.

    Note: For local development only. Production uses Podman systemd.

    Args:
        config: Compose configuration with services

    Returns:
        Rendered docker-compose.yml content

    Raises:
        TemplateGenerationError: If template rendering fails

    Example:
        >>> config = ComposeConfig(services=services, project_name="my-app", project_root=Path.cwd())
        >>> content = generate_compose(config)
        >>> Path("docker-compose.yml").write_text(content)
    """
    return render_template(
        "docker-compose.yml.j2", config.to_dict(), label="docker-compose.yml"
    )
