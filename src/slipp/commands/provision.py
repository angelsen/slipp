"""Provision command - order a VPS via Gigahost and configure it for slipp deploy."""

from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.constants import DEFAULT_ENV, PLAYBOOK_FILENAME, get_inventory_filename
from slipp.services.config import write_minimal_inventory
from slipp.services.launch.registration import register_project
from slipp.services.providers import get_gigahost_client, provision_and_bootstrap
from slipp.services.providers.gigahost import GigahostClient
from slipp.services.ssh import hint_ssh_log
from slipp.utils.errors import (
    BootstrapError,
    ProviderError,
    SSHConnectionError,
)


def provision_or_exit(client: GigahostClient, name: str) -> str:
    """Provision + bootstrap a VPS, printing enriched errors and exiting on failure.

    Shared by `slipp provision` and `slipp up` so the two-arm error handling
    (order failure vs bootstrap-after-order failure) can't drift.

    Returns:
        The new server's IP address.
    """
    try:
        ip, _srv_id = provision_and_bootstrap(client, name)
        return ip
    except ProviderError as e:
        output.error(f"Provisioning failed: {e}")
        raise typer.Exit(1)
    except (SSHConnectionError, BootstrapError) as e:
        output.error(f"Bootstrap failed: {e}")
        output.hint("Server is provisioned -- retry with: slipp bootstrap account <ip>")
        hint_ssh_log()
        raise typer.Exit(1)


def provision_command(
    name: Annotated[str, typer.Argument(help="Project name")],
    environment: Annotated[
        str, typer.Option("--env", "-e", help="Environment name")
    ] = DEFAULT_ENV,
) -> None:
    """Order a VPS via Gigahost, bootstrap it, and register it as a slipp project."""
    client = get_gigahost_client()
    ip = provision_or_exit(client, name)

    inventory_filename = get_inventory_filename(environment)
    write_minimal_inventory(Path.cwd() / inventory_filename, environment, ip)

    register_project(
        name=name,
        project_root=Path.cwd(),
        inventory_path=inventory_filename,
        playbook_path=PLAYBOOK_FILENAME,
    )

    output.success("Provisioning complete")
    if (Path.cwd() / PLAYBOOK_FILENAME).exists():
        output.hint("slipp deploy is ready to run")
    else:
        output.hint(f"No {PLAYBOOK_FILENAME} found -- add one, or run: slipp launch")
