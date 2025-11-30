"""Centralized Ansible subprocess wrapper."""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from slipp.utils.errors import AnsibleError, AnsibleNotFoundError

ProgressCallback = Callable[[str], None]


@dataclass
class AnsibleResult:
    """Result from Ansible command execution."""

    exit_code: int
    log_path: Path | None = None


def _check_installed(tool: str) -> None:
    if not shutil.which(tool):
        raise AnsibleNotFoundError(
            f"'{tool}' not found. Install with: uv tool install ansible-core"
        )


def run_inventory(inventory_path: Path) -> dict[str, Any]:
    """Run ansible-inventory --list, return parsed JSON."""
    _check_installed("ansible-inventory")

    result = subprocess.run(
        ["ansible-inventory", "-i", str(inventory_path), "--list"],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise AnsibleError(
            f"'ansible-inventory' failed (exit {result.returncode}): {result.stderr[:200]}"
        )

    return json.loads(result.stdout)


def run_list_tasks(playbook: Path, inventory: Path | None = None) -> str:
    """Run ansible-playbook --list-tasks, return stdout."""
    _check_installed("ansible-playbook")

    cmd = ["ansible-playbook", str(playbook), "--list-tasks"]
    if inventory and inventory.exists():
        cmd.extend(["-i", str(inventory)])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        cwd=playbook.parent,
    )

    if result.returncode != 0:
        raise AnsibleError(
            f"'ansible-playbook' failed (exit {result.returncode}): {result.stderr[:200]}"
        )

    return result.stdout


def syntax_check(playbook: Path) -> bool:
    """Validate playbook syntax without executing.

    Returns True if valid, False otherwise.
    """
    _check_installed("ansible-playbook")

    result = subprocess.run(
        ["ansible-playbook", str(playbook), "--syntax-check"],
        capture_output=True,
        text=True,
        check=False,
        cwd=playbook.parent,
    )
    return result.returncode == 0


def validate_inventory(inventory_path: Path) -> bool:
    """Validate inventory file is parseable.

    Returns True if valid, False otherwise.
    """
    try:
        run_inventory(inventory_path)
        return True
    except AnsibleError:
        return False


def get_host_group(playbook_path: Path) -> str:
    """Extract host group pattern from playbook.

    Args:
        playbook_path: Path to playbook file

    Returns:
        Host group name (default: 'servers' if not detected)
    """
    _check_installed("ansible-playbook")

    result = subprocess.run(
        ["ansible-playbook", "--list-hosts", str(playbook_path)],
        capture_output=True,
        text=True,
        check=False,
        cwd=playbook_path.parent,
    )

    for line in result.stdout.splitlines():
        if "pattern:" in line:
            import re

            match = re.search(r"pattern:\s*\['([^']+)'\]", line)
            if match:
                return match.group(1)

    return "servers"


def check_roles_installed(roles_path: str) -> bool:
    """Check if roles are already installed.

    Args:
        roles_path: Directory where roles are installed

    Returns:
        True if roles directory exists and has content
    """
    roles_dir = Path(roles_path)
    return roles_dir.exists() and any(roles_dir.iterdir())


def install_requirements(
    requirements_file: str,
    roles_path: str = "roles",
    log_dir: Path | None = None,
    force: bool = False,
    on_progress: ProgressCallback | None = None,
) -> AnsibleResult:
    """Run ansible-galaxy install, return result.

    Args:
        requirements_file: Path to requirements.yml file
        roles_path: Directory to install roles (default: roles/)
        log_dir: Directory for log file (optional)
        force: Force reinstall even if roles exist
        on_progress: Optional callback for progress updates

    Returns:
        AnsibleResult with exit code and optional log path

    Note: Caller should check check_roles_installed() first if skip logic needed.
    """
    _check_installed("ansible-galaxy")

    cmd = [
        "ansible-galaxy",
        "role",
        "install",
        "-r",
        requirements_file,
        "-p",
        roles_path,
        "--force",
    ]

    log_path: Path | None = None
    log_handle = None
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        log_path = log_dir / f"ansible-galaxy-{timestamp}.log"
        log_handle = log_path.open("w")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if log_handle:
                log_handle.write(line)
            if on_progress:
                on_progress(line.strip().removeprefix("- ")[:60])

        exit_code = proc.wait()
        return AnsibleResult(exit_code=exit_code, log_path=log_path)

    finally:
        if log_handle:
            log_handle.close()


def run_playbook(
    playbook: str,
    inventory: str,
    check: bool = False,
    vault_file: str | None = None,
    vault_password_file: Path | None = None,
    tags: str | None = None,
    skip_tags: str | None = None,
    log_dir: Path | None = None,
    extra_vars: dict[str, Any] | None = None,
    on_progress: ProgressCallback | None = None,
) -> AnsibleResult:
    """Run ansible-playbook, return result.

    Args:
        playbook: Path to playbook file
        inventory: Path to inventory file
        check: Run in dry-run mode
        vault_file: Optional path to vault file (adds -e @path)
        vault_password_file: Optional path to vault password file
        tags: Optional comma-separated tags to run
        skip_tags: Optional comma-separated tags to skip
        log_dir: Directory for log file (optional)
        extra_vars: Optional dict of extra variables to pass (-e key=value)
        on_progress: Optional callback for progress updates

    Returns:
        AnsibleResult with exit code and optional log path
    """
    _check_installed("ansible-playbook")

    cmd = ["ansible-playbook", playbook, "-i", inventory]
    if check:
        cmd.append("--check")
    if vault_file:
        cmd.extend(["-e", f"@{vault_file}"])
    if vault_password_file:
        cmd.extend(["--vault-password-file", str(vault_password_file)])
    if tags:
        cmd.extend(["--tags", tags])
    if skip_tags:
        cmd.extend(["--skip-tags", skip_tags])
    if extra_vars:
        for key, value in extra_vars.items():
            cmd.extend(["-e", f"{key}={json.dumps(value)}"])

    log_path: Path | None = None
    log_handle = None
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        log_path = log_dir / f"ansible-playbook-{timestamp}.log"
        log_handle = log_path.open("w")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=Path(playbook).parent,
        env=env,
    )

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if log_handle:
                log_handle.write(line)
            if on_progress:
                on_progress(line.strip()[:60])

        exit_code = proc.wait()
        return AnsibleResult(exit_code=exit_code, log_path=log_path)

    finally:
        if log_handle:
            log_handle.close()
