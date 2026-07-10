"""Public Pangolin resource management - slipp resources sync/list/remove.

`sync` auto-resolves domain/target from the current project's inventory,
mirroring `dns.py`'s `sync` -- a public Pangolin Resource+Target is a
different kind of "external routing" than a DNS record, but the same
converge-from-declared-config shape applies.
"""

import json
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from slipp import output
from slipp.constants import OutputFormat
from slipp.models.deployment import InventoryConfig
from slipp.services.config import LocalConfigService, resolve_project_name
from slipp.services.providers import get_pangolin_client
from slipp.services.providers.pangolin import resolve_site
from slipp.utils.errors import ConfigError, ProviderError

resources_app = typer.Typer(
    name="resources",
    help="Manage public Pangolin resources",
)


def _target_from_project(project_root: Path) -> tuple[str, str, int, str]:
    """Resolve (app_domain, ip, port, method) for this project's public resource.

    Mirrors dns.py's _domain_and_ip_from_project (reads the raw inventory
    file so the custom app_domain host var survives), extended with the
    same has-its-own-Caddy port/method logic deploy.py's post-deploy hint
    already uses.

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

    has_caddy = (project_root / "roles" / "caddy").exists()
    if has_caddy:
        port, method = 443, "https"
    else:
        if not host.app_port:
            raise ConfigError(
                f"No app_port configured on inventory host '{host.inventory_hostname}' "
                "(required when the project has no roles/caddy)"
            )
        port, method = host.app_port, "http"

    return host.app_domain, host.ansible_host, port, method


def _resolve_domain_id(app_domain: str, domains: list[dict[str, Any]]) -> tuple[str, str]:
    """Match app_domain's suffix against a configured Pangolin domain.

    Picks the *longest* matching baseDomain, not just the first in API list
    order -- an org can have both an apex (example.com) and a subdomain
    (dev.example.com) configured as separate Pangolin domains, and the more
    specific one should win regardless of API ordering.

    Returns:
        (domain_id, subdomain) -- subdomain is "" for an apex match.

    Raises:
        ConfigError: If no configured domain's baseDomain matches.
    """
    matches = [
        d
        for d in domains
        if app_domain == d["baseDomain"] or app_domain.endswith(f".{d['baseDomain']}")
    ]
    match = max(matches, key=lambda d: len(d["baseDomain"]), default=None)
    if not match:
        available = ", ".join(d["baseDomain"] for d in domains)
        raise ConfigError(
            f"'{app_domain}' doesn't match any configured Pangolin domain"
            + (f" ({available})" if available else "")
        )

    base = match["baseDomain"]
    subdomain = app_domain[: -len(base) - 1] if app_domain != base else ""
    return match["domainId"], subdomain


@resources_app.command(name="sync")
def sync_resource(
    site: Annotated[
        str, typer.Option("--site", help="Pangolin site name, niceId, or siteId")
    ],
) -> None:
    """Converge this project's public Pangolin resource+target to match its inventory."""
    project_root = LocalConfigService.resolve_root()
    project_name = resolve_project_name()

    try:
        app_domain, ip, port, method = _target_from_project(project_root)
    except ConfigError as e:
        output.error(str(e))
        raise typer.Exit(1)

    output.info(f"Syncing Pangolin resource for {app_domain} -> {ip}:{port}")

    try:
        client = get_pangolin_client()
        site_match = resolve_site(client.list_sites(), site)
        if not site_match:
            output.error(f"Pangolin site '{site}' not found")
            raise typer.Exit(1)

        domain_id, subdomain = _resolve_domain_id(app_domain, client.list_domains())

        resource = next(
            (r for r in client.list_resources() if r.get("fullDomain") == app_domain),
            None,
        )
        if not resource:
            resource = client.create_resource(
                name=project_name, domain_id=domain_id, subdomain=subdomain or None
            )
            output.success(f"Created Pangolin resource: {app_domain}")
        else:
            output.info(f"Pangolin resource already exists: {app_domain}")

        site_id = site_match["siteId"]
        # list_resources()'s targets don't carry siteId (confirmed against
        # listResources.ts -- only targetId/ip/port/enabled/healthStatus/
        # siteName), so match on siteName instead; it's populated from the
        # same sites.name column siteId would resolve to.
        has_target = any(
            t.get("siteName") == site_match.get("name")
            and t.get("ip") == ip
            and t.get("port") == port
            for t in resource.get("targets", [])
        )
        if has_target:
            output.info(f"Target already present: {ip}:{port}")
        else:
            client.add_target(resource["resourceId"], site_id, ip, port, method=method)
            output.success(f"Added target: {ip}:{port} ({method})")
    except ProviderError as e:
        output.error(str(e))
        raise typer.Exit(1)

    output.blank()
    output.kv("resource", app_domain)
    output.kv("target", f"{ip}:{port}")
    output.hint(f"https://{app_domain}")


@resources_app.command(name="list")
def list_resources() -> None:
    """List public Pangolin resources, live from Pangolin."""
    try:
        resources = get_pangolin_client().list_resources()
    except ProviderError as e:
        output.error(str(e))
        raise typer.Exit(1)

    if not resources:
        output.info("No resources found")
        return

    if output.get_output_format() == OutputFormat.json:
        output.stdout(json.dumps(resources, indent=2))
        return

    output.table(
        [
            {
                "name": r.get("name"),
                "domain": r.get("fullDomain"),
                "targets": ", ".join(
                    f"{t.get('ip')}:{t.get('port')}" for t in r.get("targets", [])
                )
                or "-",
            }
            for r in resources
        ]
    )


@resources_app.command(name="remove")
def remove_resource(
    name: Annotated[str, typer.Argument(help="Resource name")],
) -> None:
    """Remove a public Pangolin resource (and its targets)."""
    try:
        client = get_pangolin_client()
        match = next(
            (r for r in client.list_resources() if r.get("name") == name), None
        )
        if not match:
            output.error(f"Resource '{name}' not found")
            raise typer.Exit(1)

        client.delete_resource(match["resourceId"])
        output.success(f"Removed Pangolin resource: {match.get('fullDomain')}")
    except ProviderError as e:
        output.error(str(e))
        raise typer.Exit(1)
