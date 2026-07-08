"""Interactive session manager for SSH and container shells.

Extracts interactive shell logic from ssh.py into a shared service.
Provides methods for starting interactive SSH and container sessions.
"""

import subprocess

from slipp.models.host import AnsibleHost
from slipp.services.ssh.command import CommandBuilder, build_ssh_command


def _run_interactive(cmd: list[str]) -> int:
    """Run an interactive subprocess, returning 130 on Ctrl-C like a shell would."""
    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except KeyboardInterrupt:
        return 130


class InteractiveSessionManager:
    """Manage interactive SSH and container sessions.

    This service handles the complexity of starting interactive shells
    with proper TTY handling using subprocess (not Paramiko).

    Note: This service does not produce output. Callers should display
    connection messages before calling these methods.
    """

    def ssh_session(self, host: AnsibleHost) -> int:
        """Start interactive SSH session.

        Uses subprocess for proper TTY handling.

        Args:
            host: Remote host configuration

        Returns:
            Exit code from SSH session
        """
        cmd = build_ssh_command(host, flags=["-t"])
        return _run_interactive(cmd)

    def ssh_as_user(self, host: AnsibleHost, target_user: str) -> int:
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
            return self.ssh_session(host)

        inner_cmd = "sh -c 'cd ~ && exec /bin/sh'"
        remote_cmd = CommandBuilder.vps_command(
            target_user, inner_cmd, host.ansible_user
        )
        cmd = build_ssh_command(host, flags=["-t"], remote_command=remote_cmd)
        return _run_interactive(cmd)

    def container_shell(
        self,
        host_config: AnsibleHost,
        container_name: str,
        user: str | None = None,
        runtime: str = "docker",
    ) -> int:
        """Interactive shell in container via SSH.

        Uses subprocess for proper TTY handling of nested SSH + container exec.

        Args:
            host_config: SSH host configuration
            container_name: Container name
            user: User inside container (None = container default)
            runtime: Container runtime (podman/docker)

        Returns:
            Exit code from session
        """
        user_flag = f"-u {user}" if user and user != "root" else ""
        exec_cmd = f"{runtime} exec -it {user_flag} {container_name} /bin/sh".strip()

        cmd = build_ssh_command(host_config, flags=["-t"], remote_command=exec_cmd)
        return _run_interactive(cmd)
