"""Ansible role generator for service deployments."""

from pathlib import Path

from jinja2 import TemplateError

from slipp.generator.env import make_env
from slipp.generator.errors import TemplateGenerationError
from slipp.models.deployment import DetectedService
from slipp.models.service import Runtime


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
        self.env = make_env()

    def _template_dir(self, runtime: Runtime) -> str:
        """Pick the source template set for a runtime.

        The build step and systemd unit are structurally different for a
        native systemd deploy (npm build, no image) vs docker/podman (image
        build) -- a separate template set, not conditionals inside one
        template, keeps each shape readable.
        """
        return "roles/app-systemd" if runtime == Runtime.SYSTEMD else "roles/app-container"

    def generate_app_role(
        self,
        service: DetectedService,
        project_name: str,
        runtime: Runtime = Runtime.DOCKER,
    ) -> dict[Path, str]:
        """Generate role files for a service.

        Args:
            service: Detected service configuration
            project_name: Project name for resource naming
            runtime: How the app runs (systemd, docker, or podman)

        Returns:
            Dict mapping file paths to content

        Raises:
            TemplateGenerationError: If template rendering fails

        Example:
            >>> service = DetectedService(name="backend", framework="flask", ...)
            >>> generator = RoleGenerator()
            >>> files = generator.generate_app_role(service, "my-app", Runtime.PODMAN)
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
                service, project_name, runtime
            )
            files[Path(f"roles/{role_name}/templates/systemd.service.j2")] = (
                self._render_systemd(service, project_name, runtime)
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
        self, service: DetectedService, project_name: str, runtime: Runtime
    ) -> str:
        """Render tasks/main.yml template.

        Args:
            service: Service configuration
            project_name: Project name
            runtime: How the app runs (systemd, docker, or podman)

        Returns:
            Rendered tasks YAML content
        """
        template = self.env.get_template(
            f"{self._template_dir(runtime)}/tasks/main.yml.j2"
        )
        return template.render(
            service=service.model_dump(),
            project_name=project_name,
            runtime=runtime.value,
        )

    def _render_systemd(
        self, service: DetectedService, project_name: str, runtime: Runtime
    ) -> str:
        """Render systemd.service.j2 template.

        Args:
            service: Service configuration
            project_name: Project name
            runtime: How the app runs (systemd, docker, or podman)

        Returns:
            Rendered systemd unit content
        """
        template = self.env.get_template(
            f"{self._template_dir(runtime)}/templates/systemd.service.j2"
        )
        return template.render(
            service=service.model_dump(),
            project_name=project_name,
            runtime=runtime.value,
        )

    def _render_handlers(self, service: DetectedService, project_name: str) -> str:
        """Render handlers/main.yml template.

        Args:
            service: Service configuration
            project_name: Project name

        Returns:
            Rendered handlers YAML content
        """
        template = self.env.get_template("roles/app-container/handlers/main.yml.j2")
        return template.render(
            service=service.model_dump(),
            project_name=project_name,
        )
