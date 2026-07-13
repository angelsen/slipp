"""Ansible role generator for service deployments."""

from pathlib import Path
from typing import Any

from slipp.constants import PLAYBOOK_FILENAME
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
    PLAYBOOK_FILENAME,
    "inventory*.yml",
    "group_vars",
    "roles",
    "slipp.yaml",
    "requirements.yml",
    "docker-compose.yml",
    ".slipp",
]

_SYSTEMD_TEMPLATE_DIRS = {"roles/app-systemd-python", "roles/app-systemd"}


def _template_dir(runtime: Runtime, service: DetectedService) -> str:
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
        excludes.extend(f"{prefix}{pattern}" for pattern in _SLIPP_GENERATED_PATTERNS)

    return excludes


def generate_app_role(
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

    Creates role directory structure:
    - roles/{service-name}/tasks/main.yml
    - roles/{service-name}/templates/systemd.service.j2
    - roles/{service-name}/handlers/main.yml (container runtimes only --
      systemd deploys restart/verify inline via block/rescue)

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
        >>> files = generate_app_role(service, "my-app", Runtime.PODMAN)
        >>> # files contains 3 entries:
        >>> # - roles/app-backend/tasks/main.yml
        >>> # - roles/app-backend/templates/systemd.service.j2
        >>> # - roles/app-backend/handlers/main.yml
    """
    role_name = f"app-{service.name}"
    files = {}
    sync_excludes = _compute_sync_excludes(
        service,
        all_services if all_services is not None else [service],
        project_root if project_root is not None else service.path,
    )
    template_dir = _template_dir(runtime, service)
    systemd_vars = _extract_systemd_vars(template_dir, service)

    files[Path(f"roles/{role_name}/tasks/main.yml")] = _render_tasks(
        service,
        project_name,
        runtime,
        sync_excludes,
        uv_extra,
        health_check,
        template_dir,
        systemd_vars,
    )
    files[Path(f"roles/{role_name}/templates/systemd.service.j2")] = _render_systemd(
        service, project_name, runtime, exec_args, template_dir, systemd_vars
    )
    # Systemd deploys handle restart/verification inline (see tasks/main.yml.j2's
    # block/rescue) rather than via notify, so only the container role -- whose
    # community.docker/podman tasks still notify a recreate handler -- needs one.
    if runtime != Runtime.SYSTEMD:
        files[Path(f"roles/{role_name}/handlers/main.yml")] = _render_handlers(
            service, project_name
        )

    return files


def _render_tasks(
    service: DetectedService,
    project_name: str,
    runtime: Runtime,
    sync_excludes: list[str],
    uv_extra: str | None,
    health_check: str | None,
    template_dir: str,
    systemd_vars: dict[str, Any] | None,
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
        template_dir: Source template set, from _template_dir()
        systemd_vars: Systemd-only template vars, from
            _extract_systemd_vars() (None for non-systemd runtimes)

    Returns:
        Rendered tasks YAML content
    """
    context = {
        "service": service.model_dump(),
        "project_name": project_name,
        "health_check": health_check,
        "runtime": runtime.value,
        "sync_excludes": sync_excludes,
        "uv_extra": uv_extra,
    }
    if systemd_vars:
        context.update(systemd_vars)
    return render_template(
        f"{template_dir}/tasks/main.yml.j2",
        context,
        label=f"role for {service.name} (tasks)",
    )


def _render_systemd(
    service: DetectedService,
    project_name: str,
    runtime: Runtime,
    exec_args: str | None,
    template_dir: str,
    systemd_vars: dict[str, Any] | None,
) -> str:
    """Render systemd.service.j2 template.

    Args:
        service: Service configuration
        project_name: Project name
        runtime: How the app runs (systemd, docker, or podman)
        exec_args: Optional extra ExecStart arguments (Python systemd
            deploys only)
        template_dir: Source template set, from _template_dir()
        systemd_vars: Systemd-only template vars, from
            _extract_systemd_vars() (None for non-systemd runtimes)

    Returns:
        Rendered systemd unit content
    """
    context = {
        "service": service.model_dump(),
        "project_name": project_name,
        "runtime": runtime.value,
        "exec_args": exec_args,
    }
    if systemd_vars:
        context.update(systemd_vars)
    return render_template(
        f"{template_dir}/templates/systemd.service.j2",
        context,
        label=f"role for {service.name} (systemd unit)",
    )


def _extract_systemd_vars(
    template_dir: str, service: DetectedService
) -> dict[str, Any] | None:
    """Compute systemd-only template vars (exec entrypoint, deps), once per role.

    extract_template_variables() also sets a "runtime" key (a
    Dockerfile-label display string, e.g. "SvelteKit") for the
    Fly-launch templates it's normally paired with -- unrelated to
    (and must not clobber) the deploy-mechanism "runtime" the tasks/
    systemd render contexts already carry (systemd/docker/podman).

    Returns:
        Vars to merge into the render context, or None for non-systemd
        template dirs (tasks/systemd renders are then unaffected).
    """
    if template_dir not in _SYSTEMD_TEMPLATE_DIRS:
        return None
    extra = extract_template_variables(service)
    extra.pop("runtime", None)
    return extra


def _render_handlers(service: DetectedService, project_name: str) -> str:
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
