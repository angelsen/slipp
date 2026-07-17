"""List running services (like docker ps) across registered projects."""

from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import ProjectOption
from slipp.models.service import Service
from slipp.services.config import HostResolver, collect_managed_roles
from slipp.services.discovery import filter_services
from slipp.services.discovery.pipeline import discover_across_hosts
from slipp.services.ssh import hint_ssh_log


def _display_services_table(services: list[Service]) -> None:
    """Render services as a table (or JSON), one row schema for both formats."""
    rows = [
        {
            "project": ", ".join(s.projects) if s.projects else "-",
            "service": s.name,
            "host": s.inventory_hostname,
            "ip": s.host,
            "runtime": s.runtime.value,
            "state": s.state.value,
            "uptime": s.uptime or "-",
        }
        for s in services
    ]
    output.empty_or_table(rows, "No services found")


def ps_command(
    project: ProjectOption = None,
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Force re-discovery (bypass cache)")
    ] = False,
    all_services: Annotated[
        bool, typer.Option("--all", help="Include system services in discovery")
    ] = False,
) -> None:
    """List running services (like docker ps)."""
    resolver = HostResolver()

    if project:
        # Every host the project owns, not just its primary -- a
        # multi-host project's services live on more than one machine,
        # and resolving to a single connection target here (as exec/ssh/
        # logs correctly do) would silently omit every secondary host's
        # services from the listing.
        project_hosts = [(project, h) for h in resolver.all_hosts_for_project(project)]
        managed_roles = collect_managed_roles(project)

        if refresh:
            output.info(
                f"Re-discovering services across {len(project_hosts)} host(s)..."
            )

        services, errors = discover_across_hosts(
            project_hosts,
            include_system=all_services,
            force=refresh,
        )

        services = filter_services(
            services,
            project=project,
            show_all=all_services,
            managed_roles=managed_roles,
        )

    else:
        hosts = resolver.all_hosts()

        if not hosts:
            output.warning("No projects registered")
            output.info(
                "Hint: Use 'slipp projects add' or 'slipp deploy' to register a project"
            )
            raise typer.Exit(0)

        managed_roles = collect_managed_roles()

        if refresh:
            output.info(f"Re-discovering services across {len(hosts)} host(s)...")

        services, errors = discover_across_hosts(
            hosts,
            include_system=all_services,
            force=refresh,
        )

        services = filter_services(
            services, show_all=all_services, managed_roles=managed_roles
        )

    _display_services_table(services)

    cache_status = "(from cache)" if not refresh else "(fresh discovery)"

    all_projects: set[str] = set()
    for s in services:
        all_projects.update(s.projects)
    projects_found = len(all_projects)

    output.blank()
    if project:
        output.info(f"Found {len(services)} service(s) {cache_status}")
    else:
        output.info(
            f"Found {len(services)} service(s) across {projects_found} project(s) {cache_status}"
        )

    if errors:
        output.blank()
        output.warning(f"{len(errors)} host(s) unreachable:")
        output.list_items(errors, indent=1)
        hint_ssh_log()

    if not all_services and not project:
        output.hint("Tip: Use --all for system services, -p <project> to filter")
