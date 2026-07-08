"""List running services (like docker ps) across registered projects."""

import json

import typer

from slipp import output
from slipp.commands.common import display_services_table, resolve_host_or_exit
from slipp.constants import OutputFormat
from slipp.services.discovery import (
    discover_across_hosts,
    discover_and_enrich,
    filter_services,
)
from slipp.services.config import HostResolver, collect_managed_roles


def ps_command(
    ctx: typer.Context,
    project: str | None = typer.Option(
        None, "--project", "-p", help="Filter by project name"
    ),
    refresh: bool = typer.Option(
        False, "--refresh", help="Force re-discovery (bypass cache)"
    ),
    all_services: bool = typer.Option(
        False, "--all", help="Include system services in discovery"
    ),
):
    """List running services (like docker ps)."""
    resolver = HostResolver()

    if project:
        ssh_config = resolve_host_or_exit(project=project)
        managed_roles = collect_managed_roles(project)

        if refresh:
            output.info(f"Re-discovering services on {ssh_config.ansible_host}...")

        services = discover_and_enrich(
            ssh_config, include_system=all_services, force=refresh
        )

        services = filter_services(
            services,
            project=project,
            show_all=all_services,
            managed_roles=managed_roles,
        )
        errors: list[str] = []

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
            hosts, include_system=all_services, force=refresh
        )

        services = filter_services(
            services, show_all=all_services, managed_roles=managed_roles
        )

    if output.get_output_format() == OutputFormat.json:
        data = [
            {
                "name": s.name,
                "project": ", ".join(s.projects) if s.projects else None,
                "host": s.inventory_hostname,
                "ip": s.host,
                "runtime": s.runtime.value,
                "state": s.state.value,
                "uptime": s.uptime,
            }
            for s in services
        ]
        output.stdout(json.dumps(data, indent=2))
        return

    display_services_table(
        services,
        include_project=True,
        include_host=True,
        include_ip=True,
    )

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
        output.list_items(errors, indent=2)

    if not all_services and not project:
        output.hint("Tip: Use --all for system services, -p <project> to filter")
