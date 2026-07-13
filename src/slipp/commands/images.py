"""Image listing commands (plural = management)."""

from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import (
    ProjectOption,
    require_container_runtime,
    resolve_host_or_exit,
)
from slipp.services.image import list_images

images_app = typer.Typer(name="images", help="Manage container images on VPS")


@images_app.command(name="list")
def list_command(
    project: ProjectOption = None,
    filter_pattern: Annotated[
        str | None, typer.Option("--filter", "-f", help="Filter by name pattern")
    ] = None,
) -> None:
    """List container images on VPS."""
    ssh_config = resolve_host_or_exit(project=project, command="images list")
    runtime = require_container_runtime(project, action="list")

    rows = list_images(ssh_config, runtime.value, filter_pattern)

    output.empty_or_table(rows, "No images found")
