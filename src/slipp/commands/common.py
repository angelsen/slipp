"""Shared CLI helpers for commands.

Resolve-or-exit helpers, shared Typer options, and other cross-command
plumbing live here. Business logic (filtering, discovery, lookups) is in
services/discovery/.
"""

from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.constants import SecretEncoding
from slipp.models.deployment import DeploymentHostConfig
from slipp.models.host import AnsibleHost
from slipp.models.service import Runtime, Service
from slipp.output import format_path
from slipp.scanner.workspaces import detect_workspace_members
from slipp.services import wg_manage
from slipp.services.config import (
    HostResolver,
    LocalConfigService,
    RuntimeDetector,
    is_wg_manage_host,
    load_first_host,
)
from slipp.services.deploy import DeployOverrides, DeployResult, run_deploy
from slipp.services.discovery import filter_services, find_service
from slipp.services.discovery.pipeline import discover_and_enrich
from slipp.services.registry import ProjectRegistry
from slipp.services.vault import generate_jwk, generate_secret
from slipp.utils.errors import AmbiguousServiceError, DeployError, WgManageError
from slipp.utils.identifiers import parse_service_identifier
from slipp.utils.matching import get_suggestions

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

ForceOption = Annotated[
    bool,
    typer.Option("--force", "-f", help="Skip confirmation prompt"),
]

ProjectOption = Annotated[
    str | None,
    typer.Option("--project", "-p", help="Project name"),
]

RuntimeOption = Annotated[
    Runtime | None,
    typer.Option("--runtime", help="How the app runs: systemd, docker, podman"),
]

NumBytesOption = Annotated[
    int,
    typer.Option("--bytes", "-b", help="Bytes of entropy (default: 32 = 256-bit)"),
]

EncodingOption = Annotated[
    SecretEncoding,
    typer.Option(
        "--encoding",
        "-e",
        help="Output encoding: hex (default), base64, or ulid",
    ),
]

JwkOption = Annotated[bool, typer.Option("--jwk", help="Generate RSA JWK keypair")]

BitsOption = Annotated[
    int, typer.Option("--bits", help="RSA key size for --jwk (default: 2048)")
]


def validate_num_bytes_encoding(num_bytes: int, encoding: SecretEncoding) -> None:
    """Reject a --bytes override that ULID encoding can't honor.

    ULID is a fixed 128-bit (26-char) identifier -- --bytes has no effect
    on it, so a non-default value would silently produce less entropy than
    the user asked for.

    Raises:
        typer.BadParameter: If --bytes was overridden alongside --encoding ulid
    """
    if encoding == SecretEncoding.ulid and num_bytes != 32:
        raise typer.BadParameter(
            "--bytes has no effect with --encoding ulid (fixed 128-bit/26-char output)"
        )


def _validate_jwk_flags(num_bytes: int, encoding: SecretEncoding) -> None:
    """Reject --bytes/--encoding overrides that --jwk can't honor.

    --jwk generates an RSA keypair, not a random-byte secret -- --bytes and
    --encoding have no effect on it, so a non-default value would silently
    produce output the user didn't ask for.

    Raises:
        typer.BadParameter: If --bytes or --encoding was overridden alongside --jwk
    """
    if num_bytes != 32 or encoding != SecretEncoding.hex:
        raise typer.BadParameter(
            "--bytes/--encoding have no effect with --jwk (use --bits instead)"
        )


def generate_secret_value(
    num_bytes: int,
    encoding: SecretEncoding,
    *,
    jwk: bool = False,
    bits: int = 2048,
) -> str:
    """Validate args and generate a secret or JWK keypair, whichever was asked for."""
    if jwk:
        _validate_jwk_flags(num_bytes, encoding)
        return generate_jwk(bits)
    validate_num_bytes_encoding(num_bytes, encoding)
    return generate_secret(num_bytes, encoding)


def describe_secret(
    secret: str,
    encoding: SecretEncoding,
    num_bytes: int,
    *,
    jwk: bool = False,
    bits: int = 2048,
) -> str:
    """One-line description of a generated secret, for output.hint()."""
    if jwk:
        return f"RSA-{bits} JWK keypair"
    if encoding == SecretEncoding.ulid:
        return "26 char ULID"
    bits_entropy = num_bytes * 8
    return f"{len(secret)} {encoding.value} chars, {bits_entropy}-bit"


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
    local_config = LocalConfigService.load(project_root)
    if not local_config or not local_config.project_dirs:
        return None
    return [project_root / d for d in local_config.project_dirs]


