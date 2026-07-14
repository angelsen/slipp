"""wg-deploy provider verification and hub creation.

wg-deploy is a local checkout, not an API -- "verification" is a shape
check (playbook.yml + scripts/new-host.sh present) rather than an auth
call, but it lives here to match the per-provider module layout of
gigahost.py/pangolin.py.
"""

import subprocess
from pathlib import Path

from slipp.utils.errors import ProviderError, WgManageError


def verify_repo(repo_path: Path) -> None:
    """Confirm repo_path looks like a wg-deploy checkout.

    Raises:
        ProviderError: If playbook.yml or scripts/new-host.sh is missing.
    """
    if (
        not (repo_path / "playbook.yml").is_file()
        or not (repo_path / "scripts" / "new-host.sh").is_file()
    ):
        raise ProviderError(f"Not a wg-deploy checkout: {repo_path}")


def make_hub(name: str, ip: str, repo_path: Path) -> None:
    """Hub-ify a host by running wg-deploy's scripts/new-host.sh against it.

    Interactive: ansible-vault may prompt for the vault password (no
    stdout/stderr capture, so the prompt reaches the terminal).

    Raises:
        WgManageError: If new-host.sh exits non-zero, or the configured
            repo path has gone stale (moved/deleted since `providers add
            wg-deploy` validated it) and can't be used as a cwd.
    """
    try:
        result = subprocess.run(
            ["bash", "scripts/new-host.sh", name, ip],
            cwd=repo_path,
        )
    except OSError as e:
        raise WgManageError(f"Cannot run new-host.sh in {repo_path}: {e}") from e
    if result.returncode != 0:
        raise WgManageError(f"new-host.sh failed (exit {result.returncode})")
