"""Logs command - view service logs."""

from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import find_service_or_exit, resolve_host_or_exit
from slipp.models.service import Runtime
from slipp.services.ssh import SSHService


def logs_command(
    service: Annotated[
        str, typer.Argument(help="Service name (e.g., synapse or synapse@matrix)")
    ],
    follow: Annotated[
        bool, typer.Option("--follow", "-f", help="Follow log output")
    ] = False,
    lines: Annotated[
        int, typer.Option("--lines", "-n", help="Number of lines to show")
    ] = 50,
    all_services: Annotated[
        bool, typer.Option("--all", help="Include system services in discovery")
    ] = False,
) -> None:
    """View service logs (journalctl or podman/docker logs)."""
    ssh_config = resolve_host_or_exit(service=service, command="logs")

    target_service = find_service_or_exit(
        ssh_config, service, include_system=all_services
    )

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
                    output.stdout(line)
            else:
                log_output = ssh.execute(cmd)
                output.stdout(log_output.text)
        except KeyboardInterrupt:
            output.success("Stopped following logs")
            raise typer.Exit(0)
