"""Public-resource orchestration for `slipp resources` (Pangolin backend).

Business logic behind commands/resources.py's Pangolin branch: resolving
this project's public target from its inventory, and converging a Pangolin
Resource+Target against it. The wg-manage branch's equivalent lives in
services/wg_manage; this module keeps the Pangolin side at the same
commands = args -> service -> output layering.
"""

from pathlib import Path

from slipp import output
from slipp.services.config import load_first_host_strict
from slipp.services.config.detection import has_caddy_role
from slipp.services.providers.pangolin import (
    PangolinClient,
    resolve_domain,
    resolve_site,
)
from slipp.utils.errors import ConfigError, ProviderError


def resolve_public_target(project_root: Path) -> tuple[str, str, int, str]:
    """Resolve (app_domain, ip, port, method) for this project's public resource.

    Reads the raw inventory file (via load_first_host_strict) so the custom
    app_domain host var survives, extended with the same has-its-own-Caddy
    port/method logic deploy.py's post-deploy hint already uses.

    Raises:
        ConfigError: If no inventory/host/app_domain is configured.
    """
    app_domain, host = load_first_host_strict(project_root)

    if has_caddy_role(project_root):
        port, method = 443, "https"
    else:
        if not host.app_port:
            raise ConfigError(
                f"No app_port configured on inventory host '{host.inventory_hostname}' "
                "(required when the project has no roles/caddy)"
            )
        port, method = host.app_port, "http"

    return app_domain, host.ansible_host, port, method


def find_resource(
    resources: list[dict], *, name: str | None = None, full_domain: str | None = None
) -> dict | None:
    """Find a Pangolin resource by name or fullDomain from a list_resources() result."""
    return next(
        (
            r
            for r in resources
            if (name is not None and r.get("name") == name)
            or (full_domain is not None and r.get("fullDomain") == full_domain)
        ),
        None,
    )


def sync_pangolin_resource(
    client: PangolinClient,
    *,
    project_name: str,
    app_domain: str,
    ip: str,
    port: int,
    method: str,
    site: str,
    dry_run: bool,
) -> None:
    """Converge a Pangolin Resource+Target for app_domain -> ip:port.

    Find-or-create the resource on app_domain, then find-or-add the
    ip:port target on `site`, honoring dry_run throughout.

    Raises:
        ProviderError: On API failures or if `site` doesn't resolve.
        ConfigError: If app_domain matches no configured Pangolin domain.
    """
    site_match = resolve_site(client.list_sites(), site)
    if not site_match:
        raise ProviderError(f"Pangolin site '{site}' not found")

    domain_id, subdomain = resolve_domain(app_domain, client.list_domains())

    resource = find_resource(client.list_resources(), full_domain=app_domain)
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
    # str()-normalize port: matched against unverified API JSON, and a
    # string/int mismatch there would make this always-False, silently
    # re-adding a duplicate target on every sync instead of recognizing
    # the one already present. NOTE: `method` is deliberately NOT compared
    # here -- list_resources()'s targets don't carry it at all (confirmed
    # against listResources.ts: only targetId/ip/port/enabled/healthStatus/
    # siteName), so comparing it would always be `None == method`, always
    # False, and re-add a target on every single sync instead of fixing
    # anything. A stale wrong-method target is a real gap this can't catch
    # from the read side; it isn't something this fix can safely close.
    has_target = resource is not None and any(
        t.get("siteName") == site_match.get("name")
        and t.get("ip") == ip
        and str(t.get("port")) == str(port)
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
