"""Per-service port override application and same-host collision detection."""

from slipp.models.local_config import resolve_service_host
from slipp.models.service import Runtime
from slipp.services.launch.context import FullContext
from slipp.services.launch.stages.common import load_declared_expose, require
from slipp.utils.errors import LaunchError


class PortResolutionStage:
    """Resolve each service's host-facing port; fail loud on any remaining collision.

    The scanner assigns one fixed default port per language (8080 for
    Python, 3000 for Node) -- two services of the same family on the same
    host would otherwise silently try to bind the identical host port.

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

    Runs after InventoryLoadStage (host runtimes known) and
    InventoryValidationStage (expose.<service>.host already validated),
    before any stage that consumes context.services[*].port or
    context.host_ports for file generation.
    """

    def execute(self, context: FullContext) -> None:
        """Resolve host_ports, applying overrides and failing on collisions.

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

        # --proxy none shows primary_host.app_port in the final URL --
        # keep it in sync with any resolved override on the primary
        # (index-0) service, the one field it's defined to track.
        if context.services:
            primary_host = inventory_config.primary_host
            primary_host.app_port = host_ports[context.services[0].name]
