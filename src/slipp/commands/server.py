"""Out-of-band server operations - slipp server reboot/status/install."""

from typing import Annotated

import typer

from slipp import output
from slipp.services.providers import get_gigahost_client
from slipp.services.providers.provision import install_server, resolve_server
from slipp.utils.errors import ProviderError

VALID_ACTIONS = ["reboot", "status", "install"]


def server_command(
    action: Annotated[str, typer.Argument(help="Action: status, reboot, or install")],
    name_or_ip: Annotated[str, typer.Argument(help="Server name or IP address")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompts"),
    ] = False,
) -> None:
    """Manage a server: check status, reboot, or reinstall OS."""
    if action not in VALID_ACTIONS:
        output.error(
            f"Unknown action '{action}' (expected: {', '.join(VALID_ACTIONS)})"
        )
        raise typer.Exit(1)

    try:
        client = get_gigahost_client()

        if action == "install":
            install_server(client, name_or_ip, force=force)
            return

        srv_id, display, _ip = resolve_server(client, name_or_ip)

        if action == "status":
            powered_on = client.get_powerstate(srv_id)
            output.kv("power", "on" if powered_on else "off")
            return

        if not force and not typer.confirm(f"Reboot '{display}'?", default=False):
            output.info("Cancelled")
            return

        client.reboot(srv_id)
        output.success(f"Reboot requested for '{display}'")
    except ProviderError as e:
        output.error(str(e))
        raise typer.Exit(1)


__all__ = ["server_command"]
