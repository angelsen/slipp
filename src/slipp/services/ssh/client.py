"""SSH service with Paramiko wrapper and best practices."""

import sys
import threading
from collections.abc import Generator
from dataclasses import dataclass

import paramiko

from slipp import output
from slipp.models.host import AnsibleHost
from slipp.utils.errors import (
    SSHAuthenticationError,
    SSHCommandError,
    SSHConnectionError,
    SudoPasswordRequired,
)

# Verified sudo passwords per connection, so every SSHService in one CLI
# invocation (discovery, then logs/status/exec's second connection) reuses
# a password prompted once. Keyed by AnsibleHost.connection_string().
_sudo_passwords: dict[str, str] = {}
# Connections verified to have working passwordless sudo (skip re-probing).
_sudo_passwordless: set[str] = set()


def _can_prompt() -> bool:
    """Only prompt from the main thread of an interactive session."""
    return sys.stdin.isatty() and threading.current_thread() is threading.main_thread()


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

    def __init__(self, host_config: AnsibleHost):
        """Initialize SSH service with host configuration.

        Args:
            host_config: Host configuration with SSH details
        """
        self.config = host_config
        self.client: paramiko.SSHClient | None = None
        self.last_stream_result: SSHResult | None = None

    @property
    def sudo_password(self) -> str | None:
        """Verified sudo password for this connection, if one was prompted.

        Read lazily from the process-wide cache so an SSHService constructed
        before the prompt happened (e.g. exec's connection, opened before
        discovery) still picks the password up.
        """
        return _sudo_passwords.get(self.config.connection_string())

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

    def ensure_sudo(self, context: str) -> None:
        """Make sure sudo will work: passwordless, cached password, or prompt.

        Probes ``sudo -n true``; on failure prompts for the password (main
        thread + tty only), verifies it, and caches it for every later
        SSHService to the same connection. Raises SudoPasswordRequired when
        prompting is impossible or the password is rejected 3 times.
        """
        key = self.config.connection_string()
        if self.sudo_password is not None or key in _sudo_passwordless:
            return
        if self.execute("sudo -n true").ok:
            _sudo_passwordless.add(key)
            return
        if not _can_prompt():
            raise SudoPasswordRequired(
                f"{context}: sudo requires a password on {key} and no "
                "terminal is available to prompt. Run a single-host command "
                "from a terminal (e.g. 'slipp ps -p <project>') to enter it."
            )
        for _ in range(3):
            candidate = output.prompt_password(f"BECOME (sudo) password for {key}")
            # Doesn't start with "sudo " so _prepare_sudo_command leaves it
            # alone; the candidate is piped manually.
            probe = self.execute(
                "LC_MESSAGES=C sudo -S -p '' true", stdin_data=candidate + "\n"
            )
            if probe.ok:
                _sudo_passwords[key] = candidate
                return
            # A correct password can still fail authorization (user not in
            # sudoers) — re-prompting won't help, so surface sudo's own
            # message instead. Strings from sudo's logging.c, pinned to
            # English by LC_MESSAGES=C above.
            fatal = next(
                (
                    line.strip()
                    for line in probe.stderr.splitlines()
                    if "is not in the sudoers file" in line
                    or "is not allowed to run sudo" in line
                    or "may not run sudo" in line
                ),
                None,
            )
            if fatal:
                raise SudoPasswordRequired(f"{context}: {fatal}")
            output.warning("Sudo password rejected, try again.")
        raise SudoPasswordRequired(
            f"{context}: sudo password rejected after 3 attempts."
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
                "The sudo password was rejected."
                if self.sudo_password
                else "Commands with embedded sudo can't be prompted for a "
                "password; use a leading sudo (e.g. 'slipp exec -u root ...')."
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
