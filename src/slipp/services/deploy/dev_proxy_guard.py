"""Pre-deploy guard against colliding with the dev proxy on the target host."""

from pathlib import Path

from slipp.models.deployment import DeploymentHostConfig
from slipp.services.config.detection import has_caddy_role
from slipp.services.run.caddy import CaddyProxy
from slipp.utils.errors import DeployError, SSHConnectionError


def guard_against_dev_proxy_collision(
    project_root: Path, host: DeploymentHostConfig | None
) -> None:
    """Refuse to deploy a Caddy-fronted project onto a host running the dev proxy.

    `slipp launch --proxy caddy` and the dev proxy (`slipp bootstrap proxy`,
    used by `slipp run --tunnel-out`) both own /etc/caddy/Caddyfile on the
    target host with no coordination between them -- deploying here would
    silently overwrite whichever one is currently live, worse yet leaving
    the dev proxy's iptables :443 redirect pointed at a Caddy config that no
    longer serves anything on :8443. Checked with the same
    CaddyProxy.is_installed() probe ensure_installed() already uses, so
    there's exactly one place that knows what "dev proxy present" means.

    Best-effort: a host we can't even reach to check is left for the real
    playbook run to fail on with its own, clearer connection error.

    Raises:
        DeployError: If the dev proxy is confirmed installed on this host.
    """
    if not has_caddy_role(project_root) or host is None:
        return

    try:
        with CaddyProxy(host) as proxy:
            dev_proxy_present = proxy.is_installed()
    except SSHConnectionError:
        return

    if dev_proxy_present:
        raise DeployError(
            f"{host.ansible_host} already runs slipp's dev proxy "
            "(`slipp run --tunnel-out`) -- deploying this Caddy-fronted "
            "project would silently overwrite its Caddyfile and strand its "
            "iptables :443 redirect. Move this deploy to a different host, "
            "or remove the dev proxy first if you're repurposing this box."
        )
