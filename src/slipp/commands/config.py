"""Display and manage slipp project configuration.

Shows local slipp.yaml settings, inventory hosts, and global
registry status. Supports both human-readable table and JSON output.
"""

from pathlib import Path

import typer

from slipp import output
from slipp.constants import OutputFormat
from slipp.services.config import ConfigResolver, LocalConfigService
from slipp.services.registry import ProjectRegistry


def config_command():
    """Show current project configuration."""
    project_root = Path.cwd()

    if output.get_output_format() == OutputFormat.json:
        _show_json(project_root)
    else:
        _show_table(project_root)


def _load_hosts_for_project(project_path: Path) -> list[dict[str, str | int]]:
    """Load hosts from project's local config and inventory.

    Returns list of dicts with inventory_hostname and ansible_host.
    """
    from slipp.services.config import InventoryService

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


def _show_table(project_root: Path) -> None:
    """Display config as formatted table."""
    resolver = ConfigResolver(project_root)

    if not resolver.has_local_config:
        output.warning("No slipp.yaml found in current directory")
        output.hint("Run 'ac register <name> -i <inventory>' to create config")
        output.hint(
            "Or 'ac deploy --name <name> -i <inventory>' to deploy and save config"
        )
        raise typer.Exit(1)

    local_config = resolver.local_config
    assert local_config is not None

    output.task("Project Configuration")
    output.blank()

    rows = [
        {"setting": "name", "value": local_config.name},
        {"setting": "inventory", "value": local_config.inventory},
        {"setting": "playbook", "value": local_config.playbook},
        {
            "setting": "roles_path",
            "value": ", ".join(local_config.roles_path)
            if local_config.roles_path
            else "(none)",
        },
        {"setting": "galaxy_path", "value": local_config.galaxy_path or "(none)"},
        {"setting": "vault", "value": local_config.vault or "(none)"},
        {
            "setting": "managed_roles",
            "value": f"{len(local_config.managed_roles)} role(s)"
            if local_config.managed_roles
            else "(none)",
        },
    ]
    output.table(rows)

    hosts = _load_hosts_for_project(project_root)
    output.blank()
    if hosts:
        output.info(f"Hosts ({len(hosts)}):")
        for host in hosts:
            output.stdout(f"  - {host['inventory_hostname']}: {host['ansible_host']}")
    else:
        output.warning("No hosts found in inventory")

    output.blank()
    registry = ProjectRegistry()
    project = registry.get(local_config.name)

    if project:
        output.success(f"Global registry: registered as '{project.name}'")
    else:
        output.warning("Not in global registry")
        output.hint("Run 'ac register' or 'ac deploy' to register globally")


def _show_json(project_root: Path) -> None:
    """Display config as JSON."""
    import json

    resolver = ConfigResolver(project_root)
    registry = ProjectRegistry()
    local_config = resolver.local_config

    project = None
    if local_config:
        project = registry.get(local_config.name)

    result = {
        "project_name": local_config.name if local_config else None,
        "project_root": str(project_root),
        "has_local_config": resolver.has_local_config,
        "local_config": None,
        "global_registry": None,
        "hosts": None,
    }

    if resolver.has_local_config and local_config:
        result["local_config"] = local_config.model_dump()
        result["hosts"] = _load_hosts_for_project(project_root)

    if project:
        result["global_registry"] = {
            "name": project.name,
            "project_path": str(project.project_path),
            "registered_at": project.registered_at.isoformat(),
        }

    output.stdout(json.dumps(result, indent=2))