def sync_wg_manage_project(
    project_root: Path,
    project_name: str,
    host: DeploymentHostConfig,
    *,
    dry_run: bool = False,
    quiet: bool = False,
) -> None:
    """Resolve declared dirs + expose config, then converge wg-manage.

    Shared by the post-deploy stray-cleanup hook and `resources sync` --
    both need the same resolve-dirs -> load-config -> wg_manage.sync()
    sequence, just with different quiet/dry_run defaults.
    """
    dirs, _ = resolve_project_dirs(
        resolve_declared_dirs(project_root), root=project_root, quiet=quiet
    )
    local_config = LocalConfigService.load(project_root)
    wg_manage.sync(
        dirs,
        project_name,
        host,
        expose=local_config.expose if local_config else None,
        dry_run=dry_run,
        quiet=quiet,
    )


def sync_wg_manage_after_deploy(project_root: Path, project_name: str) -> None:
    """Best-effort post-deploy wg-manage exposure converge.

    Removes stray wg-manage services this project labeled but no longer
    declares (renamed/removed services since the last deploy), so a live
    exposure never silently outlives the service it pointed at. No-op for
    non-wg-manage projects. Shared by `slipp deploy` and `slipp up` so
    both get the same post-deploy cleanup.

    Never raises: a sync hiccup here shouldn't retroactively turn an
    already-successful deploy into a failed one, it just means one fewer
    thing got tidied up this run -- `slipp resources sync` remains
    available to run by hand. wg_manage.sync() converts every internal
    failure mode (SSH, scanning, missing config) to WgManageError, so
    catching that one type here is actually exhaustive.
    """
    host = load_first_host(project_root)
    if host is None or not is_wg_manage_host(host):
        return

    try:
        sync_wg_manage_project(project_root, project_name, host, quiet=True)
    except WgManageError as e:
        output.warning(f"wg-manage exposure sync failed after deploy: {e}")


def run_deploy_or_exit(
    project_root: Path,
    project_name: str,
    environment: str,
    tags: str | None,
    skip_tags: str | None,
    *,
    overrides: DeployOverrides,
    cli_name: str | None = None,
    requirements: str | None = None,
    dry_run: bool = False,
    force_requirements: bool = False,
    ask_become_pass: bool = False,
) -> DeployResult:
    """Run a deploy, exiting with a formatted error on failure.

    Shared by `slipp deploy` and `slipp up`'s final deploy step so both
    report DeployError and a non-zero playbook exit code identically.

    Raises:
        typer.Exit: On DeployError or a non-zero playbook exit code
    """
    try:
        result = run_deploy(
            project_root,
            project_name,
            environment,
            tags,
            skip_tags,
            overrides=overrides,
            cli_name=cli_name,
            requirements=requirements,
            dry_run=dry_run,
            force_requirements=force_requirements,
            ask_become_pass=ask_become_pass,
        )
    except DeployError as e:
        output.error(str(e))
        if e.log_dir:
            output.hint(f"See log: {format_path(e.log_dir, project_root)}")
        raise typer.Exit(1)

    if result.exit_code != 0:
        output.hint(f"Review log: {format_path(result.log_dir, project_root)}")
        raise typer.Exit(result.exit_code)

    return result


def resolve_host_or_exit(
    service: str | None = None,
    project: str | None = None,
    *,
    command: str,
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
    try:
        return HostResolver().resolve(service=service, project=project)
    except AmbiguousServiceError as e:
        output.error(str(e))
        output.suggestions("Specify target:", e.get_suggestions(command=command))
        raise typer.Exit(1)


def confirm_or_exit(message: str, *, force: bool = False) -> None:
    """Prompt to confirm a destructive action, exiting cleanly if declined.

    Args:
        message: Yes/no question to show (e.g. "Remove service 'foo'?")
        force: Skip the prompt and proceed unconditionally

    Raises:
        typer.Exit: If the user declines
    """
    if not force and not output.confirm(message, default=False):
        output.info("Cancelled")
        raise typer.Exit()


def confirm_or_fail(message: str, *, decline_message: str) -> None:
    """Prompt to confirm a required step, hard-failing (exit 1) if declined.

    Unlike confirm_or_exit, declining here isn't a benign cancellation --
    it aborts a multi-step pipeline that can't proceed without this step.

    Args:
        message: Yes/no question to show
        decline_message: Error shown on decline, explaining what's now blocked

    Raises:
        typer.Exit: If the user declines
    """
    if not output.confirm(message, default=False):
        output.error(decline_message)
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
    project = ProjectRegistry().get(project_name)
    if project:
        return project.project_path
    return LocalConfigService.resolve_root()


def _resolve_runtime(project: str | None) -> Runtime:
    """Resolve project root and detect its runtime.

    Args:
        project: Optional project name (defaults to cwd if not given)

    Returns:
        The detected Runtime

    Raises:
        RuntimeDetectionError: If runtime detection fails
    """
    project_root = (
        _get_project_root(project) if project else LocalConfigService.resolve_root()
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
