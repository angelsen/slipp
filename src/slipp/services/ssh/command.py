"""Command builder service for VPS and container execution.

Extracts command building logic from exec.py into a shared service.
Provides static methods for building properly formatted shell commands.
"""


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
            parts.extend(["-u", user])

        parts.append(container)
        parts.append(cmd)

        return " ".join(parts)
