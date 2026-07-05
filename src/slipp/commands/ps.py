"""List running services (like docker ps) across registered projects."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import typer

from slipp import output
from slipp.commands.common import display_services_table, resolve_host_or_exit
from slipp.constants import OutputFormat
from slipp.models.host import AnsibleHost
from slipp.models.service import Service
from slipp.services.discovery import discover_and_enrich, filter_services
from slipp.services.config import HostResolver


def _discover_on_host(
    project: str,
    host: AnsibleHost,
    include_system: bool,
    force: bool,
) -> tuple[str, list[Service], str | None]:
    """Discover services on a single host.

    Args:
        project: Project name
        host: Host to query
        include_system: Include system services
        force: Force re-discovery

    Returns:
        Tuple of (project_name, services, error_message)
    """
    try:
        services = discover_and_enrich(host, include_system=include_system, force=force)
        return (project, services, None)
    except Exception as e:
        return (project, [], str(e))


def _discover_all_hosts_parallel(
    hosts: list[tuple[str, AnsibleHost]],
    include_system: bool,
    force: bool,
    max_workers: int = 5,
) -> tuple[list[Service], list[str]]:
    """Discover services across all hosts in parallel.

    Args:
        hosts: List of (project_name, AnsibleHost) tuples
        include_system: Include system services
        force: Force re-discovery
        max_workers: Maximum parallel connections

    Returns:
        Tuple of (all_services, error_messages)
    """
    all_services: list[Service] = []
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_discover_on_host, project, host, include_system, force): (
                project,
                host,
            )
            for project, host in hosts
        }

        for future in as_completed(futures):
            project, host = futures[future]
            try:
                _, services, error = future.result(timeout=30)
                if error:
                    errors.append(f"{project} ({host.ansible_host}): {error}")
                else:
                    all_services.extend(services)
            except Exception as e:
                errors.append(f"{project} ({host.ansible_host}): {e}")

    return all_services, errors


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
    from slipp.services.registry import ProjectRegistry

    resolver = HostResolver()

    if project:
        ssh_config = resolve_host_or_exit(project=project)

        from slipp.services.config import LocalConfigService

        project_registry = ProjectRegistry()
        proj = project_registry.get(project)
        managed_roles: list[str] | None = None
        if proj:
            local_config = LocalConfigService.load(proj.project_path)
            if local_config and local_config.managed_roles:
                managed_roles = local_config.managed_roles

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

        from slipp.services.config import LocalConfigService

        project_registry = ProjectRegistry()
        all_managed_roles: set[str] = set()
        for proj in project_registry.list_all():
            local_config = LocalConfigService.load(proj.project_path)
            if local_config and local_config.managed_roles:
                all_managed_roles.update(local_config.managed_roles)
        managed_roles = list(all_managed_roles) if all_managed_roles else None

        if refresh:
            output.info(f"Re-discovering services across {len(hosts)} host(s)...")

        services, errors = _discover_all_hosts_parallel(
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
