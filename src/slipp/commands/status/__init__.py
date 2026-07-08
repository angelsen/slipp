"""Status command for checking service and system status.

Provides the `slipp status` command to display health and status information
for managed services and infrastructure.
"""

from slipp.commands.status.status import status_command

__all__ = ["status_command"]
