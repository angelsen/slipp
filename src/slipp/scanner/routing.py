"""Shared frontend/backend routing convention for multi-service deploys.

Single source of truth for slipp's routing convention: Node frameworks
serve as the frontend, Python as the backend. Both routing consumers --
build_caddy_sites() (launch/stages/caddy.py) and build_wg_services()
(services/wg_manage) -- seed and validate their expose: blocks through
default_expose()/validate_expose() here, so the convention can never
drift between Caddy and wg-manage deploys.
"""

from slipp.models.deployment import DetectedService
from slipp.models.local_config import ExposeEntry
from slipp.scanner.models import NODE_FRAMEWORKS, PYTHON_FRAMEWORKS


def validate_expose(
    expose: dict[str, ExposeEntry], services: list[DetectedService]
) -> None:
    """Validate an expose: block against the detected services.

    Shared by both proxy translators (build_caddy_sites, build_wg_services)
    so a hand-edited block that one proxy can't serve fails identically
    under the other, instead of silently routing differently -- the drift
    this module exists to prevent. Callers wrap ValueError in their own
    error type (LaunchError / WgManageError).

    Raises:
        ValueError: On an unknown service name, two services claiming the
            same domain+path, or a domain with path entries but no "/"
            service (unservable by wg-manage; silently misrouted by the
            Caddy site template).
    """
    known = {s.name for s in services}
    claims: dict[tuple[str, str], str] = {}
    roots: dict[str, bool] = {}
    for name, entry in expose.items():
        if name not in known:
            raise ValueError(
                f"expose: references unknown service '{name}' "
                f"(detected: {', '.join(sorted(known))})"
            )
        claim = (entry.domain, entry.path)
        if claim in claims:
            raise ValueError(
                f"expose: '{name}' and '{claims[claim]}' both claim "
                f"{entry.domain} at '{entry.path}'"
            )
        claims[claim] = name
        roots.setdefault(entry.domain, False)
        if entry.path == "/":
            roots[entry.domain] = True

    for domain, has_root in roots.items():
        if not has_root:
            raise ValueError(
                f"expose: no '/' service on '{domain}' -- every domain "
                "needs a root entry (path routes attach to it)"
            )


def default_expose(
    services: list[DetectedService], domain: str
) -> dict[str, ExposeEntry]:
    """Seed the expose: routing block from the default convention.

    The primary service (frontend if present, else the backend) gets the
    bare domain at "/". The backend gets "/api" on that domain only when
    a frontend occupies "/" -- with no frontend, the backend *is* the app
    and stays at the root, so adding a worker service never relocates
    the app's public URL. Everything else gets a {name}.{domain}
    subdomain.
    """
    if len(services) == 1:
        return {services[0].name: ExposeEntry(domain=domain)}

    frontend = next((s for s in services if s.framework in NODE_FRAMEWORKS), None)
    backend = next((s for s in services if s.framework in PYTHON_FRAMEWORKS), None)
    primary = frontend or backend
    assert primary is not None  # framework sets are exhaustive (scanner/models.py)

    expose = {primary.name: ExposeEntry(domain=domain)}
    if frontend and backend:
        expose[backend.name] = ExposeEntry(domain=domain, path="/api")

    for service in services:
        if service.name not in expose:
            expose[service.name] = ExposeEntry(domain=f"{service.name}.{domain}")

    return expose


def ip_expose(
    services: list[DetectedService], site: str
) -> tuple[dict[str, ExposeEntry], list[DetectedService]]:
    """Routing for a domainless (IP) deploy, e.g. site=":80".

    The primary service (and a backend at "/api") route on the bare site;
    there are no subdomains to mint, so every service that would get one
    is returned as unroutable for the caller to warn about.
    """
    expose = default_expose(services, site)
    routable = {name: e for name, e in expose.items() if e.domain == site}
    skipped = [s for s in services if s.name not in routable]
    return routable, skipped
