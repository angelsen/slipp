"""Domain management commands - slipp domains check/register/list."""

from typing import Annotated

import typer

from slipp import output
from slipp.services.providers import (
    get_gigahost_client,
    register_domain_interactive,
)

domains_app = typer.Typer(
    name="domains",
    help="Domain availability, registration, and listing",
)


def _not_available_message(domain: str, reason: str | None) -> str:
    """Format the "domain is not available" message, with an optional reason suffix."""
    return f"{domain} is not available" + (f": {reason}" if reason else "")


@domains_app.command(name="check")
def check_domain(
    domain: Annotated[str, typer.Argument(help="Domain to check (.no only)")],
) -> None:
    """Check .no domain availability."""
    with get_gigahost_client() as client:
        available, reason = client.check_domain(domain)

    if available:
        output.success(f"{domain} is available")
    else:
        output.warning(_not_available_message(domain, reason))


@domains_app.command(name="register")
def register_domain(
    domain: Annotated[str, typer.Argument(help="Domain to register (.no only)")],
) -> None:
    """Register a .no domain (prompts for registrant info)."""
    with get_gigahost_client() as client:
        available, reason = client.check_domain(domain)

        if not available:
            output.error(_not_available_message(domain, reason))
            raise typer.Exit(1)

        output.info(f"{domain} is available")

        result = register_domain_interactive(client, domain)

    output.success(f"Registered {domain}")
    output.kv("zone_id", result.get("zone_id"), indent=1)
    output.kv("status", result.get("status"), indent=1)


@domains_app.command(name="list")
def list_domains() -> None:
    """List domains across configured providers."""
    with get_gigahost_client() as client:
        zones = client.list_zones()

    output.empty_or_table(
        [{"domain": z.name, "records": z.record_count} for z in zones],
        "No domains found",
    )
