"""Per-process SSH transcript log: every command's invocation and output."""

import threading
from datetime import datetime
from pathlib import Path
from typing import IO, TYPE_CHECKING

from slipp import output
from slipp.models.host import AnsibleHost
from slipp.utils.files import get_log_dir, open_log

if TYPE_CHECKING:
    from slipp.services.ssh.client import SSHResult

# Log of every SSH command executed this process, opened lazily on the first
# one (so a cache-hit `slipp ps` that never touches SSH creates no file) and
# shared by every SSHService constructed afterwards — a module-level cache so
# no construction site needs a log_dir param threaded through it. One slipp
# invocation is always one process, so there's no session boundary to
# manage: the log just stays open for the process's lifetime.
_ssh_log_handle: IO[str] | None = None
_ssh_log_path: Path | None = None
_ssh_log_attempted = False
_ssh_log_lock = threading.Lock()


def _ensure_ssh_log_open() -> None:
    """Open this run's SSH log on first use; at most one attempt per process.

    Anchored to the enclosing project root (falling back to cwd for
    project-less commands), matching deploy's own log placement, so logs for
    one project don't scatter across whatever directory a command happened
    to run from. Best-effort: if the log can't be opened (read-only cwd,
    disk full, etc.) logging is silently skipped rather than failing the SSH
    command it would have logged.
    """
    global _ssh_log_handle, _ssh_log_path, _ssh_log_attempted
    if _ssh_log_attempted:
        return
    with _ssh_log_lock:
        if _ssh_log_attempted:
            return
        _ssh_log_attempted = True
        # Local import: services.config -> hosts.py -> services.discovery ->
        # discovery.py imports SSHService from slipp.services.ssh.client, so
        # a top-level import here would be circular.
        from slipp.services.config import LocalConfigService

        try:
            project_root = LocalConfigService.resolve_root()
            _ssh_log_path, _ssh_log_handle = open_log(get_log_dir(project_root), "ssh")
        except OSError:
            pass


def hint_ssh_log() -> None:
    """Print a 'See log: ...' hint if this run wrote to the SSH log."""
    if _ssh_log_path is not None:
        output.hint(f"See log: {_ssh_log_path}")


def _write_ssh_log(text: str, *, ensure_open: bool = False) -> None:
    """Append text to this run's SSH log.

    Args:
        text: Text to append.
        ensure_open: Lazily open the log first (for the first write of a
            command/stream); later writes to an already-open stream skip
            this since `_ensure_ssh_log_open` has already run.
    """
    if ensure_open:
        _ensure_ssh_log_open()
    if _ssh_log_handle is None:
        return
    with _ssh_log_lock:
        if _ssh_log_handle is not None:
            _ssh_log_handle.write(text)
            _ssh_log_handle.flush()


def log_ssh_call(host: AnsibleHost, command: str, result: "SSHResult") -> None:
    """Append one command's invocation and output to this run's SSH log."""
    parts = [
        f"--- [{datetime.now().strftime('%H:%M:%S')}] {host.connection_string} ---\n",
        f"$ {command}\n",
    ]
    if result.stdout:
        parts.append(
            result.stdout if result.stdout.endswith("\n") else result.stdout + "\n"
        )
    for line in result.stderr.splitlines():
        parts.append(f"[stderr] {line}\n")
    parts.append(f"[exit {result.exit_code}]\n\n")
    _write_ssh_log("".join(parts), ensure_open=True)


def log_stream_start(host: AnsibleHost, command: str) -> None:
    """Write a stream's header line immediately, before any output arrives.

    Written incrementally (not buffered) since execute_stream() is used for
    `logs -f`, which can run indefinitely — buffering the whole stream in
    memory to log it in one shot would grow unbounded.
    """
    _write_ssh_log(
        f"--- [{datetime.now().strftime('%H:%M:%S')}] {host.connection_string} ---\n"
        f"$ {command}\n",
        ensure_open=True,
    )


def log_stream_line(line: str) -> None:
    """Write one streamed output line to the log as it's yielded."""
    _write_ssh_log(f"{line}\n")


def log_stream_end(stderr: str, exit_code: int) -> None:
    """Write a stream's trailing stderr/exit-code footer, once it ends."""
    parts = [f"[stderr] {line}\n" for line in stderr.splitlines()]
    parts.append(f"[exit {exit_code}]\n\n")
    _write_ssh_log("".join(parts))
