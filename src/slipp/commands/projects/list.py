"""List all registered projects with their hosts and paths.

Displays projects in table format by default or JSON with --json.
Loads host details from each project's inventory on-demand.
"""

import json
from pathlib import Path

import typer

from slipp import output
from slipp.constants import OutputFormat
from slipp.services.registry import ProjectRegistry


def _load_hosts_for_project(project_path: Path) -> list[dict[str, str | int]]:
    """Load hosts from project's local config and inventory."""
    from slipp.services.config import InventoryService, LocalConfigService

    local_config = LocalConfigService.load(project_path)
    if not local_config:
        return []

    inventory_path = project_path / local_config.inventory
    if not inventory_path.exists():
        return []

    try:
        inventory_config = InventoryService.parse(inventory_path)
        return [
            {
                "inventory_hostname": hostname,
                "ansible_host": host.ansible_host,
                "ansible_user": host.ansible_user,
                "ansible_port": host.ansible_port,
            }
            for hostname, host in inventory_config.hosts.items()
        ]
    except Exception:
        return []


def list_command(
    ctx: typer.Context,
):
    """List all registered projects."""
    project_registry = ProjectRegistry()
    projects = project_registry.list_all()

    if not projects:
        output.warning("No projects registered yet")
        output.hint("Deploy a project with 'ac deploy' to register it automatically")
        return

    if output.get_output_format() == OutputFormat.json:
        data = []
        for p in projects:
            hosts = _load_hosts_for_project(p.project_path)
            data.append(
                {
                    "name": p.name,
                    "hosts": hosts,
                    "project_path": str(p.project_path),
                    "registered_at": p.registered_at.isoformat(),
                }
            )
        output.stdout(json.dumps(data, indent=2))
    else:
        output.blank()
        output.task("Registered Projects")
        output.blank()

        rows: list[dict[str, str]] = []
        total_hosts = 0
        for p in projects:
            hosts = _load_hosts_for_project(p.project_path)
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
        output.hint("Tip: Use 'ac logs <project>' from any directory")
