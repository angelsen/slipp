"""Display detailed service status information.

Provides systemctl-style status output for Ansible-managed services,
including current state, resource usage, and recent logs.
"""

import re

import typer

from slipp import output
from slipp.commands.common import show_service_not_found_error
from slipp.services.discovery import discover_and_enrich, find_service
from slipp.services.config import HostResolver
from slipp.services.ssh import SSHService
from slipp.utils.errors import AmbiguousServiceError, HostNotFoundError


def status_command(
    ctx: typer.Context,
    service: str = typer.Argument(..., help="Service name to show status for"),
):
    """Display detailed service status (like systemctl status).

    Shows service state, resource usage, and recent logs from systemctl.

    Args:
        ctx: Typer context (auto-injected).
        service: Service name or identifier to display status for.

    Raises:
        typer.Exit: On service not found or host resolution errors.
    """
    resolver = HostResolver()

    try:
        ssh_config = resolver.by_service(service)
    except HostNotFoundError as e:
        output.error(str(e))
        raise typer.Exit(1)
    except AmbiguousServiceError as e:
        output.error(str(e))
        output.suggestions("Specify target:", e.get_suggestions(command="status"))
        raise typer.Exit(1)

    services = discover_and_enrich(ssh_config, include_system=True)
    target_service = find_service(services, service)

    if not target_service:
        show_service_not_found_error(service, ssh_config.ansible_host, services)
        raise typer.Exit(1)

    output.task(f"Status for {target_service.name}@{target_service.host}")

    with SSHService(ssh_config) as ssh:
        try:
            cmd_output = ssh.execute(
                f"sudo systemctl status {target_service.unit_name}"
            )
            details = _parse_systemctl_status(cmd_output)

            output.text(f"Service: {target_service.name}")
            output.text(f"Unit: {target_service.unit_name}")
            output.text(f"Runtime: {target_service.runtime}")
            output.text(f"State: {target_service.state}")

            if details.get("loaded"):
                output.text(f"Loaded: {details['loaded']}")
            if details.get("active"):
                output.text(f"Active: {details['active']}")
            if details.get("pid"):
                output.text(f"Main PID: {details['pid']}")
            if details.get("memory"):
                output.text(f"Memory: {details['memory']}")
            if details.get("tasks"):
                output.text(f"Tasks: {details['tasks']}")

            output.blank()
            output.task("Recent logs")

            log_lines = _extract_log_lines(cmd_output)
            for line in log_lines[-10:]:
                output.text(line)

            output.blank()
            output.hint(f"Tip: Use 'ac logs {target_service.name} -f' to follow logs")

        except Exception as e:
            output.error(f"Failed to get status: {e}")
            raise typer.Exit(1)


def _parse_systemctl_status(output_text: str) -> dict:
    """Parse systemctl status output to extract key details.

    Args:
        output_text: Raw output from systemctl status command.

    Returns:
        Dictionary with keys: loaded, active, pid, memory, tasks.
    """
    details = {}

    for line in output_text.splitlines():
        line = line.strip()

        if line.startswith("Loaded:"):
            details["loaded"] = line.replace("Loaded:", "").strip()
        elif line.startswith("Active:"):
            details["active"] = line.replace("Active:", "").strip()
        elif line.startswith("Main PID:"):
            match = re.search(r"Main PID:\s+(\d+)", line)
            if match:
                details["pid"] = match.group(1)
        elif line.startswith("Memory:"):
            match = re.search(r"Memory:\s+([\d.]+\w+)", line)
            if match:
                details["memory"] = match.group(1)
        elif line.startswith("Tasks:"):
            match = re.search(r"Tasks:\s+(\d+)", line)
            if match:
                details["tasks"] = match.group(1)

    return details


def _extract_log_lines(output_text: str) -> list[str]:
    """Extract log lines from systemctl status output.

    Args:
        output_text: Raw output from systemctl status command.

    Returns:
        List of log lines from the systemctl output.
    """
    log_lines = []
    in_logs = False

    months = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]

    for line in output_text.splitlines():
        if in_logs or any(line.strip().startswith(m) for m in months):
            in_logs = True
            log_lines.append(line)

    return log_lines
