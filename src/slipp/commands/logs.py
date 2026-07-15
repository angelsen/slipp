"""Logs command - view service logs."""

from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import (
    find_service_or_exit,
    resolve_host_or_exit,
)
from slipp.services.ssh import SSHService, build_logs_command, hint_ssh_log


def logs_command(
    service: Annotated[
        str, typer.Argument(help="Service name (e.g., synapse or synapse@matrix)")
    ],
    follow: Annotated[bool, typer.Option("--follow", help="Follow log output")] = False,
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

    cmd = build_logs_command(target_service, lines, follow)

    output.task(f"Logs for {target_service.name}@{target_service.host}")
    output.info(f"({target_service.runtime}, {target_service.state})")

    with SSHService(ssh_config) as ssh:
        # Discovery may have been a cache hit (no SSH, no prompt), and a
        # stream can't prompt once it has started — so ensure sudo up front.
        ssh.ensure_sudo("Fetching logs")
        try:
            if follow:
                for line in ssh.execute_stream(cmd):
                    output.stdout(line)
                if ssh.last_stream_result:
                    ssh.check_sudo(ssh.last_stream_result, "Fetching logs")
            else:
                log_output = ssh.execute(cmd)
                ssh.check_sudo(log_output, "Fetching logs")
                if not log_output.ok:
                    output.warning(f"Command exited with code {log_output.exit_code}")
                    hint_ssh_log()
                output.stdout(log_output.text)
        except KeyboardInterrupt:
            output.success("Stopped following logs")
            raise typer.Exit(0)
