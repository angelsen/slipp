"""SSH command for interactive shell on VPS or container.

This module provides the SSH CLI command that opens an interactive shell
on either the VPS directly or inside a running service container.
"""

from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import find_service_or_exit, resolve_host_or_exit
from slipp.services.ssh import SSHService, container_shell, resolve_user, ssh_as_user


def ssh_command(
    service: Annotated[
        str | None,
        typer.Argument(help="Service to shell into (container or systemd)"),
    ] = None,
    user: Annotated[
        str | None,
        typer.Option("--user", "-u", help="Override user (e.g., root, postgres)"),
    ] = None,
) -> None:
    """Open interactive shell on VPS or container service."""
    ssh_config = resolve_host_or_exit(service=service, command="ssh")

    if not service:
        target_user = user or ssh_config.ansible_user
        exit_code = ssh_as_user(ssh_config, target_user)
        raise typer.Exit(exit_code)

    with SSHService(ssh_config) as ssh:
        svc = find_service_or_exit(ssh_config, service, include_system=False)

        resolved_user = resolve_user(ssh, svc, user, ssh_config.ansible_user)

        if svc.runtime.is_container():
            output.info(
                f"Shelling into container {svc.name} on {ssh_config.ansible_host}..."
            )
            output.blank()
            exit_code = container_shell(
                ssh_config,
                svc.name,
                resolved_user,
                svc.runtime,
            )
        else:
            output.info(
                f"Connecting to {ssh_config.ansible_host} as {resolved_user}..."
            )
            output.blank()
            exit_code = ssh_as_user(ssh_config, resolved_user)

        raise typer.Exit(exit_code)
