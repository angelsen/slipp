"""Image listing commands (plural = management)."""

import json
from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import get_project_root, resolve_host_or_exit
from slipp.constants import OutputFormat
from slipp.services.config import RuntimeDetectionError, RuntimeDetector
from slipp.services.ssh import CommandBuilder, SSHService

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
    ssh_config = resolve_host_or_exit(project=host)
    project_root = get_project_root(host) if host else Path.cwd()

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

    if output.get_output_format() == OutputFormat.json:
        output.stdout(json.dumps(rows, indent=2))
        return

    output.table(rows)
