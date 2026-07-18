"""Per-service port/bind-address resolution and same-host collision detection."""

from slipp.constants import ProxyType
from slipp.models.local_config import resolve_service_host
from slipp.models.service import Runtime
from slipp.services.launch.context import FullContext
from slipp.services.launch.stages.common import load_declared_expose, require
from slipp.utils.errors import LaunchError

# Ansible-side expression, not a slipp-side one -- embedded verbatim into a
# service's bind_ip (see PortResolutionStage), Jinja does not recursively
# re-render a variable's own string value, so this reaches the generated
# systemd unit as literal text for Ansible's own template pass to resolve
# at deploy time (see roles/app-container/tasks/main.yml.j2's discovery
# task, which registers _wg_bind_ip_result).
LIVE_WG_BIND_IP = "{{ _wg_bind_ip_result.stdout }}"


class PortResolutionStage:
    """Resolve each service's host-facing port and bind address.

    ## Ports

    Fails loud on any remaining same-host collision after
    `expose.<service>.port` overrides are applied. The scanner assigns one
    fixed default port per language (8080 for Python, 3000 for Node) --
    two services of the same family on the same host would otherwise
    silently try to bind the identical host port.

    Matches this project's standing "fail loud on identity/location
    conflicts" precedent: never silently reassign a port the user didn't
    ask for -- point at the one existing remediation path
    (expose.<service>.port, mirroring expose.<service>.host) and stop.

    The host-facing port is *not* always the same as DetectedService.port:
    for a container runtime, the Dockerfile's own CMD is fetched verbatim
    from the upstream flyctl template and hardcodes its listening port
    (e.g. Flask's "flask run --port=8080" has no template variable slot
    for it) -- so DetectedService.port must stay untouched (it's what the
    container actually listens on internally, unrelated to any override).
    Only the *host*-side publish port and the Caddy/wg-manage proxy target
    vary; that resolved value is exposed via context.host_ports for
    downstream stages to read (AppRolesStage, ComposeGenerationStage,
    CaddyConfigStage, WgManageRoleStage). For a systemd runtime there's no
    container layer -- the process's own listening port IS the host-facing
    port (the systemd unit already sets Environment=PORT={{ service.port
    }}), so an override there applies directly to DetectedService.port.

    ## Bind addresses

    A container runtime's default `-p PORT:PORT` publishes on `0.0.0.0` --
    reachable from the raw internet, completely bypassing whatever `ufw`
    rule was meant to scope it (Docker/rootful Podman both manage their
    own NAT rules ahead of the firewall's own INPUT chain -- confirmed
    live 2026-07-18: a WireGuard peer's `ufw` rule correctly scoped to the
    hub's tunnel IP had zero effect on reachability from the raw public
    IP). context.bind_ips resolves the one address each service's
    published port should actually listen on:
    - `--proxy none`: "0.0.0.0" -- public reachability is the intent.
    - A service on the primary host, fronted by a proxy: "127.0.0.1" --
      Caddy/wg-manage's own Caddy is always on the same machine.
    - A service on a wg-manage secondary host: not knowable at launch
      time (the peer may not even be bootstrapped yet, and its tunnel IP
      shouldn't be baked into a static file regardless) -- resolved to
      the literal Ansible expression text `{{ _wg_bind_ip_result.stdout
      }}` instead, read live off the peer's own WireGuard interface by a
      task AppRolesStage emits before the container is deployed.

    Runs after InventoryLoadStage (host runtimes known) and
    InventoryValidationStage (expose.<service>.host already validated),
    before any stage that consumes context.services[*].port,
    context.host_ports, or context.bind_ips for file generation.
    """

    def execute(self, context: FullContext) -> None:
        """Resolve host_ports/bind_ips, applying overrides and failing on collisions.

        Args:
            context: Launch context with inventory_config and services
                already populated.

        Raises:
            LaunchError: If two services assigned to the same host still
                share a host-facing port after overrides are applied.
        """
        inventory_config = require(context.inventory_config, "inventory config")
        primary_name = inventory_config.primary_host.inventory_hostname
        declared_expose = load_declared_expose(context) or {}

        host_ports: dict[str, int] = {}
        bind_ips: dict[str, str] = {}
        for i, service in enumerate(context.services):
            host_name = resolve_service_host(
                service.name, declared_expose, primary_name
            )
            runtime = inventory_config.hosts[host_name].runtime

            entry = declared_expose.get(service.name)
            override = entry.port if entry and entry.port is not None else None
            resolved = override if override is not None else service.port

            if runtime == Runtime.SYSTEMD:
                # No container layer -- the unit's own Environment=PORT
                # already reads DetectedService.port directly.
                if resolved != service.port:
                    context.services[i] = service.model_copy(update={"port": resolved})
            host_ports[service.name] = resolved

            if context.proxy == ProxyType.none:
                bind_ips[service.name] = "0.0.0.0"
            elif host_name == primary_name:
                bind_ips[service.name] = "127.0.0.1"
            else:
                bind_ips[service.name] = LIVE_WG_BIND_IP

        claimed_by_host: dict[str, dict[int, str]] = {}
        for service in context.services:
            host_name = resolve_service_host(
                service.name, declared_expose, primary_name
            )
            claimed = claimed_by_host.setdefault(host_name, {})
            port = host_ports[service.name]
            if port in claimed:
                other = claimed[port]
                raise LaunchError(
                    f"'{other}' and '{service.name}' would both bind port "
                    f"{port} on host '{host_name}' -- set "
                    f"expose.{service.name}.port (or expose.{other}.port) to "
                    "a free port in slipp.yaml, then re-run with --reconfigure"
                )
            claimed[port] = service.name

        context.host_ports = host_ports
        context.bind_ips = bind_ips

        # --proxy none shows primary_host.app_port in the final URL --
        # keep it in sync with any resolved override on the primary
        # (index-0) service, the one field it's defined to track.
        if context.services:
            primary_host = inventory_config.primary_host
            primary_host.app_port = host_ports[context.services[0].name]
