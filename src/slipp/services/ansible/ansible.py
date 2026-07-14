"""Centralized Ansible subprocess wrapper."""

import json
import os
import re
import subprocess
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

import yaml

from slipp import output
from slipp.utils.cli_tools import check_tool_installed, run_checked
from slipp.utils.errors import AnsibleError, AnsibleNotFoundError
from slipp.utils.files import open_log, prompted_secret_file

ProgressCallback = Callable[[str], None]

_PROGRESS_RE = re.compile(r"^(PLAY|TASK|RUNNING HANDLER) \[(.+?)\]")


def _parse_playbook_progress(line: str) -> str | None:
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


def spinner_progress_callback(update: Callable[[str], None]) -> ProgressCallback:
    """Build an on_progress callback that feeds playbook progress labels to a spinner's update fn."""

    def on_progress(line: str) -> None:
        label = _parse_playbook_progress(line)
        if label:
            update(label[:60])

    return on_progress


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


def run_list_tasks(
    playbook: Path,
    inventory: Path | None = None,
    roles_path: list[str] | None = None,
) -> str:
    """Run ansible-playbook --list-tasks, return stdout.

    Args:
        playbook: Path to playbook file
        inventory: Optional inventory path
        roles_path: Optional list of role directories (sets ANSIBLE_ROLES_PATH)
    """
    check_tool_installed("ansible-playbook", AnsibleNotFoundError)

    cmd = ["ansible-playbook", str(playbook), "--list-tasks"]
    if inventory and inventory.exists():
        cmd.extend(["-i", str(inventory)])

    env = _subprocess_env(roles_path)

    result = run_checked(cmd, AnsibleError, cwd=playbook.parent, env=env)

    return result.stdout


