"""SSH command for interactive shell on VPS or container.

This module provides the SSH CLI command that opens an interactive shell
on either the VPS directly or inside a running service container.
"""

import sys

import typer

from slipp import output
from slipp.models.service import Runtime
from slipp.services.discovery import ServiceLocator
from slipp.services.config import HostResolver
from slipp.services.ssh import InteractiveSessionManager, SSHService, UserResolver
from slipp.utils.errors import (
    AmbiguousServiceError,
    HostNotFoundError,
    ServiceNotFoundError,
)


def ssh_command(
    ctx: typer.Context,
    service: str | None = typer.Argument(
        None, help="Service to shell into (container or systemd)"
    ),
    user: str | None = typer.Option(
        None, "--user", "-u", help="Override user (e.g., root, postgres)"
    ),
):
    """Open interactive shell on VPS or container service.

    If no service is specified, connects directly to the VPS.
    If a service is specified, shells into the running container or connects
    as the service user for systemd services.

    Args:
        ctx: Typer context (auto-injected).
        service: Optional service name to shell into.
        user: Optional override for the target user.

    Exits:
        1: If host or service cannot be resolved.
    """
    host_resolver = HostResolver()
    session_manager = InteractiveSessionManager()

    try:
        if service:
            ssh_config = host_resolver.by_service(service)
        else:
            ssh_config = host_resolver.current()
    except HostNotFoundError as e:
        output.error(str(e))
        raise typer.Exit(1)
    except AmbiguousServiceError as e:
        output.error(str(e))
        output.suggestions("Specify target:", e.get_suggestions(command="ssh"))
        raise typer.Exit(1)

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
        locator = ServiceLocator(ssh_config, include_system=False)

        try:
            svc = locator.find_one(service)
        except ServiceNotFoundError as e:
            output.error(str(e))
            output.info("Hint: Use 'slipp ps' to see available services")
            raise typer.Exit(1)

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
