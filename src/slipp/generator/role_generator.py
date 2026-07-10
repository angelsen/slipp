"""Ansible role generator for service deployments."""

from pathlib import Path

from slipp.generator.env import render_template
from slipp.generator.extractors import extract_template_variables
from slipp.models.deployment import DetectedService
from slipp.models.service import Runtime
from slipp.scanner.models import PYTHON_FRAMEWORKS

# Top-level paths slipp itself generates into the project root. When a
# service's own source directory *is* (or contains) the project root -- the
# common "monorepo root is also an app" shape -- these must be excluded from
# that service's rsync, or slipp's own generated Ansible project gets synced
# to the deploy target as if it were app source.
_SLIPP_GENERATED_PATTERNS = [
    "playbook.yml",
    "inventory*.yml",
    "group_vars",
    "roles",
    "slipp.yaml",
    "requirements.yml",
    "docker-compose.yml",
    ".slipp",
]


class RoleGenerator:
    """Generate Ansible roles for detected services.

    Creates role directory structure:
    - roles/{service-name}/tasks/main.yml
    - roles/{service-name}/templates/systemd.service.j2
    - roles/{service-name}/handlers/main.yml (container runtimes only --
      systemd deploys restart/verify inline via block/rescue)

    Example:
        >>> service = DetectedService(name="backend", ...)
        >>> generator = RoleGenerator()
        >>> files = generator.generate_app_role(service, "my-app")
    """

    def _template_dir(self, runtime: Runtime, service: DetectedService) -> str:
        """Pick the source template set for a runtime + language.

        The build step and systemd unit are structurally different for a
        native systemd deploy (npm/uv build, no image) vs docker/podman
        (image build), and for a systemd deploy, again between Node (npm
        build + node ExecStart) and Python (uv sync + venv-binary
        ExecStart) -- separate template sets, not conditionals inside one
        template, keep each shape readable.
        """
        if runtime != Runtime.SYSTEMD:
            return "roles/app-container"
        if service.framework in PYTHON_FRAMEWORKS:
            return "roles/app-systemd-python"
        return "roles/app-systemd"

    def _compute_sync_excludes(
        self,
        service: DetectedService,
        all_services: list[DetectedService],
        project_root: Path,
    ) -> list[str]:
        """Compute rsync --exclude patterns for other services/slipp's own files.

        Two sources of overlap, both only possible when another path is
        nested inside this service's own source directory (siblings never
        overlap, so they're left alone):
        - Other detected services nested inside this one (the "monorepo
          root is also an app" shape, e.g. bulletins-admin living in a
          subdirectory of bulletins-chat's own repo root).
        - slipp's own generated project files, when this service's path is
          (or contains) the project root.

        Args:
            service: The service to compute excludes for
            all_services: Every detected service in this launch
            project_root: The generated project's root directory

        Returns:
            Relative exclude patterns (rsync-pattern syntax, e.g. "admin" or
            "inventory*.yml")
        """
        excludes: list[str] = []

        for other in all_services:
            # Path equality, not object identity: a caller may pass a
            # model_copy() of `service` (e.g. with an overridden port) that
            # is a distinct object but still the same service on disk.
            if other.path == service.path:
                continue
            try:
                rel = other.path.relative_to(service.path)
            except ValueError:
                continue
            excludes.append(str(rel))

        try:
            rel_root = project_root.relative_to(service.path)
        except ValueError:
            pass
        else:
            prefix = "" if str(rel_root) == "." else f"{rel_root}/"
            excludes.extend(
                f"{prefix}{pattern}" for pattern in _SLIPP_GENERATED_PATTERNS
            )

        return excludes

    def generate_app_role(
        self,
        service: DetectedService,
        project_name: str,
        runtime: Runtime = Runtime.DOCKER,
        all_services: list[DetectedService] | None = None,
        project_root: Path | None = None,
        uv_extra: str | None = None,
        exec_args: str | None = None,
        health_check: str | None = None,
    ) -> dict[Path, str]:
        """Generate role files for a service.

        Args:
            service: Detected service configuration
            project_name: Project name for resource naming
            runtime: How the app runs (systemd, docker, or podman)
            all_services: Every detected service in this launch (defaults to
                just this one) -- used to exclude sibling services nested
                inside this one's source directory from its sync
            project_root: The generated project's root directory (defaults
                to service.path) -- used to exclude slipp's own generated
                files when this service's path is/contains the root
            uv_extra: Optional `uv sync --extra <name>` group (Python
                systemd deploys only)
            exec_args: Optional extra arguments appended to ExecStart
                (Python systemd deploys only)
            health_check: Optional HTTP path (e.g. "/health") polled after
                restart; on failure the previous deployment is restored
                (systemd deploys only). Also enables crash-loop detection
                (no rollback) when unset.

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
        sync_excludes = self._compute_sync_excludes(
            service,
            all_services if all_services is not None else [service],
            project_root if project_root is not None else service.path,
        )

        files[Path(f"roles/{role_name}/tasks/main.yml")] = self._render_tasks(
            service, project_name, runtime, sync_excludes, uv_extra, health_check
        )
        files[Path(f"roles/{role_name}/templates/systemd.service.j2")] = (
            self._render_systemd(service, project_name, runtime, exec_args)
        )
        # Systemd deploys handle restart/verification inline (see tasks/main.yml.j2's
        # block/rescue) rather than via notify, so only the container role -- whose
        # community.docker/podman tasks still notify a recreate handler -- needs one.
        if runtime != Runtime.SYSTEMD:
            files[Path(f"roles/{role_name}/handlers/main.yml")] = (
                self._render_handlers(service, project_name)
            )

        return files

    def _render_tasks(
        self,
        service: DetectedService,
        project_name: str,
        runtime: Runtime,
        sync_excludes: list[str],
        uv_extra: str | None = None,
        health_check: str | None = None,
    ) -> str:
        """Render tasks/main.yml template.

        Args:
            service: Service configuration
            project_name: Project name
            runtime: How the app runs (systemd, docker, or podman)
            sync_excludes: Extra rsync --exclude patterns (see
                _compute_sync_excludes)
            uv_extra: Optional `uv sync --extra <name>` group (Python
                systemd deploys only)
            health_check: Optional HTTP path polled after restart, with
                rollback on failure (systemd deploys only)

        Returns:
            Rendered tasks YAML content
        """
        template_dir = self._template_dir(runtime, service)
        context = {
            "service": service.model_dump(),
            "project_name": project_name,
            "health_check": health_check,
            "runtime": runtime.value,
            "sync_excludes": sync_excludes,
            "uv_extra": uv_extra,
        }
        if template_dir == "roles/app-systemd-python":
            context.update(extract_template_variables(service))
        return render_template(
            f"{template_dir}/tasks/main.yml.j2",
            context,
            label=f"role for {service.name} (tasks)",
        )

    def _render_systemd(
        self,
        service: DetectedService,
        project_name: str,
        runtime: Runtime,
        exec_args: str | None = None,
    ) -> str:
        """Render systemd.service.j2 template.

        Args:
            service: Service configuration
            project_name: Project name
            runtime: How the app runs (systemd, docker, or podman)
            exec_args: Optional extra ExecStart arguments (Python systemd
                deploys only)

        Returns:
            Rendered systemd unit content
        """
        template_dir = self._template_dir(runtime, service)
        context = {
            "service": service.model_dump(),
            "project_name": project_name,
            "runtime": runtime.value,
            "exec_args": exec_args,
        }
        if template_dir == "roles/app-systemd-python":
            context.update(extract_template_variables(service))
        return render_template(
            f"{template_dir}/templates/systemd.service.j2",
            context,
            label=f"role for {service.name} (systemd unit)",
        )

    def _render_handlers(self, service: DetectedService, project_name: str) -> str:
        """Render handlers/main.yml template.

        Args:
            service: Service configuration
            project_name: Project name

        Returns:
            Rendered handlers YAML content
        """
        return render_template(
            "roles/app-container/handlers/main.yml.j2",
            {"service": service.model_dump(), "project_name": project_name},
            label=f"role for {service.name} (handlers)",
        )
