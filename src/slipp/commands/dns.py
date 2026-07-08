"""DNS record management commands - slipp dns sync/list."""

from pathlib import Path
from typing import Annotated

import typer
import yaml

from slipp import output
from slipp.models.deployment import InventoryConfig
from slipp.services.config import LocalConfigService
from slipp.services.providers import resolve_dns_provider, sync_dns
from slipp.utils.errors import ConfigError, ProviderError

dns_app = typer.Typer(
    name="dns",
    help="DNS record management",
)


def _domain_and_ip_from_project(project_root: Path) -> tuple[str, str]:
    """Resolve the app domain + current IP straight from slipp.yaml/inventory.yml.

    Reads the raw inventory file (not the ansible-inventory-normalized form,
    which deliberately drops app_domain) so the custom app_domain host var
    survives.

    Raises:
        ConfigError: If no inventory/host/app_domain is configured.
    """
    local_config = LocalConfigService.load(project_root)
    if not local_config or not local_config.inventory:
        raise ConfigError(f"No inventory configured in {project_root}")

    inventory_path = project_root / local_config.inventory
    if not inventory_path.exists():
        raise ConfigError(f"Inventory not found: {inventory_path}")

    data = yaml.safe_load(inventory_path.read_text()) or {}
    inventory = InventoryConfig.from_ansible_format(data)

    if not inventory.hosts:
        raise ConfigError(f"No hosts found in inventory: {inventory_path}")

    host = inventory.first_host
    if not host.app_domain:
        raise ConfigError(
            f"No app_domain configured on inventory host '{host.inventory_hostname}'"
        )

    return host.app_domain, host.ansible_host


@dns_app.command(name="sync")
def dns_sync_command() -> None:
    """Converge DNS A record from inventory to the configured provider."""
    project_root = LocalConfigService.resolve_root()

    try:
        domain, ip = _domain_and_ip_from_project(project_root)
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
