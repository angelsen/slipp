"""Display and manage slipp project configuration.

Shows local slipp.yaml settings, inventory hosts, and global
registry status. Supports both human-readable table and JSON output.
"""

from pathlib import Path

import typer

from slipp import output
from slipp.constants import OutputFormat
from slipp.models.local_config import LocalConfig
from slipp.services.config import ConfigResolver, LocalConfigService, load_project_hosts
from slipp.services.registry import ProjectRegistry


def _resolve_local_config_or_exit(
    project_root: Path,
) -> tuple[ConfigResolver, LocalConfig]:
    """Resolve local config, reporting (in the active output format) and exiting if none exists."""
    resolver = ConfigResolver(project_root)

    if not resolver.has_local_config:
        if output.get_output_format() == OutputFormat.json:
            output.json(
                {
                    "error": "No slipp.yaml found in current directory or any parent",
                    "has_local_config": False,
                }
            )
        else:
            output.warning("No slipp.yaml found in current directory or any parent")
            output.hint(
                "Run 'slipp projects add <name> -i <inventory>' to create config"
            )
            output.hint(
                "Or 'slipp deploy --name <name> -i <inventory>' to deploy and save config"
            )
        raise typer.Exit(1)

    assert resolver.local_config is not None
    return resolver, resolver.local_config


def config_command() -> None:
    """Show current project configuration."""
    project_root = LocalConfigService.resolve_root()
    _, local_config = _resolve_local_config_or_exit(project_root)

    if output.get_output_format() == OutputFormat.json:
        _show_json(project_root, local_config)
    else:
        _show_table(project_root, local_config)


def _show_table(project_root: Path, local_config: LocalConfig) -> None:
    """Display config as formatted table."""
    output.task("Project Configuration")
    output.blank()

    rows = [
        {"setting": "name", "value": local_config.name},
        {"setting": "inventory", "value": local_config.inventory or "(none)"},
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

    hosts = load_project_hosts(project_root)
    output.blank()
    if hosts:
        output.info(f"Hosts ({len(hosts)}):")
        output.list_items(
            [f"{host['inventory_hostname']}: {host['ansible_host']}" for host in hosts]
        )
    else:
        output.warning("No hosts found in inventory")

    output.blank()
    registry = ProjectRegistry()
    project = registry.get(local_config.name)

    if project:
        output.success(f"Global registry: registered as '{project.name}'")
    else:
        output.warning("Not in global registry")
        output.hint("Run 'slipp projects add' or 'slipp deploy' to register globally")


def _show_json(project_root: Path, local_config: LocalConfig) -> None:
    """Display config as JSON."""
    registry = ProjectRegistry()
    project = registry.get(local_config.name)

    result = {
        "project_name": local_config.name,
        "project_root": str(project_root),
        "has_local_config": True,
        "local_config": local_config.model_dump(),
        "global_registry": None,
        "hosts": load_project_hosts(project_root),
    }

    if project:
        result["global_registry"] = {
            "name": project.name,
            "project_path": str(project.project_path),
            "registered_at": project.registered_at.isoformat(),
        }

    output.json(result)
