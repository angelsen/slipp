"""DNS record management commands - slipp dns sync/list."""

from typing import Annotated

import typer

from slipp import output
from slipp.services.config import LocalConfigService, load_first_host_strict
from slipp.services.providers import resolve_dns_provider, sync_dns
from slipp.utils.errors import ConfigError, ProviderError

dns_app = typer.Typer(
    name="dns",
    help="DNS record management",
)


@dns_app.command(name="sync")
def dns_sync_command() -> None:
    """Converge DNS A record from inventory to the configured provider."""
    project_root = LocalConfigService.resolve_root()

    try:
        domain, host = load_first_host_strict(project_root)
        ip = host.ansible_host
    except ConfigError as e:
        output.error(str(e))
        raise typer.Exit(1)

    output.info(f"Syncing DNS for {domain} -> {ip}")

    try:
        provider = resolve_dns_provider(domain)
        changes = sync_dns(provider, domain, ip)
    except ProviderError as e:
        output.error(str(e))
        raise typer.Exit(1)

    if changes:
        for change in changes:
            output.success(change)
    else:
        output.info("DNS already up to date")


@dns_app.command(name="list")
def dns_list_command(
    domain: Annotated[str, typer.Argument(help="Domain to list records for")],
) -> None:
    """List current DNS records for a domain."""
    try:
        provider = resolve_dns_provider(domain)
        zone = provider.find_zone(domain)
        if zone is None:
            output.error(f"No zone found for {domain}")
            raise typer.Exit(1)
        records = provider.list_records(zone.zone_id)
    except ProviderError as e:
        output.error(str(e))
        raise typer.Exit(1)

    if not records:
        output.info("No records found")
        return

    output.table(
        [
            {"name": r.name, "type": r.type, "value": r.value, "ttl": r.ttl}
            for r in records
        ]
    )
