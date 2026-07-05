"""Image management commands (singular = action)."""

import subprocess
from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import get_project_root, resolve_host_or_exit
from slipp.services.config import RuntimeDetectionError, RuntimeDetector
from slipp.services.ssh import CommandBuilder, SSHService

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
    project_root = get_project_root(host) if host else Path.cwd()

    local_runtime = _detect_local_runtime(image)
    if not local_runtime:
        output.error(f"Image '{image}' not found locally")
        output.hint("Build with: podman build -t <name> .")
        raise typer.Exit(1)

    try:
        remote_runtime = RuntimeDetector(project_root).detect()
    except RuntimeDetectionError as e:
        output.error(str(e))
        raise typer.Exit(1)

    target_name = name or image
    target = f"{ssh_config.ansible_user}@{ssh_config.ansible_host}"

    output.info(f"Pushing {image} → {target}")
    output.hint(f"Local: {local_runtime}, Remote: {remote_runtime}")
    if name:
        output.hint(f"Renaming to: {target_name}")

    with output.spinner("Transferring image"):
        save_proc = subprocess.Popen(
            [local_runtime, "save", image],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        load_cmd = CommandBuilder.vps_command(
            "root", f"{remote_runtime} load", ssh_config.ansible_user
        )
        ssh_cmd = [
            "ssh",
            "-p",
            str(ssh_config.ansible_port),
            target,
            load_cmd,
        ]

        load_proc = subprocess.Popen(
            ssh_cmd,
            stdin=save_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Allow save_proc to receive SIGPIPE if load_proc exits
        if save_proc.stdout:
            save_proc.stdout.close()

        stdout, stderr = load_proc.communicate()
        save_proc.wait()

        if load_proc.returncode != 0:
            output.error("Transfer failed")
            if stderr:
                output.hint(stderr.decode().strip())
            raise typer.Exit(1)

    if name and name != image:
        output.info(f"Renaming to {name}")
        tag_cmd = CommandBuilder.vps_command(
            "root", f"{remote_runtime} tag {image} {name}", ssh_config.ansible_user
        )
        with SSHService(ssh_config) as ssh:
            ssh.execute(tag_cmd)

    output.success(f"Image pushed: {target_name}")


def _detect_local_runtime(image: str) -> str | None:
    """Detect local container runtime and verify image exists."""
    # Try podman first
    check = subprocess.run(
        ["podman", "image", "exists", image],
        capture_output=True,
    )
    if check.returncode == 0:
        return "podman"

    # Try docker
    check = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
    )
    if check.returncode == 0:
        return "docker"

    return None
