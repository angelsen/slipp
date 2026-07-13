"""Image management commands (singular = action)."""

from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import require_container_runtime, resolve_host_or_exit
from slipp.services.image import detect_local_runtime, push_image

image_app = typer.Typer(name="image", help="Container image operations")


@image_app.command(name="push")
def push_command(
    image: Annotated[str, typer.Argument(help="Local image name:tag")],
    project: Annotated[
        str | None, typer.Option("--project", "-p", help="Project name")
    ] = None,
    name: Annotated[
        str | None, typer.Option("--name", "-n", help="Rename image on VPS")
    ] = None,
) -> None:
    """Push local container image to VPS via SSH."""
    ssh_config = resolve_host_or_exit(project=project)

    local_runtime = detect_local_runtime(image)
    if not local_runtime:
        output.error(f"Image '{image}' not found locally")
        output.hint("Build with: podman build -t <name> .")
        raise typer.Exit(1)

    remote_runtime = require_container_runtime(project, action="push to")

    target_name = name or image
    target = f"{ssh_config.ansible_user}@{ssh_config.ansible_host}"

    output.info(f"Pushing {image} → {target}")
    output.hint(f"Local: {local_runtime}, Remote: {remote_runtime}")
    if name:
        output.hint(f"Renaming to: {target_name}")

    with output.spinner("Transferring image"):
        push_image(ssh_config, image, local_runtime, remote_runtime, rename=name)

    output.success(f"Image pushed: {target_name}")
