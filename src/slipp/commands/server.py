"""Out-of-band server operations - slipp server status/reboot/install."""

from typing import Annotated

import typer

from slipp import output
from slipp.services.providers import get_gigahost_client
from slipp.services.providers.provision import install_server, resolve_server

server_app = typer.Typer(name="server", help="Out-of-band server operations")


@server_app.command(name="status")
def status_command(
    name_or_ip: Annotated[str, typer.Argument(help="Server name or IP address")],
) -> None:
    """Show server power state."""
    client = get_gigahost_client()
    srv_id, _display, _ip = resolve_server(client, name_or_ip)
    powered_on = client.get_powerstate(srv_id)
    output.kv("power", "on" if powered_on else "off")


@server_app.command(name="reboot")
def reboot_command(
    name_or_ip: Annotated[str, typer.Argument(help="Server name or IP address")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Reboot a server."""
    client = get_gigahost_client()
    srv_id, display, _ip = resolve_server(client, name_or_ip)

    if not force and not output.confirm(f"Reboot '{display}'?", default=False):
        output.info("Cancelled")
        return

    client.reboot(srv_id)
    output.success(f"Reboot requested for '{display}'")


@server_app.command(name="install")
def install_command(
    name_or_ip: Annotated[str, typer.Argument(help="Server name or IP address")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompts"),
    ] = False,
) -> None:
    """Reinstall server OS."""
    client = get_gigahost_client()
    install_server(client, name_or_ip, force=force)


__all__ = ["server_app"]
