"""Container image transfer to remote hosts via SSH."""

import subprocess

from slipp.models.host import AnsibleHost
from slipp.services.ssh import CommandBuilder, SSHService, build_ssh_command
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


def list_images(
    ssh_config: AnsibleHost,
    remote_runtime: str,
    filter_pattern: str | None = None,
) -> list[dict[str, str]]:
    """List container images on a remote host.

    Args:
        ssh_config: Target host
        remote_runtime: Remote container runtime ("podman" or "docker")
        filter_pattern: Optional name pattern to filter by

    Returns:
        List of dicts with image, size, and created keys

    Raises:
        ImageTransferError: If the remote command fails
    """
    fmt = "{{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}"
    if filter_pattern:
        base_cmd = (
            f"{remote_runtime} images --filter 'reference={filter_pattern}' "
            f"--format '{fmt}'"
        )
    else:
        base_cmd = f"{remote_runtime} images --format '{fmt}'"

    cmd = CommandBuilder.vps_command("root", base_cmd, ssh_config.ansible_user)

    with SSHService(ssh_config) as ssh:
        result = ssh.execute(cmd)

    if not result.ok:
        raise ImageTransferError(f"Failed to list images: {result.stderr.strip()}")

    if not result.stdout.strip():
        return []

    rows = []
    for line in result.stdout.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) >= 3:
            rows.append({"image": parts[0], "size": parts[1], "created": parts[2]})

    return rows


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
    save_proc = subprocess.Popen(
        [local_runtime, "save", image],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    load_cmd = CommandBuilder.vps_command(
        "root", f"{remote_runtime} load", ssh_config.ansible_user
    )
    ssh_cmd = build_ssh_command(ssh_config, remote_command=load_cmd)

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
    save_stderr = save_proc.stderr.read() if save_proc.stderr else b""

    if save_proc.returncode != 0:
        message = f"Failed to save local image '{image}'"
        if save_stderr:
            message += f"\n{save_stderr.decode().strip()}"
        raise ImageTransferError(message)

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
            tag_result = ssh.execute(tag_cmd)
            if not tag_result.ok:
                raise ImageTransferError(
                    f"Failed to tag image as {rename}\n{tag_result.text.strip()}"
                )
