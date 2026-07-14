"""Container image transfer to remote hosts via SSH."""

import shlex
import subprocess
import threading

from slipp.models.host import AnsibleHost
from slipp.services.ssh import SSHService, build_ssh_command, build_vps_command
from slipp.utils.errors import ImageTransferError, SSHCommandError


def detect_local_runtime(image: str) -> str | None:
    """Detect local container runtime and verify image exists.

    Args:
        image: Local image name:tag to check

    Returns:
        "podman" or "docker" if the image exists locally, None otherwise
    """
    for runtime, args in (
        ("podman", ["podman", "image", "exists", image]),
        ("docker", ["docker", "image", "inspect", image]),
    ):
        try:
            check = subprocess.run(args, capture_output=True)
        except FileNotFoundError:
            continue
        if check.returncode == 0:
            return runtime

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
            f"{remote_runtime} images "
            f"--filter {shlex.quote(f'reference={filter_pattern}')} "
            f"--format '{fmt}'"
        )
    else:
        base_cmd = f"{remote_runtime} images --format '{fmt}'"

    cmd = build_vps_command("root", base_cmd, ssh_config.ansible_user)

    with SSHService(ssh_config) as ssh:
        ssh.ensure_sudo("Listing container images")
        result = ssh.execute(cmd)

    try:
        result.check("Failed to list images")
    except SSHCommandError as e:
        raise ImageTransferError(str(e)) from e

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
    # Primed here (rather than relying on the raw ssh subprocess below) because
    # that subprocess's stdin carries the piped image tar, leaving no channel
    # to answer a sudo password prompt -- only NOPASSWD hosts can complete the
    # load. Priming first turns a missing-NOPASSWD host into a clear upfront
    # error instead of a confusing failure partway through the transfer.
    with SSHService(ssh_config) as ssh:
        ssh.ensure_sudo("Transferring container image")

    save_proc = subprocess.Popen(
        [local_runtime, "save", image],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    load_cmd = build_vps_command(
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

    # save_proc's stderr must be drained concurrently with load_proc.communicate():
    # if save_proc writes more than a pipe buffer's worth of stderr, it blocks
    # on that pipe (unread until after communicate() returns below), which stops
    # it feeding load_proc's stdin, which stalls communicate() forever.
    save_stderr_chunks: list[bytes] = []

    def _drain_save_stderr() -> None:
        if save_proc.stderr:
            save_stderr_chunks.append(save_proc.stderr.read())

    stderr_reader = threading.Thread(target=_drain_save_stderr, daemon=True)
    stderr_reader.start()

    try:
        _, stderr = load_proc.communicate()
        save_proc.wait()
    finally:
        for proc in (save_proc, load_proc):
            if proc.poll() is None:
                proc.terminate()
                proc.wait()

    stderr_reader.join()
    save_stderr = save_stderr_chunks[0] if save_stderr_chunks else b""

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
        tag_cmd = build_vps_command(
            "root", f"{remote_runtime} tag {image} {rename}", ssh_config.ansible_user
        )
        with SSHService(ssh_config) as ssh:
            ssh.ensure_sudo("Tagging transferred image")
            try:
                ssh.execute(tag_cmd).check(f"Failed to tag image as {rename}")
            except SSHCommandError as e:
                raise ImageTransferError(str(e)) from e