def _run_uncertain(
    cmd: list[str], cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess without raising, for callers that inspect the raw exit code."""
    return subprocess.run(
        cmd, capture_output=True, text=True, check=False, cwd=cwd, env=env
    )


def syntax_check(playbook: Path, roles_path: list[str] | None = None) -> bool:
    """Validate playbook syntax without executing.

    Args:
        playbook: Path to playbook file
        roles_path: Optional list of role directories (sets ANSIBLE_ROLES_PATH)

    Returns True if valid, False otherwise.
    """
    check_tool_installed("ansible-playbook", AnsibleNotFoundError)

    env = _subprocess_env(roles_path)

    result = _run_uncertain(
        ["ansible-playbook", str(playbook), "--syntax-check"], playbook.parent, env
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

    result = _run_uncertain(
        ["ansible-playbook", "--list-hosts", str(playbook_path)],
        playbook_path.parent,
        env,
    )

    for line in result.stdout.splitlines():
        if "pattern:" in line:
            match = re.search(r"pattern:\s*\['([^']+)'\]", line)
            if match:
                return match.group(1)

    return "servers"


def _check_roles_installed(install_dir: str) -> bool:
    """Check if roles are already installed.

    Args:
        install_dir: Directory where roles are installed

    Returns:
        True if roles directory exists and has content
    """
    roles_dir = Path(install_dir)
    return roles_dir.exists() and any(roles_dir.iterdir())


def _requirements_have_collections(requirements_file: str) -> bool:
    """Check if a requirements file declares a collections block.

    Collections install to a separate path from install_dir, so
    _check_roles_installed() can't see them -- this lets callers avoid
    skipping the install step when collections still need installing.
    """
    try:
        with open(requirements_file) as f:
            data = yaml.safe_load(f)
    except OSError:
        return False
    return isinstance(data, dict) and bool(data.get("collections"))


def _stream_subprocess(
    cmd: list[str],
    env: dict[str, str],
    log_handle: IO[str] | None,
    on_line: Callable[[str], None] | None = None,
    cwd: Path | None = None,
) -> int:
    """Run a subprocess, streaming each stdout line to log_handle/on_line.

    Shared by _run_galaxy_command and run_playbook, which both need to
    launch a subprocess, tee its combined stdout/stderr to a log file and a
    line callback, and make sure the process is terminated if the caller
    bails out (e.g. Ctrl-C) before it exits on its own.
    """
    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=cwd,
        env=env,
    ) as proc:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                if log_handle:
                    log_handle.write(line)
                if on_line:
                    on_line(line)

            return proc.wait()
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait()


def _run_galaxy_command(
    cmd: list[str],
    env: dict[str, str],
    log_handle: IO[str] | None,
    on_progress: ProgressCallback | None,
) -> int:
    """Run one ansible-galaxy subprocess, streaming output to log/progress."""

    def on_line(line: str) -> None:
        if on_progress:
            on_progress(line.strip().removeprefix("- ")[:60])

    return _stream_subprocess(cmd, env, log_handle, on_line)


def _install_requirements(
    requirements_file: str,
    install_dir: str = "roles",
    log_dir: Path | None = None,
    force: bool = False,
    on_progress: ProgressCallback | None = None,
) -> AnsibleResult:
    """Install roles and collections from requirements.yml via ansible-galaxy.

    Runs two steps: `ansible-galaxy role install` (installed to install_dir)
    and `ansible-galaxy collection install` (installed to the default
    collections path). The collection step is a no-op if requirements_file
    has no `collections:` block.

    Args:
        requirements_file: Path to requirements.yml file
        install_dir: Directory to install roles (default: roles/)
        log_dir: Directory for log file (optional)
        force: Force reinstall even if roles/collections exist
        on_progress: Optional callback for progress updates

    Returns:
        AnsibleResult with exit code (first non-zero step wins) and log path
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
            install_dir,
        ]
        if force:
            roles_cmd.append("--force")
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
    install_dir: str,
    *,
    log_dir: Path,
    force: bool = False,
) -> None:
    """Install galaxy requirements unless already present, with progress UI.

    Shared by deploy and launch/scaffold, which both need "skip if already
    installed, show a spinner, raise with the log path on failure" - the
    only prior difference was deploy re-implementing _check_roles_installed()
    inline instead of calling it.

    Args:
        requirements_file: Path to requirements.yml
        install_dir: Directory to install roles into
        log_dir: Directory for install logs
        force: Force reinstall even if roles are already present

    Raises:
        AnsibleError: If installation fails
    """
    if (
        not force
        and _check_roles_installed(install_dir)
        and not _requirements_have_collections(requirements_file)
    ):
        output.info(f"Roles already installed in {install_dir}")
        return

    with output.spinner("Installing requirements") as update:
        result = _install_requirements(
            requirements_file,
            install_dir,
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
    deploy target and writes a temp password file, deleted on exit.

    Passed via --become-password-file, same as vault_password_file is
    passed via --vault-password-file, to keep it out of argv/`ps`.

    Yields:
        Path to a temporary password file (deleted on exit)
    """
    with prompted_secret_file("BECOME (sudo) password", prefix="become_pass_") as path:
        yield path


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
        become_pw_file: Optional path to a become-password file
            (see become_password_file() above)
        tags: Optional comma-separated tags to run
        skip_tags: Optional comma-separated tags to skip
        roles_path: Optional list of role directories (sets ANSIBLE_ROLES_PATH)
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
        cmd.extend(["--become-password-file", str(become_pw_file)])
    if tags:
        cmd.extend(["--tags", tags])
    if skip_tags:
        cmd.extend(["--skip-tags", skip_tags])
    if extra_vars:
        for key, value in extra_vars.items():
            cmd.extend(["-e", f"{key}={json.dumps(value)}"])

    log_path, log_handle = open_log(log_dir, "ansible-playbook")
    env = _subprocess_env(roles_path, unbuffered=True)

    saw_no_hosts_skip = False
    saw_recap_host_row = False

    def on_line(line: str) -> None:
        nonlocal saw_no_hosts_skip, saw_recap_host_row
        stripped = line.strip()
        if on_progress:
            on_progress(stripped)
        if _NO_HOSTS_SKIP_RE.search(stripped):
            saw_no_hosts_skip = True
        elif _RECAP_HOST_ROW_RE.match(stripped):
            saw_recap_host_row = True

    try:
        exit_code = _stream_subprocess(
            cmd, env, log_handle, on_line, cwd=Path(playbook).parent
        )
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
