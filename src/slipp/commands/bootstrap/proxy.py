"""Setup dev proxy infrastructure for reverse tunneling.

Configures Caddy reverse proxy on a remote host to enable local development
with remote services via ac run --tunnel-out.
"""

import typer

from slipp import output
from slipp.models.host import AnsibleHost
from slipp.services.config import HostResolver
from slipp.services.run import CaddyProxy
from slipp.utils.errors import CaddyProxyError, HostNotFoundError


def proxy_command(
    host: str = typer.Argument(..., help="Host name or registered project"),
    email: str = typer.Option(
        ..., "--email", "-e", help="Email for Let's Encrypt certificates"
    ),
    fallback_port: int = typer.Option(
        9443,
        "--fallback-port",
        "-p",
        help="Port where existing service listens for HTTPS",
    ),
) -> None:
    """Setup dev proxy infrastructure for ac run --tunnel-out."""
    try:
        resolver = HostResolver()
        ansible_host = resolver.by_project(host)
    except HostNotFoundError:
        ansible_host = AnsibleHost(
            inventory_hostname=host,
            ansible_host=host,
            ansible_user="slipp",
        )

    output.blank()
    output.text(f"Setting up dev proxy on {ansible_host.ansible_host}...")
    output.blank()

    proxy = CaddyProxy(ansible_host, acme_email=email, fallback_port=fallback_port)

    output.info("1. Checking port 443...")
    if not proxy.is_port_443_free():
        output.error("Port 443 in use")
        output.blank()
        output.hint("Free port 443 and retry")
        raise typer.Exit(1)
    output.success("Port 443 available")

    output.info("2. Installing Caddy dev proxy...")
    try:
        proxy.ensure_installed()
    except CaddyProxyError as e:
        output.error(f"Installation failed: {e}")
        raise typer.Exit(1)

    output.blank()
    output.success("Dev proxy ready!")
    output.hint(f"Now use: ac run <profile> --tunnel-out <port>:<domain>@{host}")
