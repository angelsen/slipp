"""Proxy ownership resolution stage.

Resolves `--proxy auto` to a concrete owner ("caddy" or "wg-manage") by
probing the target host over SSH, and caches the answer on the host's
inventory record so later launches/deploys against the same host skip the
probe. Runs after InventoryLoadStage, which is the earliest point SSH
connection details (ansible_host/user/port) exist.
"""

from slipp import output
from slipp.models.deployment import DeploymentHostConfig
from slipp.services.launch.context import FullContext
from slipp.services.launch.stages.common import require
from slipp.services.ssh import SSHService
from slipp.utils.errors import LaunchError


class ProxyResolutionStage:
    """Resolve `--proxy auto`, set skip_caddy, and apply the --public check.

    Resolution order:
    1. An explicit `--proxy` value (anything but "auto") always wins.
    2. Else a cached `proxy_owner` on the host (from a prior launch's
       inventory.yml) wins -- keeps re-launches offline-stable.
    3. Else probe the host with `wg-manage --version` over SSH: exit 0
       means the host is a wg-manage hub, a clean non-zero exit means a
       plain host that needs slipp's own caddy role.

    Only a *connected* probe's result gets cached to proxy_owner -- design
    intent is that an explicit `--proxy` "still overrides" (a one-off
    choice, not a fact about the host), and a failed SSH connection proves
    nothing about whether the host has wg-manage, so persisting either
    would permanently misconfigure future `--proxy auto` runs on a single
    manual override or a transient network blip.

    An inconclusive probe (connection failed) fails the launch outright
    rather than silently guessing caddy: guessing wrong doesn't just
    mis-set a cache -- it generates a full caddy-role project for *this*
    launch, and if deployed to a host that's actually a wg-manage hub,
    slipp's caddy would fight wg-manage's own Caddy for :80/:443. A
    deploy needs SSH to succeed anyway, so failing here costs nothing a
    deploy wouldn't already require -- it just fails at the cheaper, more
    diagnosable point instead of mid-deploy.

    The `--public`-requires-wg-manage check moves here from ValidationStage
    because it can't be evaluated before the proxy is resolved.
    """

    def execute(self, context: FullContext) -> None:
        """Resolve context.proxy/skip_caddy and persist proxy_owner.

        Args:
            context: Deployment context with inventory_config already
                loaded (by InventoryLoadStage).

        Raises:
            LaunchError: If --public is set but the resolved proxy isn't
                wg-manage, or if `--proxy auto` couldn't reach the host to
                probe it.
        """
        inventory_config = require(context.inventory_config, "inventory config")
        first_host = inventory_config.first_host

        if context.proxy != "auto":
            resolved = context.proxy
        elif first_host.proxy_owner:
            resolved = first_host.proxy_owner
            output.info(
                f"Using cached proxy owner for {first_host.ansible_host}: {resolved}"
            )
        elif context.dry_run:
            # InventoryLoadStage fills in a dummy, unreachable host for dry
            # runs -- probing it would just burn the SSH connect timeout.
            output.info("Dry run: skipping wg-manage probe, assuming caddy")
            resolved = "caddy"
        else:
            probed = self._probe(first_host)
            if probed is None:
                raise LaunchError(
                    f"Could not reach {first_host.ansible_host} to check for a "
                    "wg-manage hub. Retry once the host is reachable, or pass "
                    "an explicit --proxy caddy|wg-manage|none to skip the probe."
                )
            resolved = probed
            first_host.proxy_owner = resolved

        context.proxy = resolved
        context.skip_caddy = resolved != "caddy"

        if context.public and resolved != "wg-manage":
            raise LaunchError("--public only applies to --proxy wg-manage")

    def _probe(self, host: DeploymentHostConfig) -> str | None:
        """SSH-probe a host for `wg-manage --version`.

        Returns:
            "wg-manage" or "caddy" for a connected probe (confirmed
            present/absent, safe to cache); None if the connection itself
            failed (inconclusive -- caller fails the launch rather than
            guessing).
        """
        output.info(f"Probing {host.ansible_host} for a wg-manage hub...")
        try:
            with SSHService(host) as ssh:
                result = ssh.execute("wg-manage --version")
        except Exception as e:
            output.info(f"Probe failed: {e}")
            return None

        if result.exit_code == 0:
            output.success(f"{host.ansible_host} is a wg-manage hub")
            return "wg-manage"

        output.info("wg-manage not found on host; using slipp's caddy role")
        return "caddy"
