"""Cross-project host-sharing visibility.

Slipp already treats a physical host serving multiple projects as a
first-class supported pattern (`services/discovery/pipeline.py` explicitly
dedupes SSH discovery by `ansible_host` for exactly this reason) -- real
examples include two independent apps sharing one production VPS, or a
throwaway VPS reused across several smoke-test fixtures. So sharing an IP
is never itself an error. What's missing is visibility: `slipp provision`
auto-registering a project for a host that's *already* claimed elsewhere
can be a genuine mistake (found live 2026-07-17, worked around by hand) --
this module surfaces that at registration time so a human notices
immediately, without ever blocking a deliberate shared deploy.
"""

from pathlib import Path

from slipp.services.config.inventory import load_project_ansible_hosts
from slipp.services.registry.projects import ProjectRegistry
from slipp.utils.errors import ConfigError, HostNotFoundError


def find_shared_hosts(
    own_project_path: Path, own_ips: set[str]
) -> dict[str, list[str]]:
    """ansible_host -> [other project names] for any of `own_ips` already
    claimed by a *different* registered project.

    Excludes the caller's own project by path (not name), so this works
    whether or not the project is registered under a name yet -- and
    whether or not the name matches (e.g. re-registration under a renamed
    slipp.yaml). Best-effort: an unloadable peer inventory contributes
    nothing rather than raising -- a broken peer must not block
    registering a healthy project.

    Args:
        own_project_path: Root directory of the project being registered
            or modified -- excluded from the scan.
        own_ips: The `ansible_host` values to check for overlap.

    Returns:
        Empty dict if no overlap found (the common case).
    """
    if not own_ips:
        return {}

    resolved_self = own_project_path.resolve()
    shared: dict[str, list[str]] = {}
    for peer in ProjectRegistry().list_all():
        if peer.project_path == resolved_self:
            continue
        try:
            peer_hosts = load_project_ansible_hosts(peer.project_path)
        except (ConfigError, HostNotFoundError):
            continue
        for host in peer_hosts:
            if host.ansible_host in own_ips:
                shared.setdefault(host.ansible_host, []).append(peer.name)

    return shared


def describe_shared_hosts(shared: dict[str, list[str]]) -> list[str]:
    """Render find_shared_hosts()'s result as one human-readable line per host."""
    return [
        f"Host '{ip}' is also used by project(s): {', '.join(sorted(projects))}"
        for ip, projects in shared.items()
    ]
