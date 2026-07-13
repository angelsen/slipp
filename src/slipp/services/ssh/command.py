"""Command builder service for VPS and container execution.

Extracts command building logic from exec.py into a shared service.
Provides static methods for building properly formatted shell commands.
"""

import shlex

from slipp.models.host import AnsibleHost


def build_ssh_command(
    host: AnsibleHost,
    *,
    flags: list[str] | None = None,
    remote_command: str | None = None,
) -> list[str]:
    """Build an `ssh` argv list honoring a host's port and key_file.

    Single source of truth for the subprocess-ssh paths (tunnels, interactive
    sessions, image transfer) - unlike SSHService (paramiko), these shell out
    to the `ssh` binary directly and previously built their argv by hand,
    which meant `key_file` was silently ignored outside of SSHService.

    Args:
        host: Target host configuration
        flags: Extra ssh flags/options to insert before the target
            (e.g. ["-t"], or ["-R", "5173:localhost:5173", "-N"])
        remote_command: Optional command to run on the remote host

    Returns:
        Full argv list, ready for subprocess

    Example:
        >>> build_ssh_command(host, flags=["-t"])
        ['ssh', 'root@example.com', '-t']
    """
    cmd = ["ssh"]
    if host.ansible_port != 22:
        cmd += ["-p", str(host.ansible_port)]
    if host.key_file:
        cmd += ["-i", str(host.key_file)]
    cmd += flags or []
    cmd.append(f"{host.ansible_user}@{host.ansible_host}")
    if remote_command:
        cmd.append(remote_command)
    return cmd


class CommandBuilder:
    """Build commands for VPS and container execution.

    This class provides static methods to build properly formatted
    commands for different execution contexts.
    """

    @staticmethod
    def vps_command(target_user: str, cmd: str, current_user: str) -> str:
        """Build command to execute on VPS.

        Handles sudo escalation when target user differs from current user.

        Args:
            target_user: User to run command as
            cmd: Command to execute
            current_user: Current SSH user

        Returns:
            Full command string (with sudo if needed)

        Examples:
            >>> CommandBuilder.vps_command("root", "ls", "deploy")
            'sudo ls'
            >>> CommandBuilder.vps_command("postgres", "psql", "deploy")
            'sudo -u postgres psql'
            >>> CommandBuilder.vps_command("deploy", "ls", "deploy")
            'ls'
        """
        if target_user == current_user:
            return cmd

        if target_user == "root":
            return f"sudo {cmd}"

        return f"sudo -u {target_user} {cmd}"

    @staticmethod
    def container_command(
        container: str,
        cmd: str,
        user: str | None = None,
        runtime: str = "docker",
        interactive: bool = False,
    ) -> str:
        """Build container exec command.

        Args:
            container: Container name
            cmd: Command to execute inside container
            user: User inside container (None = container default, usually root)
            runtime: Container runtime (podman/docker)
            interactive: If True, add -it flags for interactive use

        Returns:
            Full container exec command string

        Examples:
            >>> CommandBuilder.container_command("nginx", "cat /etc/nginx/nginx.conf", runtime="docker")
            'docker exec nginx cat /etc/nginx/nginx.conf'
            >>> CommandBuilder.container_command("db", "psql", user="postgres", runtime="podman")
            'podman exec -u postgres db psql'
            >>> CommandBuilder.container_command("app", "/bin/sh", interactive=True)
            'docker exec -it app /bin/sh'
        """
        parts = [runtime, "exec"]

        if interactive:
            parts.append("-it")

        if user and user != "root":
            parts.extend(["-u", shlex.quote(user)])

        # cmd stays raw on purpose: `slipp exec` commands are the user's own
        # shell input and should be interpreted remotely, same as an ssh
        # prompt. Only the identifiers around it get quoted.
        parts.append(shlex.quote(container))
        parts.append(cmd)

        return " ".join(parts)
