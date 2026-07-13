"""Host info command for pipeable output."""

from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import resolve_host_or_exit


def host_command(
    project: Annotated[
        str | None, typer.Option("--project", "-p", help="Project name")
    ] = None,
    ip_only: Annotated[bool, typer.Option("--ip", help="Output IP only")] = False,
    user_only: Annotated[bool, typer.Option("--user", help="Output user only")] = False,
    port_only: Annotated[bool, typer.Option("--port", help="Output port only")] = False,
) -> None:
    """Output host connection info (pipeable)."""
    host = resolve_host_or_exit(project=project)

    if ip_only:
        output.stdout(host.ansible_host)
    elif user_only:
        output.stdout(host.ansible_user)
    elif port_only:
        output.stdout(str(host.ansible_port))
    else:
        output.stdout(f"{host.ansible_user}@{host.ansible_host}")
