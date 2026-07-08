"""Checks for required external CLI tools."""

import shutil
import subprocess
from pathlib import Path

from slipp.utils.errors import SlippError


def check_tool_installed(
    tool: str,
    error_cls: type[SlippError],
    install_hint: str = "uv tool install ansible-core",
) -> None:
    """Raise error_cls if tool isn't on PATH.

    Args:
        tool: Executable name to check (e.g. "ansible-playbook").
        error_cls: SlippError subclass to raise if not found.
        install_hint: Install command shown in the error message.

    Raises:
        error_cls: If tool is not found on PATH.
    """
    if not shutil.which(tool):
        raise error_cls(f"'{tool}' not found. Install with: {install_hint}")


def run_checked(
    cmd: list[str],
    error_cls: type[SlippError],
    *,
    context: str | None = None,
    cwd: Path | None = None,
    input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess, raising error_cls if it exits non-zero.

    Args:
        cmd: Command and arguments to run.
        error_cls: SlippError subclass to raise on non-zero exit.
        context: Label for the error message (defaults to "'<cmd[0]>'").
        cwd: Working directory for the subprocess.
        input: Data to write to the subprocess's stdin (e.g. a secret value,
            keeping it off argv/`ps` output).

    Returns:
        The completed process (stdout/stderr captured as text).

    Raises:
        error_cls: If the subprocess exits non-zero.
    """
    result = subprocess.run(
        cmd, capture_output=True, text=True, check=False, cwd=cwd, input=input
    )
    if result.returncode != 0:
        label = context or f"'{cmd[0]}'"
        raise error_cls(
            f"{label} failed (exit {result.returncode}): {result.stderr.strip()[:200]}"
        )
    return result
