"""Parsing helpers for `systemctl status` output.

Used by the `slipp status` command to extract a summary and recent log
lines from raw systemctl output. Distinct from services/discovery, which
handles service *discovery* (systemctl list-units/show), not status display.
"""

import re
import shlex


def build_status_command(unit_name: str) -> str:
    """Build systemctl status command for a unit.

    LC_ALL=C forces English month names so extract_status_log_lines() can
    find the log section regardless of the host's locale.

    Args:
        unit_name: Systemd unit name to query

    Returns:
        Full command string
    """
    return f"sudo env LC_ALL=C systemctl status {shlex.quote(unit_name)}"


def parse_systemctl_status(output_text: str) -> dict[str, str]:
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


def extract_status_log_lines(output_text: str) -> list[str]:
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


__all__ = [
    "build_status_command",
    "extract_status_log_lines",
    "parse_systemctl_status",
]
