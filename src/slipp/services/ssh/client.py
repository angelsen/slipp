"""SSH service with Paramiko wrapper and best practices."""

from collections.abc import Generator
from dataclasses import dataclass

import paramiko

from slipp.models.host import AnsibleHost
from slipp.utils.errors import (
    SSHAuthenticationError,
    SSHCommandError,
    SSHConnectionError,
    SudoPasswordRequired,
)


@dataclass(frozen=True)
class SSHResult:
    """Result of a remote command execution."""

    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        """True if the command exited zero."""
        return self.exit_code == 0

    @property
    def text(self) -> str:
        """Combined stdout+stderr for display (matches the old execute() return)."""
        return f"{self.stdout}\n{self.stderr}" if self.stderr else self.stdout

    def check(self, context: str) -> "SSHResult":
        """Raise SSHCommandError if the command exited non-zero.

        Args:
            context: Human-readable description of what the command was doing,
                prefixed to the error message

        Returns:
            self, for chaining
        """
        if not self.ok:
            detail = self.stderr.strip() or self.stdout.strip()
            raise SSHCommandError(f"{context} (exit {self.exit_code})\n{detail}")
        return self


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
        ...     result = ssh.execute('ls -la')
        ...     print(result.stdout)
    """

    def __init__(self, host_config: AnsibleHost, sudo_password: str | None = None):
        """Initialize SSH service with host configuration.

        Args:
            host_config: Host configuration with SSH details
            sudo_password: If set, commands starting with ``sudo`` are
                rewritten to ``sudo -S`` and the password is piped via stdin.
        """
        self.config = host_config
        self.sudo_password = sudo_password
        self.client: paramiko.SSHClient | None = None
        self.last_stream_result: SSHResult | None = None

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

    def require_sudo(self, context: str) -> None:
        """Probe whether passwordless sudo works; raise early if not.

        Runs ``sudo -n true`` (non-interactive, no-op command). If it fails
        and no sudo_password was provided, raises SudoPasswordRequired
        immediately — before the caller runs anything that needs sudo.
        No-op when a password was provided (check_sudo catches a rejected
        one on the first real command).
        """
        if self.sudo_password:
            return
        probe = self.execute("sudo -n true")
        if not probe.ok:
            raise SudoPasswordRequired(
                f"{context}: sudo requires a password on this host. "
                "Use --ask-become-pass to provide it."
            )

    def _prepare_sudo_command(self, command: str) -> tuple[str, str | None]:
        """Rewrite a sudo command to read the password from stdin.

        All sudo commands get ``LC_MESSAGES=C`` so error messages are
        always English regardless of the remote host's locale — sudo's
        messages are gettext-translated and check_sudo matches English.

        Returns:
            Tuple of (possibly-rewritten command, stdin payload or None)
        """
        if not command.startswith("sudo "):
            return command, None
        rest = command[5:]
        if self.sudo_password:
            # -p '' suppresses the "[sudo] password for user:" prompt that
            # would otherwise leak into stderr (and displayed output)
            return f"LC_MESSAGES=C sudo -S -p '' {rest}", self.sudo_password + "\n"
        return f"LC_MESSAGES=C sudo {rest}", None

    def check_sudo(self, result: SSHResult, context: str) -> None:
        """Raise SudoPasswordRequired if a result looks like a sudo auth failure."""
        if (
            not result.ok
            and not result.stdout.strip()
            and (
                "a password is required" in result.stderr
                or "a terminal is required" in result.stderr
                or "incorrect password attempt" in result.stderr
            )
        ):
            hint = (
                "The provided sudo password was rejected."
                if self.sudo_password
                else "Use --ask-become-pass to provide it."
            )
            raise SudoPasswordRequired(
                f"{context}: sudo requires a password on this host. {hint}"
            )

    def execute(self, command: str, stdin_data: str | None = None) -> SSHResult:
        """Execute command and return its exit code, stdout, and stderr.

        Args:
            command: Shell command to execute
            stdin_data: Optional data to write to the command's stdin (e.g. a
                secret piped into `docker login --password-stdin`, avoiding
                the secret ever appearing in the remote command line)

        Returns:
            SSHResult with exit_code, stdout, stderr

        Raises:
            SSHConnectionError: Not connected

        Example:
            >>> result = ssh.execute('ls -la')
            >>> if result.ok:
            ...     print(result.stdout.strip())
        """
        if not self.client:
            raise SSHConnectionError("Not connected - call connect() first")

        command, sudo_stdin = self._prepare_sudo_command(command)
        if sudo_stdin:
            stdin_data = sudo_stdin + (stdin_data or "")

        stdin, stdout, stderr = self.client.exec_command(command)

        try:
            if stdin_data is not None:
                stdin.write(stdin_data)
                stdin.flush()
            stdin.channel.shutdown_write()

            out = stdout.read().decode("utf-8", errors="ignore")
            err = stderr.read().decode("utf-8", errors="ignore")
            # recv_exit_status() must come after draining stdout/stderr, or a
            # command with output larger than the channel window can deadlock.
            exit_code = stdout.channel.recv_exit_status()

            return SSHResult(exit_code=exit_code, stdout=out, stderr=err)
        finally:
            stdin.close()
            stdout.close()
            stderr.close()

    def execute_stream(self, command: str) -> Generator[str, None, None]:
        """Execute command and stream stdout line by line.

        After the stream ends naturally (not via KeyboardInterrupt),
        ``self.last_stream_result`` holds the exit code and stderr so
        the caller can inspect them.  Stdin is closed after the optional
        sudo password, so streamed commands cannot read interactive input.

        Args:
            command: Shell command to execute (typically with -f flag for following)

        Yields:
            Output lines as they arrive (stripped of trailing whitespace)

        Raises:
            SSHConnectionError: Not connected or execution failed

        Example:
            >>> for line in ssh.execute_stream('tail -f /var/log/app.log'):
            ...     print(line)
            >>> if ssh.last_stream_result:
            ...     ssh.check_sudo(ssh.last_stream_result, "streaming")
        """
        if not self.client:
            raise SSHConnectionError("Not connected - call connect() first")

        self.last_stream_result = None
        command, sudo_stdin = self._prepare_sudo_command(command)
        chan_stdin, chan_stdout, chan_stderr = self.client.exec_command(command)

        try:
            if sudo_stdin:
                chan_stdin.write(sudo_stdin)
                chan_stdin.flush()
            chan_stdin.channel.shutdown_write()
            for line in chan_stdout:
                yield line.rstrip()
            err = chan_stderr.read().decode("utf-8", errors="ignore")
            exit_code = chan_stdout.channel.recv_exit_status()
            self.last_stream_result = SSHResult(
                exit_code=exit_code, stdout="", stderr=err
            )
        finally:
            chan_stdin.close()
            chan_stdout.close()
            chan_stderr.close()

    def close(self) -> None:
        """Close SSH connection.

        Note: Explicit close is important even with context managers
        to avoid hangs during garbage collection.
        """
        if self.client:
            self.client.close()
            self.client = None
