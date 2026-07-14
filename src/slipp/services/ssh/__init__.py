"""SSH and remote execution services.

This package provides services for SSH connections, tunnels, and remote execution.
"""

from slipp.services.ssh.client import SSHResult, SSHService, hint_ssh_log
from slipp.services.ssh.command import (
    build_container_command,
    build_logs_command,
    build_ssh_command,
    build_vps_command,
)
from slipp.services.ssh.session import container_shell, ssh_as_user
from slipp.services.ssh.tunnel import (
    TunnelManager,
    parse_container_tunnel_in,
    parse_tunnel_in,
    parse_tunnel_out,
)
from slipp.services.ssh.user import UserResolver

__all__ = [
    "SSHResult",
    "SSHService",
    "TunnelManager",
    "parse_container_tunnel_in",
    "parse_tunnel_in",
    "parse_tunnel_out",
    "container_shell",
    "ssh_as_user",
    "build_container_command",
    "build_logs_command",
    "build_ssh_command",
    "build_vps_command",
    "UserResolver",
    "hint_ssh_log",
]
