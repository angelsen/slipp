"""Display detailed service status information.

Provides systemctl-style status output for Ansible-managed services,
including current state, resource usage, and recent logs.
"""

from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import (
    find_service_or_exit,
    resolve_host_or_exit,
)
from slipp.services.ssh import SSHService
from slipp.services.status import (
    build_status_command,
    extract_status_log_lines,
    parse_systemctl_status,
)


def status_command(
    service: Annotated[str, typer.Argument(help="Service name to show status for")],
    all_services: Annotated[
        bool, typer.Option("--all", help="Include system services in discovery")
    ] = False,
) -> None:
    """Display detailed service status (like systemctl status)."""
    ssh_config = resolve_host_or_exit(service=service, command="status")

    target_service = find_service_or_exit(
        ssh_config, service, include_system=all_services
    )

    output.task(f"Status for {target_service.name}@{target_service.host}")

    with SSHService(ssh_config) as ssh:
        # Discovery may have been a cache hit (no SSH, no prompt) - ensure
        # sudo works before running the status command.
        ssh.ensure_sudo("Fetching service status")
        # systemctl status legitimately exits non-zero for inactive/failed
        # units with usable stdout - only sudo failures are worth raising on
        result = ssh.execute(build_status_command(target_service.unit_name))
        ssh.check_sudo(result, "Fetching service status")
        cmd_output = result.stdout
        details = parse_systemctl_status(cmd_output)

        output.stdout(f"Service: {target_service.name}")
        output.stdout(f"Unit: {target_service.unit_name}")
        output.stdout(f"Runtime: {target_service.runtime}")
        output.stdout(f"State: {target_service.state}")

        if details.get("loaded"):
            output.stdout(f"Loaded: {details['loaded']}")
        if details.get("active"):
            output.stdout(f"Active: {details['active']}")
        if details.get("pid"):
            output.stdout(f"Main PID: {details['pid']}")
        if details.get("memory"):
            output.stdout(f"Memory: {details['memory']}")
        if details.get("tasks"):
            output.stdout(f"Tasks: {details['tasks']}")

        output.blank()
        output.task("Recent logs")

        log_lines = extract_status_log_lines(cmd_output)
        for line in log_lines[-10:]:
            output.stdout(line)

        output.blank()
        output.hint(f"Tip: Use 'slipp logs {target_service.name} -f' to follow logs")
