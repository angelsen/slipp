"""Interactive SSH and container shell sessions.

Starts interactive shells with proper TTY handling using subprocess (not
Paramiko). These functions do not produce output -- callers should display
connection messages before calling them.

Unlike services/ssh/tunnel.py's background tunnels, these inherit the
caller's TTY and a human is present, so an unknown-host-key or password
prompt from the `ssh` binary itself is expected, normal behavior rather
than a silent hang -- no BatchMode here on purpose.
"""

import subprocess

from slipp.models.host import AnsibleHost
from slipp.services.ssh.command import (
    build_container_command,
    build_ssh_command,
    build_vps_command,
)


def _run_interactive(cmd: list[str]) -> int:
    """Run an interactive subprocess, returning 130 on Ctrl-C like a shell would."""
    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except KeyboardInterrupt:
        return 130


def ssh_session(host: AnsibleHost) -> int:
    """Start interactive SSH session.

    Args:
        host: Remote host configuration

    Returns:
        Exit code from SSH session
    """
    cmd = build_ssh_command(host, flags=["-t"])
    return _run_interactive(cmd)


def ssh_as_user(host: AnsibleHost, target_user: str) -> int:
    """SSH then sudo to target user.

    If target_user == host.ansible_user, just SSH directly.
    Otherwise, SSH then sudo to target user with /bin/sh.

    Args:
        host: Remote host configuration (connects as host.ansible_user)
        target_user: User to switch to after SSH

    Returns:
        Exit code from session
    """
    if target_user == host.ansible_user:
        return ssh_session(host)

    inner_cmd = "sh -c 'cd ~ && exec /bin/sh'"
    remote_cmd = build_vps_command(target_user, inner_cmd, host.ansible_user)
    cmd = build_ssh_command(host, flags=["-t"], remote_command=remote_cmd)
    return _run_interactive(cmd)


def container_shell(
    host_config: AnsibleHost,
    container_name: str,
    user: str | None = None,
    runtime: str = "docker",
) -> int:
    """Interactive shell in container via SSH.

    Args:
        host_config: SSH host configuration
        container_name: Container name
        user: User inside container (None = container default)
        runtime: Container runtime (podman/docker)

    Returns:
        Exit code from session
    """
    exec_cmd = build_container_command(
        container_name, "/bin/sh", user=user, runtime=runtime, interactive=True
    )

    cmd = build_ssh_command(host_config, flags=["-t"], remote_command=exec_cmd)
    return _run_interactive(cmd)
