"""Out-of-band server operations - slipp server reboot/status."""

from typing import Annotated, Any

import typer

from slipp import output
from slipp.services.providers.gigahost import GigahostClient
from slipp.services.providers import get_gigahost_client
from slipp.utils.errors import ProviderError

VALID_ACTIONS = ["reboot", "status"]


def _resolve_server_id(client: GigahostClient, name_or_ip: str) -> tuple[int, str]:
    """Resolve a server by name or primary IP.

    Returns:
        (srv_id, display_name)

    Raises:
        ProviderError: If no server matches.
    """
    servers: list[dict[str, Any]] = client.list_servers()
    for s in servers:
        display = s.get("srv_name") or s.get("srv_hostname") or ""
        if display == name_or_ip or s.get("srv_primary_ip") == name_or_ip:
            return s["srv_id"], display or name_or_ip

    raise ProviderError(f"No server found matching '{name_or_ip}'")


def server_command(
    action: Annotated[str, typer.Argument(help="Action: reboot or status")],
    name_or_ip: Annotated[str, typer.Argument(help="Server name or IP address")],
) -> None:
    """Reboot or check power status of a server via the provider API."""
    if action not in VALID_ACTIONS:
        output.error(
            f"Unknown action '{action}' (expected: {', '.join(VALID_ACTIONS)})"
        )
        raise typer.Exit(1)

    try:
        client = get_gigahost_client()
        srv_id, display = _resolve_server_id(client, name_or_ip)

        if action == "status":
            powered_on = client.get_powerstate(srv_id)
            output.kv("power", "on" if powered_on else "off")
            return

        if not typer.confirm(f"Reboot '{display}'?", default=False):
            output.info("Cancelled")
            return

        client.reboot(srv_id)
        output.success(f"Reboot requested for '{display}'")
    except ProviderError as e:
        output.error(str(e))
        raise typer.Exit(1)


__all__ = ["server_command"]
