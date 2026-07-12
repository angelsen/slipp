"""Shared frontend/backend classification for multi-service routing.

Single source of truth for slipp's routing convention: Node frameworks
serve as the frontend, Python as the backend. Both routing consumers --
build_caddy_sites() (launch/stages/caddy.py) and build_wg_services()
(services/wg_manage) -- classify through here, so the convention can
never drift between Caddy and wg-manage deploys.
"""

from dataclasses import dataclass

from slipp.models.deployment import DetectedService
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
