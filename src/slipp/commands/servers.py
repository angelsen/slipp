"""Out-of-band server listing - slipp servers list."""

import typer

from slipp import output
from slipp.services.providers import get_gigahost_client

servers_app = typer.Typer(
    name="servers",
    help="List servers across configured providers",
)


@servers_app.command(name="list")
def list_servers() -> None:
    """List VPS servers across configured providers (no SSH needed)."""
    client = get_gigahost_client()
    servers = client.list_servers()

    if not servers:
        output.info("No servers found")
        return

    rows = [
        {
            "name": s.get("srv_name") or s.get("srv_hostname") or "-",
            "ip": s.get("srv_primary_ip") or "-",
            "cores": s.get("srv_cores", "-"),
            "ram": s.get("srv_ram", "-"),
            "os": (s.get("os") or {}).get("os_name", "-"),
            "power": "on" if s.get("srv_status") else "off",
            "location": s.get("srv_location", "-"),
        }
        for s in servers
    ]

    output.table(rows)
