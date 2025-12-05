"""Host info command for pipeable output."""

from typing import Annotated

import typer

from slipp import output
from slipp.services.config import HostResolver
from slipp.services.registry import ProjectRegistry
from slipp.utils.errors import HostNotFoundError


def host_command(
    project: Annotated[str | None, typer.Argument(help="Project name")] = None,
    ip_only: Annotated[bool, typer.Option("--ip", help="Output IP only")] = False,
    user_only: Annotated[bool, typer.Option("--user", help="Output user only")] = False,
    port_only: Annotated[bool, typer.Option("--port", help="Output port only")] = False,
) -> None:
    """Output host connection info (pipeable)."""
    resolver = HostResolver()

    try:
        if project:
            host = resolver.by_project(project)
        else:
            host = resolver.current()
    except HostNotFoundError as e:
        output.error(str(e))
        projects = ProjectRegistry().list_all()
        if projects:
            output.hint(f"Available: {', '.join(p.name for p in projects)}")
        raise typer.Exit(1)

    if ip_only:
        output.stdout(host.ansible_host)
    elif user_only:
        output.stdout(host.ansible_user)
    elif port_only:
        output.stdout(str(host.ansible_port))
    else:
        output.stdout(f"{host.ansible_user}@{host.ansible_host}")
