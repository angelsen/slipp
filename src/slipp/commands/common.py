"""Shared CLI helpers for commands.

Resolve-or-exit helpers, shared Typer options, and other cross-command
plumbing live here. Business logic (filtering, discovery, lookups) is in
services/discovery/.
"""

from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.models.host import AnsibleHost
from slipp.models.service import Runtime, Service
from slipp.scanner.workspaces import detect_workspace_members
from slipp.services.discovery import filter_services, find_service
from slipp.services.discovery.pipeline import discover_and_enrich
from slipp.utils.errors import AmbiguousServiceError
from slipp.utils.identifiers import parse_service_identifier

DryRunOption = Annotated[
    bool,
    typer.Option("--dry-run", help="Show what would be done without making changes"),
]

ProjectDirsOption = Annotated[
    list[Path] | None,
    typer.Option(
        "--dir",
        "-d",
        help="Directories to scan (default: current directory)",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
]

AskBecomePassOption = Annotated[
    bool,
    typer.Option(
        "--ask-become-pass",
        help="Prompt for the sudo/become password (target host has no passwordless sudo)",
    ),
]


def resolve_project_dirs(
    project_dirs: list[Path] | None,
    root: Path | None = None,
    *,
    quiet: bool = False,
) -> tuple[list[Path], Path]:
    """Resolve scan directories and the output directory.

    If no directories were given, scans `root` and auto-detects npm/yarn
    workspace members. The output directory is `root` when scanning
    multiple directories, or the single directory otherwise.

    Args:
        project_dirs: Explicit --dir values, or None to auto-detect from root
        root: Directory to auto-detect from when project_dirs is None
            (defaults to cwd) -- callers that already resolved a project
            root (e.g. resources.py's sync, which may run from a
            subdirectory) pass it explicitly instead of relying on cwd.
        quiet: Skip the "Detected workspace" info line -- for callers
            running as a background step of something else (e.g. deploy's
            post-deploy wg-manage sync hook) where a normal quiet run
            shouldn't print unrelated scan chatter.

    Returns:
        Tuple of (directories to scan, output directory)
    """
    if project_dirs:
        dirs = project_dirs
    else:
        cwd = root or Path.cwd()
        members = detect_workspace_members(cwd)
        if members:
            if not quiet:
                output.info(f"Detected workspace: {len(members)} member(s)")
            dirs = [cwd, *members]
        else:
            dirs = [cwd]

    output_dir = Path.cwd() if len(dirs) > 1 else dirs[0]
    return dirs, output_dir


def resolve_declared_dirs(project_root: Path) -> list[Path] | None:
    """The --dir values `slipp launch` actually scanned for this project, if recorded.

    slipp.yaml persists launch-time --dir values (LocalConfig.project_dirs)
    precisely so a later re-scan (e.g. wg-manage exposure sync, run at
    every deploy) can reproduce the exact same declared-service set
    instead of re-running auto-detection -- which, for a project launched
    with explicit --dir values, can detect a different set of services
    than what was actually exposed, silently pruning a live, still-wanted
    exposure. Pass the result straight through as resolve_project_dirs()'s
    project_dirs argument.

    Returns:
        Absolute directory paths, or None if slipp.yaml has no recorded
        dirs (project launched before this was tracked) -- callers should
        pass this straight to resolve_project_dirs(), which falls back to
        auto-detection for None exactly as before.
    """
    from slipp.services.config import LocalConfigService

    local_config = LocalConfigService.load(project_root)
    if not local_config or not local_config.project_dirs:
        return None
    return [project_root / d for d in local_config.project_dirs]


def resolve_host_or_exit(
    service: str | None = None,
    project: str | None = None,
    *,
    command: str = "exec",
) -> AnsibleHost:
    """Resolve host (service → project → cwd), exiting with suggestions on ambiguity.

    Args:
        service: Optional service identifier
        project: Optional project name
        command: Command name used in disambiguation suggestions

    Returns:
        Resolved AnsibleHost

    Raises:
        typer.Exit: If resolution is ambiguous
        HostNotFoundError: If no host matches (top-level handler reports it)
    """
    from slipp.services.config import HostResolver

    try:
        return HostResolver().resolve(service=service, project=project)
    except AmbiguousServiceError as e:
        output.error(str(e))
        output.suggestions("Specify target:", e.get_suggestions(command=command))
        raise typer.Exit(1)


def find_service_or_exit(
    ssh_config: AnsibleHost,
    identifier: str,
    *,
    include_system: bool = False,
) -> Service:
    """Find a service on a host, showing available services and exiting if not found.

    Args:
        ssh_config: Host to discover services on
        identifier: Service identifier to look up
        include_system: Include system services (systemd-*, getty@, etc.)

    Returns:
        Matched Service

    Raises:
        typer.Exit: If the service is not found
    """
    services = discover_and_enrich(ssh_config, include_system=include_system)

    filtered = filter_services(services, show_all=include_system)

    service = find_service(filtered, identifier)
    if not service:
        _show_service_not_found_error(
            identifier,
            ssh_config.ansible_host,
            filter_services(services, show_all=True),
        )
        raise typer.Exit(1)

    return service


def _get_project_root(project_name: str) -> Path:
    """Get project root path from registry, falling back to discovery.

    Args:
        project_name: Name of the project to look up

    Returns:
        Project root path from registry, or the enclosing project found by
        walking up from cwd (or cwd itself) if not found
    """
    from slipp.services.config import LocalConfigService
    from slipp.services.registry import ProjectRegistry

    project = ProjectRegistry().get(project_name)
    if project:
        return project.project_path
    return LocalConfigService.resolve_root()


def _resolve_runtime(host: str | None) -> Runtime:
    """Resolve project root and detect its runtime.

    Args:
        host: Optional project name (defaults to cwd if not given)

    Returns:
        The detected Runtime

    Raises:
        RuntimeDetectionError: If runtime detection fails
    """
    from slipp.services.config import LocalConfigService, RuntimeDetector

    project_root = (
        _get_project_root(host) if host else LocalConfigService.resolve_root()
    )
    return RuntimeDetector(project_root).detect()


def require_container_runtime(project: str | None, *, action: str) -> Runtime:
    """Resolve the project's runtime, exiting with an error if it's not a container.

    Args:
        project: Optional project name (defaults to cwd if not given)
        action: Verb phrase for the error message, e.g. "list" or "push to"

    Returns:
        The resolved container Runtime (docker/podman)

    Raises:
        typer.Exit: If the project runtime isn't a container runtime
    """
    runtime = _resolve_runtime(project)
    if not runtime.is_container():
        output.error(
            f"Project runtime is '{runtime}' -- no container images to {action}"
        )
        raise typer.Exit(1)
    return runtime


def _show_service_not_found_error(
    service_identifier: str,
    host: str,
    available_services: list[Service],
) -> None:
    """Display service not found error with available services list.

    Shows an error message, suggests similar services, and lists available
    services to help the user find the correct service name.

    Args:
        service_identifier: Service identifier that was not found
        host: Host where the service was searched
        available_services: List of available services on the host

    Example:
        >>> _show_service_not_found_error("synapze", "83.143.80.248", services)
        # Displays:
        # ✗ Service 'synapze' not found on 83.143.80.248
        # ℹ Did you mean: matrix-synapse?
        # ⚠ Available services:
        #   • matrix-synapse (active)
        #   ...
    """
    from slipp.utils.matching import get_suggestions

    service_name, _, _ = parse_service_identifier(service_identifier)
    output.error(f"Service '{service_name}' not found on {host}")

    service_names = [s.name for s in available_services]
    suggestions = get_suggestions(service_name, service_names)
    if suggestions:
        output.hint(f"Did you mean: {', '.join(suggestions)}?")

    output.warning("Available services:")

    output.list_items([f"{s.name} ({s.state.value})" for s in available_services[:20]])

    if len(available_services) > 20:
        output.info(
            f"... and {len(available_services) - 20} more (use --all to see system services)"
        )
