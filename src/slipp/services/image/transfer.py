"""Container image transfer to remote hosts via SSH."""

import subprocess

from slipp.models.host import AnsibleHost
from slipp.services.ssh import CommandBuilder, SSHService
from slipp.utils.errors import ImageTransferError


def detect_local_runtime(image: str) -> str | None:
    """Detect local container runtime and verify image exists.

    Args:
        image: Local image name:tag to check

    Returns:
        "podman" or "docker" if the image exists locally, None otherwise
    """
    check = subprocess.run(
        ["podman", "image", "exists", image],
        capture_output=True,
    )
    if check.returncode == 0:
        return "podman"

    check = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
    )
    if check.returncode == 0:
        return "docker"

    return None


def push_image(
    ssh_config: AnsibleHost,
    image: str,
    local_runtime: str,
    remote_runtime: str,
    rename: str | None = None,
) -> None:
    """Transfer a local container image to a remote host via SSH pipe.

    Args:
        ssh_config: Target host
        image: Local image name:tag
        local_runtime: Local container runtime ("podman" or "docker")
        remote_runtime: Remote container runtime ("podman" or "docker")
        rename: Optional new name for the image on the remote host

    Raises:
        ImageTransferError: If the transfer fails
    """
    target = f"{ssh_config.ansible_user}@{ssh_config.ansible_host}"

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

    _, stderr = load_proc.communicate()
    save_proc.wait()

    if load_proc.returncode != 0:
        message = "Transfer failed"
        if stderr:
            message += f"\n{stderr.decode().strip()}"
        raise ImageTransferError(message)

    if rename and rename != image:
        tag_cmd = CommandBuilder.vps_command(
            "root", f"{remote_runtime} tag {image} {rename}", ssh_config.ansible_user
        )
        with SSHService(ssh_config) as ssh:
            ssh.execute(tag_cmd)
