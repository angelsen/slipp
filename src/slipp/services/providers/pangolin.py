"""Pangolin API client -- httpx wrapper for the public-resource endpoints slipp uses.

Auth is a stopgap: Pangolin's Bearer-token Integration API has no Traefik
route wired up on this instance yet, so we authenticate the way the
dashboard itself does -- a session cookie plus a static CSRF header
(confirmed via `server/middlewares/csrfProtection.ts`: it checks for the
literal string "x-csrf-protection", not a per-session token). Once the
Integration API is reachable, swap `_headers()` for a plain
`Authorization: Bearer <key>` header -- no call site needs to change.
"""

from typing import Any

import httpx

from slipp.services.providers.http import ApiClientMixin
from slipp.utils.errors import ConfigError


def resolve_site(sites: list[dict[str, Any]], site: str) -> dict[str, Any] | None:
    """Match a site by display name, niceId, or numeric siteId.

    Args:
        sites: Result of PangolinClient.list_sites()
        site: User-supplied identifier (e.g. a site's display name)
    """
    return next(
        (
            s
            for s in sites
            if s.get("name") == site
            or s.get("niceId") == site
            or str(s.get("siteId")) == site
        ),
        None,
    )


def resolve_domain(app_domain: str, domains: list[dict[str, Any]]) -> tuple[str, str]:
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


class PangolinClient(ApiClientMixin):
    """Synchronous Pangolin API client for sites (Newt) and public resources."""

    PROVIDER_NAME = "Pangolin"

    def __init__(self, session_cookie: str, org: str, base_url: str):
        """Initialize with a p_session_token cookie value.

        Args:
            session_cookie: Value of the p_session_token dashboard cookie.
            org: Pangolin org slug.
            base_url: API base URL.

        org/base_url have no defaults here -- PangolinConfig (models/provider.py)
        is the single source of truth for those; callers always derive them
        from a PangolinConfig instance (see get_pangolin_client() and
        commands/providers.py's _add_pangolin()).
        """
        self.org = org
        self._client = httpx.Client(
            base_url=base_url,
            headers={
                "Cookie": f"p_session_token={session_cookie}",
                "X-CSRF-Token": "x-csrf-protection",
            },
            timeout=30.0,
        )

    # --- Sites ---

    def list_sites(self) -> list[dict[str, Any]]:
        """GET /org/{org}/sites -- Newt sites in the org.

        Passes a large pageSize -- the endpoint defaults to 20 and silently
        truncates otherwise (confirmed against listSites.ts).
        """
        result = self._request(
            "GET", f"/org/{self.org}/sites", params={"pageSize": 1000}
        )
        return result.get("data", {}).get("sites", [])

    # --- Domains ---

    def list_domains(self) -> list[dict[str, Any]]:
        """GET /org/{org}/domains -- org domains. -> [{domainId, baseDomain, verified, type}]"""
        result = self._request("GET", f"/org/{self.org}/domains")
        return result.get("data", {}).get("domains", [])

    # --- Resources (public, Traefik-routed) ---

    def list_resources(self) -> list[dict[str, Any]]:
        """GET /org/{org}/resources -- public resources with their targets.

        Passes a large pageSize -- the endpoint defaults to 20 and silently
        truncates otherwise (confirmed against listResources.ts).
        """
        result = self._request(
            "GET", f"/org/{self.org}/resources", params={"pageSize": 1000}
        )
        return result.get("data", {}).get("resources", [])

    def create_resource(
        self, name: str, domain_id: str, subdomain: str | None = None
    ) -> dict[str, Any]:
        """PUT /org/{org}/resource -- create a public HTTP resource."""
        result = self._request(
            "PUT",
            f"/org/{self.org}/resource",
            json={
                "name": name,
                "http": True,
                "domainId": domain_id,
                "protocol": "tcp",
                "subdomain": subdomain,
            },
        )
        return result.get("data", {})

    def add_target(
        self, resource_id: int, site_id: int, ip: str, port: int, method: str = "http"
    ) -> dict[str, Any]:
        """PUT /resource/{id}/target -- attach a backend target to a resource."""
        result = self._request(
            "PUT",
            f"/resource/{resource_id}/target",
            json={"siteId": site_id, "ip": ip, "port": port, "method": method},
        )
        return result.get("data", {})

    def delete_resource(self, resource_id: int) -> None:
        """DELETE /resource/{id} -- cascades its targets."""
        self._request("DELETE", f"/resource/{resource_id}")
