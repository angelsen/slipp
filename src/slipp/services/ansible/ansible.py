"""Centralized Ansible subprocess wrapper."""

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import IO, Any, Callable

from slipp.utils.cli_tools import check_tool_installed
from slipp.utils.errors import AnsibleError, AnsibleNotFoundError

ProgressCallback = Callable[[str], None]

_PROGRESS_RE = re.compile(r"^(PLAY|TASK|RUNNING HANDLER) \[(.+?)\]")


def parse_playbook_progress(line: str) -> str | None:
    """Extract a clean progress label from an ansible-playbook output line.

    Returns None for lines that shouldn't change the displayed status
    (blank lines, per-host results, warnings, recap table rows).
    """
    if line.startswith("PLAY RECAP"):
        return "finishing"

    match = _PROGRESS_RE.match(line)
    if not match:
        return None

    kind, name = match.group(1), match.group(2)
    if kind == "PLAY":
        return f"PLAY {name}"
    return name


@dataclass
class AnsibleResult:
    """Result from Ansible command execution."""

    exit_code: int
    log_path: Path | None = None
    no_hosts_matched: bool = False


_NO_HOSTS_SKIP_RE = re.compile(r"skipping: no hosts matched")
_RECAP_HOST_ROW_RE = re.compile(r"^\S+\s*:\s*ok=\d+")


def run_inventory(inventory_path: Path) -> dict[str, Any]:
    """Run ansible-inventory --list, return parsed JSON."""
    check_tool_installed("ansible-inventory", AnsibleNotFoundError)

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
    check_tool_installed("ansible-playbook", AnsibleNotFoundError)

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
    check_tool_installed("ansible-playbook", AnsibleNotFoundError)

    result = subprocess.run(
        ["ansible-playbook", str(playbook), "--syntax-check"],
        capture_output=True,
        text=True,
        check=False,
        cwd=playbook.parent,
    )
    return result.returncode == 0


def get_host_group(playbook_path: Path) -> str:
    """Extract host group pattern from playbook.

    Args:
        playbook_path: Path to playbook file

    Returns:
        Host group name (default: 'servers' if not detected)
    """
    check_tool_installed("ansible-playbook", AnsibleNotFoundError)

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


def _run_galaxy_command(
    cmd: list[str],
    env: dict[str, str],
    log_handle: IO[str] | None,
    on_progress: ProgressCallback | None,
) -> int:
    """Run one ansible-galaxy subprocess, streaming output to log/progress."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )

    assert proc.stdout is not None
    for line in proc.stdout:
        if log_handle:
            log_handle.write(line)
        if on_progress:
            on_progress(line.strip().removeprefix("- ")[:60])

    return proc.wait()


def install_requirements(
    requirements_file: str,
    roles_path: str = "roles",
    log_dir: Path | None = None,
    force: bool = False,
    on_progress: ProgressCallback | None = None,
) -> AnsibleResult:
    """Install roles and collections from requirements.yml via ansible-galaxy.

    Runs two steps: `ansible-galaxy role install` (installed to roles_path)
    and `ansible-galaxy collection install` (installed to the default
    collections path). The collection step is a no-op if requirements_file
    has no `collections:` block.

    Args:
        requirements_file: Path to requirements.yml file
        roles_path: Directory to install roles (default: roles/)
        log_dir: Directory for log file (optional)
        force: Force reinstall even if roles/collections exist
        on_progress: Optional callback for progress updates

    Returns:
        AnsibleResult with exit code (first non-zero step wins) and log path

    Note: Caller should check check_roles_installed() first if skip logic needed.
    """
    check_tool_installed("ansible-galaxy", AnsibleNotFoundError)

    log_path: Path | None = None
    log_handle = None
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        log_path = log_dir / f"ansible-galaxy-{timestamp}.log"
        log_handle = log_path.open("w")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    try:
        roles_cmd = [
            "ansible-galaxy",
            "role",
            "install",
            "-r",
            requirements_file,
            "-p",
            roles_path,
            "--force",
        ]
        exit_code = _run_galaxy_command(roles_cmd, env, log_handle, on_progress)

        if exit_code == 0:
            collections_cmd = [
                "ansible-galaxy",
                "collection",
                "install",
                "-r",
                requirements_file,
            ]
            if force:
                collections_cmd.append("--force")
            exit_code = _run_galaxy_command(
                collections_cmd, env, log_handle, on_progress
            )

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
    roles_path: list[str] | None = None,
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
        roles_path: Optional list of role directories (--roles-path)
        log_dir: Directory for log file (optional)
        extra_vars: Optional dict of extra variables to pass (-e key=value)
        on_progress: Optional callback for progress updates

    Returns:
        AnsibleResult with exit code and optional log path
    """
    check_tool_installed("ansible-playbook", AnsibleNotFoundError)

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
    if roles_path:
        env["ANSIBLE_ROLES_PATH"] = ":".join(roles_path)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=Path(playbook).parent,
        env=env,
    )

    saw_no_hosts_skip = False
    saw_recap_host_row = False

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if log_handle:
                log_handle.write(line)
            stripped = line.strip()
            if on_progress:
                on_progress(stripped)
            if _NO_HOSTS_SKIP_RE.search(stripped):
                saw_no_hosts_skip = True
            elif _RECAP_HOST_ROW_RE.match(stripped):
                saw_recap_host_row = True

        exit_code = proc.wait()
        return AnsibleResult(
            exit_code=exit_code,
            log_path=log_path,
            # A playbook whose `hosts:` pattern matches nothing still exits
            # 0 (ansible treats "no hosts matched" as a no-op, not a
            # failure). The recap-row guard avoids flagging a multi-play
            # playbook where only one play legitimately targets an empty
            # group while others ran normally.
            no_hosts_matched=saw_no_hosts_skip and not saw_recap_host_row,
        )

    finally:
        if log_handle:
            log_handle.close()
