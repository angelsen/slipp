"""Image listing commands (plural = management)."""

from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import resolve_host_or_exit, resolve_runtime
from slipp.services.image import list_images
from slipp.utils.errors import ImageTransferError

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
    _, runtime = resolve_runtime(host)

    if not runtime.is_container():
        output.error(f"Project runtime is '{runtime}' -- no container images to list")
        raise typer.Exit(1)

    try:
        rows = list_images(ssh_config, runtime.value, filter_pattern)
    except ImageTransferError as e:
        output.error(str(e))
        raise typer.Exit(1)

    if not rows:
        output.info("No images found")
        return

    output.table(rows)
