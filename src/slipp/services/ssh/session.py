"""Interactive session manager for SSH and container shells.

Extracts interactive shell logic from ssh.py into a shared service.
Provides methods for starting interactive SSH and container sessions.
"""

import subprocess
import sys

from slipp.models.host import AnsibleHost


class InteractiveSessionManager:
    """Manage interactive SSH and container sessions.

    This service handles the complexity of starting interactive shells
    with proper TTY handling using subprocess (not Paramiko).

    Note: This service does not produce output. Callers should display
    connection messages before calling these methods.
    """

    def ssh_session(self, host: str, user: str, port: int = 22) -> int:
        """Start interactive SSH session.

        Uses subprocess for proper TTY handling.

        Args:
            host: Remote host
            user: SSH user
            port: SSH port

        Returns:
            Exit code from SSH session
        """
        cmd = ["ssh", "-t", f"{user}@{host}", "-p", str(port)]

        try:
            result = subprocess.run(cmd, check=False)
            return result.returncode
        except KeyboardInterrupt:
            return 130

    def ssh_as_user(
        self,
        host: str,
        ssh_user: str,
        target_user: str,
        port: int = 22,
    ) -> int:
        """SSH then sudo to target user.

        If target_user == ssh_user, just SSH directly.
        Otherwise, SSH then sudo to target user with /bin/sh.

        Args:
            host: Remote host
            ssh_user: User to SSH as
            target_user: User to switch to after SSH
            port: SSH port

        Returns:
            Exit code from session
        """
        if target_user == ssh_user:
            return self.ssh_session(host, ssh_user, port)

        cmd = [
            "ssh",
            "-t",
            f"{ssh_user}@{host}",
            "-p",
            str(port),
            f"sudo -u {target_user} sh -c 'cd ~ && exec /bin/sh'",
        ]

        try:
            result = subprocess.run(cmd, check=False)
            return result.returncode
        except KeyboardInterrupt:
            return 130

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

        ssh_cmd = [
            "ssh",
            "-t",
            f"{host_config.ansible_user}@{host_config.ansible_host}",
            "-p",
            str(host_config.ansible_port or 22),
            exec_cmd,
        ]

        try:
            result = subprocess.run(ssh_cmd, check=False)
            return result.returncode
        except KeyboardInterrupt:
            return 130

    def exit_with_code(self, code: int) -> None:
        """Exit the process with the given code.

        Separated for testing purposes.

        Args:
            code: Exit code to use
        """
        sys.exit(code)
