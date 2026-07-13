"""Shared frontend/backend classification for multi-service routing.

Single source of truth for slipp's routing convention: Node frameworks
serve as the frontend, Python as the backend. Both routing consumers --
build_caddy_sites() (launch/stages/caddy.py) and build_wg_services()
(services/wg_manage) -- classify through here, so the convention can
never drift between Caddy and wg-manage deploys.
"""

from dataclasses import dataclass

from slipp.models.deployment import DetectedService
from slipp.models.local_config import ExposeEntry
from slipp.scanner.models import NODE_FRAMEWORKS, PYTHON_FRAMEWORKS


@dataclass(frozen=True)
class ServiceRoles:
    """Routing roles for a set of detected services.

    frontend/backend are the first Node/Python-framework match (each may
    be None); others is everything else in original detection order.
    The framework sets are disjoint, so frontend is never backend.
    """

    frontend: DetectedService | None
    backend: DetectedService | None
    others: list[DetectedService]


def classify_services(services: list[DetectedService]) -> ServiceRoles:
    """Split services into frontend, backend, and the rest."""
    frontend = next((s for s in services if s.framework in NODE_FRAMEWORKS), None)
    backend = next((s for s in services if s.framework in PYTHON_FRAMEWORKS), None)
    others = [s for s in services if s is not frontend and s is not backend]
    return ServiceRoles(frontend=frontend, backend=backend, others=others)


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

    The primary service (frontend if present, else the backend -- the
    framework sets are exhaustive, so one always exists) gets the bare
    domain at "/". The backend gets "/api" on that domain only when a
    frontend occupies "/" -- with no frontend, the backend *is* the app
    and stays at the root, so adding a worker service never relocates
    the app's public URL. Everything else gets a {name}.{domain}
    subdomain.
    """
    if len(services) == 1:
        return {services[0].name: ExposeEntry(domain=domain)}

    roles = classify_services(services)
    primary = roles.frontend or roles.backend
    if primary is None:  # unreachable: every framework is Node or Python
        primary = services[0]

    expose = {primary.name: ExposeEntry(domain=domain)}
    if roles.frontend and roles.backend:
        expose[roles.backend.name] = ExposeEntry(domain=domain, path="/api")

    for service in services:
        if service is primary or service.name in expose:
            continue
        expose[service.name] = ExposeEntry(domain=f"{service.name}.{domain}")

    return expose
