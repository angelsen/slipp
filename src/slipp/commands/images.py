"""Image listing commands (plural = management)."""

from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.services.config import HostResolver, RuntimeDetectionError, RuntimeDetector
from slipp.services.registry import ProjectRegistry
from slipp.services.ssh import CommandBuilder, SSHService
from slipp.utils.errors import HostNotFoundError

images_app = typer.Typer(name="images", help="Manage container images on VPS")


@images_app.command(name="list")
def list_command(
    host: Annotated[
        str | None, typer.Option("--host", help="Target host/project")
    ] = None,
    filter_pattern: Annotated[
        str | None, typer.Option("--filter", "-f", help="Filter by name pattern")
    ] = None,
) -> None:
    """List container images on VPS."""
    resolver = HostResolver()

    try:
        if host:
            ssh_config = resolver.by_project(host)
            project_root = _get_project_root(host)
        else:
            ssh_config = resolver.current()
            project_root = Path.cwd()
    except HostNotFoundError as e:
        output.error(str(e))
        raise typer.Exit(1)

    try:
        runtime = RuntimeDetector(project_root).detect()
    except RuntimeDetectionError as e:
        output.error(str(e))
        raise typer.Exit(1)

    fmt = "{{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}"
    if filter_pattern:
        base_cmd = (
            f"{runtime} images --filter 'reference={filter_pattern}' --format '{fmt}'"
        )
    else:
        base_cmd = f"{runtime} images --format '{fmt}'"

    cmd = CommandBuilder.vps_command("root", base_cmd, ssh_config.ansible_user)

    with SSHService(ssh_config) as ssh:
        result = ssh.execute(cmd)

    if not result.strip():
        output.info("No images found")
        return

    rows = []
    for line in result.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) >= 3:
            rows.append(
                {
                    "image": parts[0],
                    "size": parts[1],
                    "created": parts[2],
                }
            )

    output.table(rows)


def _get_project_root(project_name: str) -> Path:
    """Get project root path from registry.

    Args:
        project_name: Name of the project to look up.

    Returns:
        Project root path from registry, or current working directory if not found.
    """
    registry = ProjectRegistry()
    project = registry.get(project_name)
    if project:
        return project.project_path
    return Path.cwd()
