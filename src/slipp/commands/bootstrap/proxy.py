"""Setup dev proxy infrastructure for reverse tunneling.

Configures Caddy reverse proxy on a remote host to enable local development
with remote services via slipp run --tunnel-out.
"""

from typing import Annotated

import typer

from slipp import output
from slipp.models.host import AnsibleHost
from slipp.services.config import HostResolver
from slipp.services.run import CaddyProxy
from slipp.services.ssh import hint_ssh_log
from slipp.utils.errors import (
    CaddyProxyError,
    HostNotFoundError,
    SSHAuthenticationError,
    SSHConnectionError,
)


def proxy_command(
    host: Annotated[str, typer.Argument(help="Host name or registered project")],
    email: Annotated[
        str, typer.Option("--email", "-e", help="Email for Let's Encrypt certificates")
    ],
    fallback_port: Annotated[
        int,
        typer.Option(
            "--fallback-port",
            "-p",
            help="Port where existing service listens for HTTPS",
        ),
    ] = 9443,
) -> None:
    """Setup dev proxy infrastructure for slipp run --tunnel-out."""
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
    output.info(f"Setting up dev proxy on {ansible_host.ansible_host}...")
    output.blank()

    with CaddyProxy(
        ansible_host, acme_email=email, fallback_port=fallback_port
    ) as proxy:
        output.info("1. Checking port 443...")
        try:
            port_free = proxy.is_port_443_free()
        except (SSHConnectionError, SSHAuthenticationError) as e:
            output.error(f"Could not reach {ansible_host.ansible_host}: {e}")
            raise typer.Exit(1)
        if not port_free:
            output.error("Port 443 in use")
            output.blank()
            output.hint("Free port 443 and retry")
            raise typer.Exit(1)
        output.success("Port 443 available")

        output.info("2. Installing Caddy dev proxy...")
        try:
            proxy.ensure_installed()
        except (CaddyProxyError, SSHConnectionError, SSHAuthenticationError) as e:
            output.error(f"Installation failed: {e}")
            hint_ssh_log()
            raise typer.Exit(1)

    output.blank()
    output.success("Dev proxy ready!")
    output.hint(f"Now use: slipp run <profile> --tunnel-out <port>:<domain>@{host}")
