"""Pre-deploy guard against colliding with the dev proxy on the target host."""

from pathlib import Path

from slipp.models.deployment import DeploymentHostConfig
from slipp.services.config.detection import has_caddy_role, has_wg_manage_role
from slipp.services.run.caddy import CaddyProxy
from slipp.utils.errors import DeployError, SSHConnectionError


def guard_against_dev_proxy_collision(
    project_root: Path, host: DeploymentHostConfig | None
) -> None:
    """Refuse to deploy a Caddy-fronted or wg-manage-exposed project onto a
    host running the dev proxy.

    `slipp launch --proxy caddy`, wg-manage (which owns Caddy on any host
    it hubs), and the dev proxy (`slipp bootstrap proxy`, used by `slipp run
    --tunnel-out`) all bind Caddy on :443 with no coordination between them.
    Beyond the Caddyfile-overwrite risk, the dev proxy also leaves an
    iptables :443->:8443 redirect in place -- once a different Caddy (an
    app's own role, or wg-manage's) takes over :443 directly, that stale
    redirect silently intercepts all inbound traffic and sends it to a port
    nothing listens on anymore, breaking the deploy with zero warning even
    though `slipp deploy` itself reports success. Checked with the same
    CaddyProxy.is_installed() probe ensure_installed() already uses, so
    there's exactly one place that knows what "dev proxy present" means.

    Best-effort: a host we can't even reach to check is left for the real
    playbook run to fail on with its own, clearer connection error.

    Raises:
        DeployError: If the dev proxy is confirmed installed on this host.
    """
    if host is None:
        return
    if not has_caddy_role(project_root) and not has_wg_manage_role(project_root):
        return

    try:
        with CaddyProxy(host) as proxy:
            dev_proxy_present = proxy.is_installed()
    except SSHConnectionError:
        return

    if dev_proxy_present:
        raise DeployError(
            f"{host.ansible_host} already runs slipp's dev proxy "
            "(`slipp run --tunnel-out`) -- deploying this project would let "
            "another Caddy instance (this project's own role, or wg-manage's) "
            "take over :443, stranding the dev proxy's iptables :443 redirect "
            "pointed at a port nothing serves anymore. Move this deploy to a "
            "different host, or remove the dev proxy first if you're "
            "repurposing this box."
        )
