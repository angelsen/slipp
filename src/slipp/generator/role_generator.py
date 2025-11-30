"""Ansible role generator for service deployments."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateError

from slipp.generator.errors import TemplateGenerationError
from slipp.models.deployment import DetectedService


class RoleGenerator:
    """Generate Ansible roles for detected services.

    Creates role directory structure:
    - roles/{service-name}/tasks/main.yml
    - roles/{service-name}/templates/systemd.service.j2
    - roles/{service-name}/handlers/main.yml

    Example:
        >>> service = DetectedService(name="backend", ...)
        >>> generator = RoleGenerator()
        >>> files = generator.generate_app_role(service, "my-app")
    """

    def __init__(self):
        """Initialize RoleGenerator with Jinja2 environment."""
        # Find templates directory relative to this module
        template_dir = Path(__file__).parent / "templates"

        # Setup Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def generate_app_role(
        self,
        service: DetectedService,
        project_name: str,
        container_runtime: str = "docker",
    ) -> dict[Path, str]:
        """Generate role files for a service.

        Args:
            service: Detected service configuration
            project_name: Project name for resource naming
            container_runtime: Container runtime (docker or podman)

        Returns:
            Dict mapping file paths to content

        Raises:
            TemplateGenerationError: If template rendering fails

        Example:
            >>> service = DetectedService(name="backend", framework="flask", ...)
            >>> generator = RoleGenerator()
            >>> files = generator.generate_app_role(service, "my-app", "podman")
            >>> # files contains 3 entries:
            >>> # - roles/app-backend/tasks/main.yml
            >>> # - roles/app-backend/templates/systemd.service.j2
            >>> # - roles/app-backend/handlers/main.yml
        """
        role_name = f"app-{service.name}"
        files = {}

        try:
            # Generate role files
            files[Path(f"roles/{role_name}/tasks/main.yml")] = self._render_tasks(
                service, project_name, container_runtime
            )
            files[Path(f"roles/{role_name}/templates/systemd.service.j2")] = (
                self._render_systemd(service, project_name, container_runtime)
            )
            files[Path(f"roles/{role_name}/handlers/main.yml")] = self._render_handlers(
                service, project_name
            )

            return files
        except TemplateError as e:
            raise TemplateGenerationError(
                f"Failed to render role for {service.name}: {e}"
            ) from e
        except Exception as e:
            raise TemplateGenerationError(
                f"Unexpected error generating role for {service.name}: {e}"
            ) from e

    def _render_tasks(
        self, service: DetectedService, project_name: str, container_runtime: str
    ) -> str:
        """Render tasks/main.yml template.

        Args:
            service: Service configuration
            project_name: Project name
            container_runtime: Container runtime (docker or podman)

        Returns:
            Rendered tasks YAML content
        """
        template = self.env.get_template("roles/app/tasks/main.yml.j2")
        return template.render(
            service=service.model_dump(),
            project_name=project_name,
            container_runtime=container_runtime,
        )

    def _render_systemd(
        self, service: DetectedService, project_name: str, container_runtime: str
    ) -> str:
        """Render systemd.service.j2 template.

        Args:
            service: Service configuration
            project_name: Project name
            container_runtime: Container runtime (docker or podman)

        Returns:
            Rendered systemd unit content
        """
        template = self.env.get_template("roles/app/templates/systemd.service.j2")
        return template.render(
            service=service.model_dump(),
            project_name=project_name,
            container_runtime=container_runtime,
        )

    def _render_handlers(self, service: DetectedService, project_name: str) -> str:
        """Render handlers/main.yml template.

        Args:
            service: Service configuration
            project_name: Project name

        Returns:
            Rendered handlers YAML content
        """
        template = self.env.get_template("roles/app/handlers/main.yml.j2")
        return template.render(
            service=service.model_dump(),
            project_name=project_name,
        )
