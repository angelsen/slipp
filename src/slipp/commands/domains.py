"""Domain management commands - slipp domains check/register/list."""

from typing import Annotated

import typer

from slipp import output
from slipp.services.providers import (
    get_gigahost_client,
    register_domain_interactive,
)
from slipp.utils.errors import DomainRegistrationError, ProviderError

domains_app = typer.Typer(
    name="domains",
    help="Domain availability, registration, and listing",
)


@domains_app.command(name="check")
def check_domain(
    domain: Annotated[str, typer.Argument(help="Domain to check (.no only)")],
) -> None:
    """Check .no domain availability."""
    try:
        client = get_gigahost_client()
        available, reason = client.check_domain(domain)
    except ProviderError as e:
        output.error(str(e))
        raise typer.Exit(1)

    if available:
        output.success(f"{domain} is available")
    else:
        output.warning(f"{domain} is not available" + (f": {reason}" if reason else ""))


@domains_app.command(name="register")
def register_domain(
    domain: Annotated[str, typer.Argument(help="Domain to register (.no only)")],
) -> None:
    """Register a .no domain (prompts for registrant info)."""
    try:
        client = get_gigahost_client()
        available, reason = client.check_domain(domain)
    except ProviderError as e:
        output.error(str(e))
        raise typer.Exit(1)

    if not available:
        output.error(f"{domain} is not available" + (f": {reason}" if reason else ""))
        raise typer.Exit(1)

    output.info(f"{domain} is available")

    try:
        result = register_domain_interactive(client, domain)
    except DomainRegistrationError as e:
        output.error(str(e))
        raise typer.Exit(1)

    output.success(f"Registered {domain}")
    output.kv("zone_id", result.get("zone_id"), indent=1)
    output.kv("status", result.get("status"), indent=1)


@domains_app.command(name="list")
def list_domains() -> None:
    """List domains across configured providers."""
    try:
        client = get_gigahost_client()
        zones = client.list_zones()
    except ProviderError as e:
        output.error(str(e))
        raise typer.Exit(1)

    if not zones:
        output.info("No domains found")
        return

    output.table([{"domain": z.name, "records": z.record_count} for z in zones])
