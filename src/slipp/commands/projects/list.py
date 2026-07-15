"""List all registered projects with their hosts and paths.

Displays projects in table format by default or JSON with -o json.
Loads host details from each project's inventory on-demand.
"""

from slipp import output
from slipp.constants import OutputFormat
from slipp.services.config import load_project_hosts
from slipp.services.registry import ProjectRegistry


def list_command() -> None:
    """List all registered projects."""
    project_registry = ProjectRegistry()
    projects = project_registry.list_all()

    if not projects:
        output.empty_or_table(
            [],
            "No projects registered yet",
            hint_msg="Deploy a project with 'slipp deploy' to register it automatically",
            warn=True,
        )
        return

    projects_with_hosts = [(p, load_project_hosts(p.project_path)) for p in projects]

    if output.get_output_format() == OutputFormat.json:
        data = [
            {
                "name": p.name,
                "hosts": hosts,
                "project_path": str(p.project_path),
                "registered_at": p.registered_at.isoformat(),
            }
            for p, hosts in projects_with_hosts
        ]
        output.json(data)
    else:
        output.task("Registered Projects")
        output.blank()

        rows: list[dict[str, str]] = []
        total_hosts = 0
        for p, hosts in projects_with_hosts:
            total_hosts += len(hosts)

            if hosts:
                first_host = hosts[0]
                host_str = (
                    f"{first_host['inventory_hostname']}: {first_host['ansible_host']}"
                )
                if len(hosts) > 1:
                    host_str += f" (+{len(hosts) - 1} more)"
            else:
                host_str = "(no hosts)"

            rows.append(
                {
                    "project": p.name,
                    "hosts": host_str,
                    "path": str(p.project_path),
                }
            )
        output.table(rows)

        output.blank()
        output.info(f"Found {len(projects)} project(s), {total_hosts} host(s)")
        output.hint("Tip: Use 'slipp logs <project>' from any directory")
