"""Image management commands (singular = action)."""

from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import resolve_host_or_exit, resolve_runtime
from slipp.services.image import detect_local_runtime, push_image
from slipp.utils.errors import ImageTransferError

image_app = typer.Typer(name="image", help="Container image operations")


@image_app.command(name="push")
def push_command(
    image: Annotated[str, typer.Argument(help="Local image name:tag")],
    host: Annotated[
        str | None, typer.Option("--host", help="Target host/project")
    ] = None,
    name: Annotated[
        str | None, typer.Option("--name", "-n", help="Rename image on VPS")
    ] = None,
) -> None:
    """Push local container image to VPS via SSH."""
    ssh_config = resolve_host_or_exit(project=host)

    local_runtime = detect_local_runtime(image)
    if not local_runtime:
        output.error(f"Image '{image}' not found locally")
        output.hint("Build with: podman build -t <name> .")
        raise typer.Exit(1)

    _, remote_runtime = resolve_runtime(host)

    if not remote_runtime.is_container():
        output.error(
            f"Project runtime is '{remote_runtime}' -- no container images to push to"
        )
        raise typer.Exit(1)

    target_name = name or image
    target = f"{ssh_config.ansible_user}@{ssh_config.ansible_host}"

    output.info(f"Pushing {image} → {target}")
    output.hint(f"Local: {local_runtime}, Remote: {remote_runtime}")
    if name:
        output.hint(f"Renaming to: {target_name}")

    try:
        with output.spinner("Transferring image"):
            push_image(ssh_config, image, local_runtime, remote_runtime, rename=name)
    except ImageTransferError as e:
        output.error(str(e))
        raise typer.Exit(1)

    output.success(f"Image pushed: {target_name}")
