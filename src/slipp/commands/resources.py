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
from typing import Annotated

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
    is_wg_manage_host,
    load_first_host,
    resolve_project_name,
)
from slipp.services.providers import get_pangolin_client
from slipp.services.resources import resolve_public_target, sync_pangolin_resource

resources_app = typer.Typer(
    name="resources",
    help="Manage exposed services (wg-manage) or public Pangolin resources",
)


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
# wrappers; errors propagate to the top-level SlippError handler.


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
    return host if is_wg_manage_host(host) else None


def _list_wg_manage(host: DeploymentHostConfig) -> None:
    """List wg-manage services on `host` (all of them, not just this project's)."""
    services = wg_manage.fetch_services(host)

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
        local_config = LocalConfigService.load(project_root)
        wg_manage.sync(
            dirs,
            project_name,
            wg_host,
            expose=local_config.expose if local_config else None,
            dry_run=dry_run,
        )
        return

    if not site:
        output.error("--site is required for Pangolin sync")
        raise typer.Exit(1)

    app_domain, ip, port, method = resolve_public_target(project_root)

    output.info(f"Syncing Pangolin resource for {app_domain} -> {ip}:{port}")

    sync_pangolin_resource(
        get_pangolin_client(),
        project_name=project_name,
        app_domain=app_domain,
        ip=ip,
        port=port,
        method=method,
        site=site,
        dry_run=dry_run,
    )

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

    resources = get_pangolin_client().list_resources()

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
        # remove_service refuses entries not labeled to this project.
        wg_manage.remove_service(wg_host, resolve_project_name(), name)
        output.success(f"Removed wg-manage service: {name}")
        return

    client = get_pangolin_client()
    match = next((r for r in client.list_resources() if r.get("name") == name), None)
    if not match:
        output.error(f"Resource '{name}' not found")
        raise typer.Exit(1)

    client.delete_resource(match["resourceId"])
    output.success(f"Removed Pangolin resource: {match.get('fullDomain')}")
