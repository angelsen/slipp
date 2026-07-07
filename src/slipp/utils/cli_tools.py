"""Checks for required external CLI tools."""

import shutil

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
