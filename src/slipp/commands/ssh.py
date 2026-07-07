"""SSH command for interactive shell on VPS or container.

This module provides the SSH CLI command that opens an interactive shell
on either the VPS directly or inside a running service container.
"""

import sys

import typer

from slipp import output
from slipp.commands.common import find_service_or_exit, resolve_host_or_exit
from slipp.models.service import Runtime
from slipp.services.ssh import InteractiveSessionManager, SSHService, UserResolver


def ssh_command(
    ctx: typer.Context,
    service: str | None = typer.Argument(
        None, help="Service to shell into (container or systemd)"
    ),
    user: str | None = typer.Option(
        None, "--user", "-u", help="Override user (e.g., root, postgres)"
    ),
):
    """Open interactive shell on VPS or container service."""
    session_manager = InteractiveSessionManager()
    ssh_config = resolve_host_or_exit(service=service, command="ssh")

    if not service:
        target_user = user or ssh_config.ansible_user
        exit_code = session_manager.ssh_as_user(
            ssh_config.ansible_host,
            ssh_config.ansible_user,
            target_user,
            ssh_config.ansible_port or 22,
        )
        sys.exit(exit_code)

    with SSHService(ssh_config) as ssh:
        svc = find_service_or_exit(ssh_config, service, include_system=False)

        user_resolver = UserResolver(ssh)
        resolution = user_resolver.resolve_from_runtime(
            svc.runtime,
            svc.unit_name,
            user,
            ssh_config.ansible_user,
        )

        if resolution.warning:
            output.warning(resolution.warning)

        if Runtime(svc.runtime).is_container():
            output.info(
                f"Shelling into container {svc.name} on {ssh_config.ansible_host}..."
            )
            output.blank()
            exit_code = session_manager.container_shell(
                ssh_config,
                svc.name,
                resolution.user,
                svc.runtime,
            )
        else:
            output.info(
                f"Connecting to {ssh_config.ansible_host} as {resolution.user}..."
            )
            output.blank()
            exit_code = session_manager.ssh_as_user(
                ssh_config.ansible_host,
                ssh_config.ansible_user,
                resolution.user,
                ssh_config.ansible_port or 22,
            )

        sys.exit(exit_code)
