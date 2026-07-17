"""Secondary deploy host management commands.

Follows the design principle: plural commands = manage resources. `slipp
hosts add/list/remove` manage inventory.yml's secondary (is_primary:
false) hosts -- the interactive `slipp launch` prompt is unchanged, and
only ever creates the primary host. Assigning a service to a secondary
host is a separate step: hand-edit slipp.yaml's `expose: <service>: host:
<name>`, then `slipp launch --reconfigure`.
"""

from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import RuntimeOption
from slipp.constants import DEFAULT_SSH_PORT, DEFAULT_SSH_USER
from slipp.services.config import (
    LocalConfigService,
    add_secondary_host,
    load_full_inventory,
    remove_secondary_host,
)
from slipp.utils.errors import ConfigError

hosts_app = typer.Typer(
    name="hosts",
    help="Manage secondary deploy hosts",
)


@hosts_app.command(name="add")
def hosts_add_command(
    name: Annotated[str, typer.Argument(help="Host name (inventory_hostname)")],
    host: Annotated[
        str, typer.Option("--host", help="IP address or domain for SSH connection")
    ],
    user: Annotated[
        str, typer.Option("--user", help="SSH username")
    ] = DEFAULT_SSH_USER,
    port: Annotated[int, typer.Option("--port", help="SSH port")] = DEFAULT_SSH_PORT,
    runtime: RuntimeOption = None,
) -> None:
    """Add a secondary host to this project's inventory."""
    project_root = LocalConfigService.resolve_root()

    try:
        new_host = add_secondary_host(
            project_root,
            name,
            ansible_host=host,
            ansible_user=user,
            ansible_port=port,
            runtime=runtime,
        )
    except ConfigError as e:
        output.error(str(e))
        raise typer.Exit(1)

    output.success(f"Added secondary host '{name}'")
    output.kv("ansible_host", new_host.ansible_host, indent=1)
    output.kv("ansible_user", new_host.ansible_user, indent=1)
    output.kv("ansible_port", str(new_host.ansible_port), indent=1)
    output.kv("runtime", new_host.runtime, indent=1)
    output.hint(
        f"Assign a service to it: expose: <service>: host: {name} in "
        "slipp.yaml, then run 'slipp launch --reconfigure'"
    )


@hosts_app.command(name="list")
def hosts_list_command() -> None:
    """List this project's hosts, primary and secondary."""
    project_root = LocalConfigService.resolve_root()
    inventory = load_full_inventory(project_root)

    rows = (
        [
            {
                "name": name,
                "role": "primary" if h.is_primary else "secondary",
                "ansible_host": h.ansible_host,
                "ansible_user": h.ansible_user,
                "ansible_port": h.ansible_port,
                "runtime": h.runtime.value,
            }
            for name, h in inventory.hosts.items()
        ]
        if inventory
        else []
    )
    output.empty_or_table(rows, "No hosts configured")


@hosts_app.command(name="remove")
def hosts_remove_command(
    name: Annotated[str, typer.Argument(help="Host name to remove")],
) -> None:
    """Remove a secondary host from this project's inventory."""
    project_root = LocalConfigService.resolve_root()

    try:
        remove_secondary_host(project_root, name)
    except ConfigError as e:
        output.error(str(e))
        raise typer.Exit(1)

    output.success(f"Removed secondary host '{name}'")
