"""Centralized Ansible subprocess wrapper."""

import json
import os
import re
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Callable

from slipp import output
from slipp.utils.cli_tools import check_tool_installed, run_checked
from slipp.utils.errors import AnsibleError, AnsibleNotFoundError
from slipp.utils.files import open_log

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


def _subprocess_env(
    roles_path: list[str] | None = None, *, unbuffered: bool = False
) -> dict[str, str]:
    """Build a subprocess environment with the common ansible-related overrides."""
    env = os.environ.copy()
    if roles_path:
        env["ANSIBLE_ROLES_PATH"] = ":".join(roles_path)
    if unbuffered:
        env["PYTHONUNBUFFERED"] = "1"
    return env


_NO_HOSTS_SKIP_RE = re.compile(r"skipping: no hosts matched")
_RECAP_HOST_ROW_RE = re.compile(r"^\S+\s*:\s*ok=\d+")


def run_inventory(inventory_path: Path) -> dict[str, Any]:
    """Run ansible-inventory --list, return parsed JSON."""
    check_tool_installed("ansible-inventory", AnsibleNotFoundError)

    result = run_checked(
        ["ansible-inventory", "-i", str(inventory_path), "--list"], AnsibleError
    )

    return json.loads(result.stdout)


def run_list_tasks(playbook: Path, inventory: Path | None = None) -> str:
    """Run ansible-playbook --list-tasks, return stdout."""
    check_tool_installed("ansible-playbook", AnsibleNotFoundError)

    cmd = ["ansible-playbook", str(playbook), "--list-tasks"]
    if inventory and inventory.exists():
        cmd.extend(["-i", str(inventory)])

    result = run_checked(cmd, AnsibleError, cwd=playbook.parent)

    return result.stdout


def syntax_check(playbook: Path, roles_path: list[str] | None = None) -> bool:
    """Validate playbook syntax without executing.

    Args:
        playbook: Path to playbook file
        roles_path: Optional list of role directories (sets ANSIBLE_ROLES_PATH)

    Returns True if valid, False otherwise.
    """
    check_tool_installed("ansible-playbook", AnsibleNotFoundError)

    env = _subprocess_env(roles_path)

    result = subprocess.run(
        ["ansible-playbook", str(playbook), "--syntax-check"],
        capture_output=True,
        text=True,
        check=False,
        cwd=playbook.parent,
        env=env,
    )
    return result.returncode == 0


def get_host_group(playbook_path: Path, roles_path: list[str] | None = None) -> str:
    """Extract host group pattern from playbook.

    Args:
        playbook_path: Path to playbook file
        roles_path: Optional list of role directories (sets ANSIBLE_ROLES_PATH)

    Returns:
        Host group name (default: 'servers' if not detected)
    """
    check_tool_installed("ansible-playbook", AnsibleNotFoundError)

    env = _subprocess_env(roles_path)

    result = subprocess.run(
        ["ansible-playbook", "--list-hosts", str(playbook_path)],
        capture_output=True,
        text=True,
        check=False,
        cwd=playbook_path.parent,
        env=env,
    )

    for line in result.stdout.splitlines():
        if "pattern:" in line:
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

    log_path, log_handle = open_log(log_dir, "ansible-galaxy")
    env = _subprocess_env(unbuffered=True)

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


def ensure_requirements_installed(
    requirements_file: str,
    roles_path: str,
    *,
    log_dir: Path,
    force: bool = False,
) -> None:
    """Install galaxy requirements unless already present, with progress UI.

    Shared by deploy and launch/scaffold, which both need "skip if already
    installed, show a spinner, raise with the log path on failure" - the
    only prior difference was deploy re-implementing check_roles_installed()
    inline instead of calling it.

    Args:
        requirements_file: Path to requirements.yml
        roles_path: Directory to install roles into
        log_dir: Directory for install logs
        force: Force reinstall even if roles are already present

    Raises:
        AnsibleError: If installation fails
    """
    if not force and check_roles_installed(roles_path):
        output.info(f"Roles already installed in {roles_path}")
        return

    with output.spinner("Installing requirements") as update:
        result = install_requirements(
            requirements_file,
            roles_path,
            log_dir=log_dir,
            force=force,
            on_progress=update,
        )

    if result.exit_code == 0:
        output.success("Installing requirements")
        return

    message = "Installing requirements failed"
    if result.log_path:
        message += f"\nSee log: {result.log_path}"
    raise AnsibleError(message)


@contextmanager
def become_password_file() -> Iterator[Path]:
    """Context manager that prompts for the become (sudo) password on the
    deploy target and writes a temp extra-vars file, deleted on exit.

    Ansible has no dedicated --become-password-file flag (unlike
    --vault-password-file) - ansible_become_pass is a normal extra-var, so
    it's passed via -e @<file> rather than -e ansible_become_pass=<value>
    to keep it out of argv/`ps`.

    Yields:
        Path to a temporary YAML extra-vars file (deleted on exit)
    """
    password = output.prompt_password("BECOME (sudo) password")

    fd, path = tempfile.mkstemp(prefix="become_pass_", suffix=".yml", text=True)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(f"ansible_become_pass: {json.dumps(password)}\n")
        yield Path(path)
    finally:
        Path(path).unlink(missing_ok=True)


def maybe_become_password_file(stack: ExitStack, ask_become_pass: bool) -> Path | None:
    """Enter become_password_file() on `stack` if `ask_become_pass`, else None.

    Shared by every playbook-running caller that supports --ask-become-pass,
    so the prompt-or-skip decision isn't duplicated at each call site.
    """
    return stack.enter_context(become_password_file()) if ask_become_pass else None


def run_playbook(
    playbook: str,
    inventory: str,
    check: bool = False,
    vault_file: str | None = None,
    vault_password_file: Path | None = None,
    become_pw_file: Path | None = None,
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
        become_pw_file: Optional path to a become-password extra-vars file
            (see become_password_file() above)
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
    if become_pw_file:
        cmd.extend(["-e", f"@{become_pw_file}"])
    if tags:
        cmd.extend(["--tags", tags])
    if skip_tags:
        cmd.extend(["--skip-tags", skip_tags])
    if extra_vars:
        for key, value in extra_vars.items():
            cmd.extend(["-e", f"{key}={json.dumps(value)}"])

    log_path, log_handle = open_log(log_dir, "ansible-playbook")
    env = _subprocess_env(roles_path, unbuffered=True)

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
