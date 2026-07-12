"""Exposed-service management - slipp resources sync/list/remove.

Two backends, dispatched on the project's inventory `proxy_owner` host var:

- `wg-manage`: the project's host is a wg-manage hub. `sync` converges
  wg-manage's service registry against this project's declared services,
  removing stray entries a rename/removal left behind (adds/updates are
  the wg-manage-exposure Ansible role's job, at deploy time -- this only
  prunes). `list`/`remove` are thin SSH wrappers around
  `wg-manage service list`/`rm`, scoped by the `slipp:<project_name>`
  label wg-manage-exposure stamps on everything it adds.
- Otherwise: public Pangolin resource management. `sync` auto-resolves
  domain/target from the current project's inventory, mirroring `dns.py`'s
  `sync` -- a public Pangolin Resource+Target is a different kind of
  "external routing" than a DNS record, but the same
  converge-from-declared-config shape applies.
"""

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from slipp import output
from slipp.commands.common import (
    DryRunOption,
    resolve_declared_dirs,
    resolve_project_dirs,
)
from slipp.constants import OutputFormat
from slipp.models.deployment import DeploymentHostConfig
from slipp.services import wg_manage
from slipp.services.config import (
    LocalConfigService,
    load_first_host,
    load_first_host_strict,
    resolve_project_name,
)
from slipp.services.providers import get_pangolin_client
from slipp.services.providers.pangolin import resolve_site
from slipp.utils.errors import ConfigError, ProviderError, WgManageError

resources_app = typer.Typer(
    name="resources",
    help="Manage exposed services (wg-manage) or public Pangolin resources",
)


def _target_from_project(project_root: Path) -> tuple[str, str, int, str]:
    """Resolve (app_domain, ip, port, method) for this project's public resource.

    Reads the raw inventory file (via load_first_host_strict) so the custom
    app_domain host var survives, extended with the same has-its-own-Caddy
    port/method logic deploy.py's post-deploy hint already uses.

    Raises:
        ConfigError: If no inventory/host/app_domain is configured.
    """
    app_domain, host = load_first_host_strict(project_root)

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

    return app_domain, host.ansible_host, port, method


# === wg-manage backend ===
#
# Active whenever the project's inventory host has proxy_owner: wg-manage
# (see services/launch/stages/proxy.py's ProxyResolutionStage). Every
# entry wg-manage-exposure adds carries a "slipp:<project_name>" label
# (services/launch/stages/wg_manage.py) -- that label is the sole
# attribution mechanism: sync/remove only ever touch entries carrying this
# project's exact label, never unlabeled or foreign-labeled entries.
#
# The SSH orchestration and converge logic itself lives in
# services/wg_manage.py -- these are thin args -> service -> output
# wrappers, converting WgManageError into typer.Exit like every other
# command in this file already does for ConfigError/ProviderError.


def _wg_manage_host_for_cwd(root: Path | None = None) -> DeploymentHostConfig | None:
    """Best-effort: the current project's host, if it's a wg-manage hub.

    None whenever there's no project here, no inventory, or the host isn't
    a wg-manage hub -- callers fall back to the (unscoped, project-free)
    Pangolin behavior in that case.

    Args:
        root: Project root, if already resolved (e.g. sync_resource, which
            needs it for other things too) -- avoids a second
            resolve_root() filesystem walk. Defaults to resolving from cwd.
    """
    host = load_first_host(root or LocalConfigService.resolve_root())
    return host if host and host.proxy_owner == "wg-manage" else None


def _list_wg_manage(host: DeploymentHostConfig) -> None:
    """List wg-manage services on `host` (all of them, not just this project's)."""
    try:
        services = wg_manage.fetch_services(host)
    except WgManageError as e:
        output.error(str(e))
        raise typer.Exit(1)

    if output.get_output_format() == OutputFormat.json:
        output.stdout(json.dumps(services, indent=2))
        return

    if not services:
        output.info("No wg-manage services found")
        return

    output.table(
        [
            {
                "name": s.get("name"),
                "target": s.get("target"),
                "label": s.get("label") or "-",
            }
            for s in services
        ]
    )


def _remove_wg_manage(host: DeploymentHostConfig, project_name: str, name: str) -> None:
    """Remove a wg-manage service, refusing if it isn't labeled to this project."""
    try:
        wg_manage.remove_service(host, project_name, name)
    except WgManageError as e:
        output.error(str(e))
        raise typer.Exit(1)

    output.success(f"Removed wg-manage service: {name}")


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
        str | None,
        typer.Option(
            "--site",
            help="Pangolin site name, niceId, or siteId (Pangolin projects only)",
        ),
    ] = None,
    dry_run: DryRunOption = False,
) -> None:
    """Converge this project's exposed services (wg-manage strays, or a Pangolin resource+target)."""
    project_root = LocalConfigService.resolve_root()
    project_name = resolve_project_name()

    wg_host = _wg_manage_host_for_cwd(project_root)
    if wg_host:
        if site:
            output.hint("--site is ignored for wg-manage sync (Pangolin projects only)")
        dirs, _ = resolve_project_dirs(
            resolve_declared_dirs(project_root), root=project_root
        )
        try:
            wg_manage.sync(dirs, project_name, wg_host, dry_run=dry_run)
        except WgManageError as e:
            output.error(str(e))
            raise typer.Exit(1)
        return

    if not site:
        output.error("--site is required for Pangolin sync")
        raise typer.Exit(1)

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
            if dry_run:
                output.warning(f"Would create Pangolin resource: {app_domain}")
            else:
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
        # same sites.name column siteId would resolve to. No resource yet
        # (dry-run, nothing created above) means no target either.
        has_target = resource is not None and any(
            t.get("siteName") == site_match.get("name")
            and t.get("ip") == ip
            and t.get("port") == port
            for t in resource.get("targets", [])
        )
        if has_target:
            output.info(f"Target already present: {ip}:{port}")
        elif dry_run:
            output.warning(f"Would add target: {ip}:{port} ({method})")
        else:
            # dry_run is False here, so the `if not resource` branch above
            # always created one -- resource can't still be None.
            assert resource is not None
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
    """List exposed services: wg-manage services (if this project is on a hub) or public Pangolin resources."""
    wg_host = _wg_manage_host_for_cwd()
    if wg_host:
        _list_wg_manage(wg_host)
        return

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
    name: Annotated[str, typer.Argument(help="Resource/service name")],
) -> None:
    """Remove an exposed service: a wg-manage service labeled to this project, or a public Pangolin resource."""
    wg_host = _wg_manage_host_for_cwd()
    if wg_host:
        _remove_wg_manage(wg_host, resolve_project_name(), name)
        return

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
