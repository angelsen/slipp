"""DNS record management commands - slipp dns sync/list."""

from typing import Annotated

import typer

from slipp import output
from slipp.services.config import LocalConfigService, load_primary_host_strict
from slipp.services.providers import (
    DNSProvider,
    get_gigahost_client,
    sync_dns,
)
from slipp.utils.errors import ProviderError

dns_app = typer.Typer(
    name="dns",
    help="DNS record management",
)


def sync_and_report(provider: DNSProvider, domain: str, ip: str) -> None:
    """Converge DNS for domain -> ip and print the resulting changes.

    Shared by `slipp dns sync` and `slipp up` so the converge behavior
    (including zone creation) and its reporting can't drift.
    """
    try:
        changes = sync_dns(provider, domain, ip)
    except ProviderError as e:
        output.error(f"DNS sync failed: {e}")
        raise typer.Exit(1)

    if changes:
        for change in changes:
            output.success(change)
    else:
        output.info("DNS already up to date")


@dns_app.command(name="sync")
def dns_sync_command() -> None:
    """Converge DNS zone + A record from inventory to the configured provider."""
    project_root = LocalConfigService.resolve_root()

    domain, host = load_primary_host_strict(project_root)
    ip = host.ansible_host

    output.info(f"Syncing DNS for {domain} -> {ip}")
    with get_gigahost_client() as client:
        sync_and_report(client, domain, ip)


@dns_app.command(name="list")
def dns_list_command(
    domain: Annotated[str, typer.Argument(help="Domain to list records for")],
) -> None:
    """List current DNS records for a domain."""
    with get_gigahost_client() as provider:
        zone = provider.find_zone(domain)
        if zone is None:
            output.error(f"No zone found for {domain}")
            raise typer.Exit(1)
        records = provider.list_records(zone.zone_id)

    output.empty_or_table(
        [
            {"name": r.name, "type": r.type, "value": r.value, "ttl": r.ttl}
            for r in records
        ],
        "No records found",
    )
