"""Logs command - view service logs."""

import typer

from slipp import output
from slipp.commands.common import show_service_not_found_error
from slipp.models.service import Runtime
from slipp.services.config import HostResolver
from slipp.services.discovery import ServiceLocator
from slipp.services.ssh import SSHService
from slipp.utils.errors import (
    AmbiguousServiceError,
    HostNotFoundError,
    ServiceNotFoundError,
)


def logs_command(
    ctx: typer.Context,
    service: str = typer.Argument(
        ..., help="Service name (e.g., synapse or synapse@matrix)"
    ),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
    lines: int = typer.Option(50, "--lines", "-n", help="Number of lines to show"),
    all_services: bool = typer.Option(
        False, "--all", help="Include system services in discovery"
    ),
):
    """View service logs (journalctl or podman/docker logs).

    Fetches logs from either journalctl (systemd-managed) or container
    runtime (docker/podman). Supports following output with --follow.

    Args:
        ctx: Typer context.
        service: Service name to fetch logs for (e.g., synapse or synapse@matrix).
        follow: If True, continuously stream new log lines.
        lines: Number of historical log lines to display.
        all_services: If True, include system services in discovery.

    Raises:
        typer.Exit: On resolution errors or service not found.
    """
    resolver = HostResolver()

    try:
        ssh_config = resolver.by_service(service)
    except HostNotFoundError as e:
        output.error(str(e))
        raise typer.Exit(1)
    except AmbiguousServiceError as e:
        output.error(str(e))
        output.suggestions("Specify target:", e.get_suggestions(command="logs"))
        raise typer.Exit(1)

    locator = ServiceLocator(ssh_config, include_system=all_services)

    try:
        target_service = locator.find_one(service)
    except ServiceNotFoundError:
        services = locator.find_many()
        show_service_not_found_error(service, ssh_config.ansible_host, services)
        raise typer.Exit(1)

    if Runtime(target_service.runtime).is_container() and not target_service.unit_name:
        cmd = f"sudo {target_service.runtime} logs --tail={lines}"
        if follow:
            cmd += " --follow"
        cmd += f" {target_service.name}"
    else:
        cmd = f"sudo journalctl -u {target_service.unit_name} -n {lines}"
        if follow:
            cmd += " -f"

    output.task(f"Logs for {target_service.name}@{target_service.host}")
    output.info(f"({target_service.runtime}, {target_service.state})")

    with SSHService(ssh_config) as ssh:
        try:
            if follow:
                for line in ssh.execute_stream(cmd):
                    print(line)
            else:
                log_output = ssh.execute(cmd)
                print(log_output)
        except KeyboardInterrupt:
            output.success("Stopped following logs")
            raise typer.Exit(0)
