"""Provision command - order a VPS via Gigahost and configure it for slipp deploy."""

from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.constants import DEFAULT_ENV, get_inventory_filename
from slipp.services.config import write_minimal_inventory
from slipp.services.launch.registration import register_project
from slipp.services.providers import get_gigahost_client, provision_and_bootstrap
from slipp.services.ssh import hint_ssh_log
from slipp.utils.errors import (
    BootstrapError,
    ProviderError,
    SSHConnectionError,
)


def provision_command(
    name: Annotated[str, typer.Argument(help="Project name")],
    environment: Annotated[
        str, typer.Option("--env", "-e", help="Environment name")
    ] = DEFAULT_ENV,
) -> None:
    """Order a VPS via Gigahost, bootstrap it, and register it as a slipp project."""
    try:
        client = get_gigahost_client()
        ip, _srv_id = provision_and_bootstrap(client, name)
    except ProviderError as e:
        output.error(f"Provisioning failed: {e}")
        raise typer.Exit(1)
    except (SSHConnectionError, BootstrapError) as e:
        output.error(f"Bootstrap failed: {e}")
        output.hint("Server is provisioned -- retry with: slipp bootstrap account <ip>")
        hint_ssh_log()
        raise typer.Exit(1)

    inventory_filename = get_inventory_filename(environment)
    write_minimal_inventory(Path.cwd() / inventory_filename, environment, ip)

    register_project(
        name=name,
        project_root=Path.cwd(),
        inventory_path=inventory_filename,
        playbook_path="playbook.yml",
    )

    output.success("Provisioning complete")
    if (Path.cwd() / "playbook.yml").exists():
        output.hint("slipp deploy is ready to run")
    else:
        output.hint("No playbook.yml found -- add one, or run: slipp launch")
