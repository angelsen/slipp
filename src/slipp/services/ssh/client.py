"""SSH service with Paramiko wrapper and best practices."""

from collections.abc import Generator

import paramiko

from slipp.models.host import AnsibleHost
from slipp.utils.errors import SSHAuthenticationError, SSHConnectionError


class SSHService:
    """SSH client with connection pooling and best practices.

    This class provides a secure SSH client wrapper with:
    - Context manager for automatic cleanup
    - System host key verification (RejectPolicy)
    - Authentication hierarchy (key file → agent → discoverable keys)
    - Streaming support for log tailing
    - IPv4/IPv6 automatic fallback

    Example:
        >>> host_config = AnsibleHost(ansible_host='example.com', ansible_user='root')
        >>> with SSHService(host_config) as ssh:
        ...     output = ssh.execute('ls -la')
        ...     print(output)
    """

    def __init__(self, host_config: AnsibleHost):
        """Initialize SSH service with host configuration.

        Args:
            host_config: Host configuration with SSH details
        """
        self.config = host_config
        self.client: paramiko.SSHClient | None = None

    def __enter__(self):
        """Context manager entry - establish connection.

        Returns:
            SSHService instance

        Raises:
            SSHConnectionError: Connection failed
            SSHAuthenticationError: Authentication failed
        """
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup connection."""
        self.close()

    def connect(self) -> None:
        """Establish SSH connection with security best practices.

        Authentication hierarchy (Paramiko pattern):
        1. Explicit key file (if provided)
        2. SSH agent keys
        3. Discoverable keys (~/.ssh/id_*)

        Security features:
        - System host keys loaded from ~/.ssh/known_hosts
        - RejectPolicy for unknown hosts (secure default)
        - IPv4/IPv6 automatic fallback
        - Proper timeouts for all phases

        Raises:
            SSHConnectionError: Connection failed
            SSHAuthenticationError: Authentication failed
        """
        self.client = paramiko.SSHClient()
        self.client.load_system_host_keys()

        # NOTE: DO NOT use AutoAddPolicy in production - always use RejectPolicy
        self.client.set_missing_host_key_policy(paramiko.RejectPolicy())

        try:
            self.client.connect(
                hostname=self.config.ansible_host,
                port=self.config.ansible_port,
                username=self.config.ansible_user,
                key_filename=str(self.config.key_file)
                if self.config.key_file
                else None,
                timeout=10.0,
                banner_timeout=10.0,
                auth_timeout=10.0,
                allow_agent=True,
                look_for_keys=True,
            )
        except paramiko.AuthenticationException as e:
            raise SSHAuthenticationError(
                f"Authentication failed for {self.config.connection_string()}"
            ) from e
        except Exception as e:
            raise SSHConnectionError(
                f"Failed to connect to {self.config.connection_string()}: {e}"
            ) from e

    def execute(self, command: str) -> str:
        """Execute command and return buffered output.

        Args:
            command: Shell command to execute

        Returns:
            Command output as string (includes stderr if present)

        Raises:
            SSHConnectionError: Not connected or execution failed

        Example:
            >>> output = ssh.execute('ls -la')
            >>> print(output.strip())
        """
        if not self.client:
            raise SSHConnectionError("Not connected - call connect() first")

        stdin, stdout, stderr = self.client.exec_command(command)

        try:
            output = stdout.read().decode("utf-8", errors="ignore")
            errors = stderr.read().decode("utf-8", errors="ignore")

            if errors:
                return f"{output}\n{errors}"
            return output
        finally:
            stdin.close()
            stdout.close()
            stderr.close()

    def execute_stream(self, command: str) -> Generator[str, None, None]:
        """Execute command and stream output line by line.

        Args:
            command: Shell command to execute (typically with -f flag for following)

        Yields:
            Output lines as they arrive (stripped of trailing whitespace)

        Raises:
            SSHConnectionError: Not connected or execution failed

        Example:
            >>> for line in ssh.execute_stream('tail -f /var/log/app.log'):
            ...     print(line)
        """
        if not self.client:
            raise SSHConnectionError("Not connected - call connect() first")

        stdin, stdout, stderr = self.client.exec_command(command)

        try:
            for line in stdout:
                yield line.rstrip()
        finally:
            stdin.close()
            stdout.close()
            stderr.close()

    def close(self) -> None:
        """Close SSH connection.

        Note: Explicit close is important even with context managers
        to avoid hangs during garbage collection.
        """
        if self.client:
            self.client.close()
            self.client = None
