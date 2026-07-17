"""wg-deploy provider verification and hub creation.

wg-deploy is a local checkout, not an API -- "verification" is a shape
check (playbook.yml + scripts/new-host.sh present) rather than an auth
call, but it lives here to match the per-provider module layout of
gigahost.py/pangolin.py.
"""

import subprocess
from pathlib import Path

from slipp.models.host import AnsibleHost
from slipp.services.run.caddy import CaddyProxy
from slipp.utils.errors import ProviderError, SSHConnectionError, WgManageError


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


def _guard_against_dev_proxy(name: str, ip: str) -> None:
    """Refuse to hub-ify a host already running slipp's dev proxy.

    wg-deploy's playbook installs its own Caddy and unconditionally
    regenerates /etc/caddy/Caddyfile from its services JSON -- on a host
    already running the dev proxy (`slipp bootstrap proxy`, used by `slipp
    run --tunnel-out`), this silently overwrites the dev proxy's config and
    strands its iptables :443->:8443 redirect pointed at a Caddy that no
    longer serves anything on :8443 once wg-manage's Caddy takes over :443
    directly. Same collision class, same probe, as
    dev_proxy_guard.guard_against_dev_proxy_collision (the deploy-side
    version) -- this is the hub-ification-side version, checked earlier
    since hub-ification is what actually clobbers the dev proxy's Caddy.

    Best-effort: a host we can't reach is left for new-host.sh's own SSH
    connection to fail on with its own, clearer error.

    Raises:
        WgManageError: If the dev proxy is confirmed installed on this host.
    """
    host = AnsibleHost(inventory_hostname=name, ansible_host=ip, ansible_user="root")
    try:
        with CaddyProxy(host) as proxy:
            dev_proxy_present = proxy.is_installed()
    except SSHConnectionError:
        return

    if dev_proxy_present:
        raise WgManageError(
            f"{ip} already runs slipp's dev proxy (`slipp run --tunnel-out`) "
            "-- hub-ifying it would let wg-manage's Caddy take over :443, "
            "stranding the dev proxy's iptables :443 redirect pointed at a "
            "port nothing serves anymore. Use a different host, or remove "
            "the dev proxy first if you're repurposing this box."
        )


def make_hub(name: str, ip: str, repo_path: Path) -> None:
    """Hub-ify a host by running wg-deploy's scripts/new-host.sh against it.

    Interactive: ansible-vault may prompt for the vault password (no
    stdout/stderr capture, so the prompt reaches the terminal).

    Raises:
        WgManageError: If the dev proxy is already installed on this host,
            new-host.sh exits non-zero, or the configured repo path has
            gone stale (moved/deleted since `providers add wg-deploy`
            validated it) and can't be used as a cwd.
    """
    _guard_against_dev_proxy(name, ip)
    try:
        result = subprocess.run(
            ["bash", "scripts/new-host.sh", name, ip],
            cwd=repo_path,
        )
    except OSError as e:
        raise WgManageError(f"Cannot run new-host.sh in {repo_path}: {e}") from e
    if result.returncode != 0:
        raise WgManageError(f"new-host.sh failed (exit {result.returncode})")
