"""File utilities shared across services."""

import os
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import IO, Iterator

from slipp import output


@contextmanager
def temp_secret_file(
    content: str, *, prefix: str = "slipp_", suffix: str = ""
) -> Iterator[Path]:
    """Write content to a 0600 temp file, yield its path, delete on exit.

    Uses mkstemp so the file is created with restrictive permissions from
    the start (no window where a secret sits in a world-readable file).
    """
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix, text=True)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        yield Path(path)
    finally:
        Path(path).unlink(missing_ok=True)


@contextmanager
def prompted_secret_file(
    label: str, *, prefix: str, confirm: bool = False
) -> Iterator[Path]:
    """Prompt for a password and write it to a temp file, deleted on exit.

    Shared by vault_password_file (ansible-vault) and become_password_file
    (sudo) -- both pass the result via a --*-password-file flag to keep the
    secret out of argv/`ps`, differing only in the prompt label and whether
    to confirm.

    Args:
        label: Prompt label shown to the user
        prefix: Temp file prefix (for identifying the file's purpose in /tmp)
        confirm: If True, prompt twice and verify match

    Yields:
        Path to temporary password file (deleted on exit)

    Raises:
        PasswordMismatchError: If confirm=True and passwords don't match
    """
    password = output.prompt_password(label, require_confirmation=confirm)
    with temp_secret_file(password, prefix=prefix) as path:
        yield path


def get_log_dir(base: Path | None = None) -> Path:
    """Return .slipp/logs/ path (does not create the directory)."""
    base = base or Path.cwd()
    return base / ".slipp" / "logs"


def open_log(log_dir: Path | None, prefix: str) -> tuple[Path | None, IO[str] | None]:
    """Open a timestamped 0600 log file under log_dir, if log_dir is given.

    Command output logged here (e.g. SSH command stdout/stderr) can contain
    secrets, so it gets the same restrictive permissions as temp_secret_file.
    """
    if not log_dir:
        return None, None
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    log_path = log_dir / f"{prefix}-{timestamp}.log"
    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    return log_path, os.fdopen(fd, "w")


def scan_roles_from_directories(
    roles_paths: list[str], project_root: Path
) -> list[str]:
    """Scan role directories for role names (faster than ansible-playbook --list-tasks).

    Args:
        roles_paths: List of role directory paths (relative or absolute)
        project_root: Project root for resolving relative paths

    Returns:
        Sorted list of unique role names
    """
    roles: set[str] = set()
    for role_path_str in roles_paths:
        role_path = Path(role_path_str)
        if not role_path.is_absolute():
            role_path = project_root / role_path
        if role_path.exists():
            roles.update(d.name for d in role_path.iterdir() if d.is_dir())
    return sorted(roles)


def atomic_write_text(path: Path, content: str, *, mode: int | None = None) -> None:
    """Write text to path atomically via a temp file in the same directory.

    Args:
        path: Destination file path
        content: Text content to write
        mode: Optional file permission bits to set after write (e.g. 0o600)

    Raises:
        Exception: If write fails (temp file is cleaned up)
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
        if mode is not None:
            path.chmod(mode)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise
