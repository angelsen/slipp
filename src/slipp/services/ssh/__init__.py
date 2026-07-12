"""SSH and remote execution services.

This package provides services for SSH connections, tunnels, and remote execution.
"""

from slipp.services.ssh.client import SSHResult, SSHService, hint_ssh_log
from slipp.services.ssh.command import CommandBuilder, build_ssh_command
from slipp.services.ssh.session import container_shell, ssh_as_user, ssh_session
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
    "ssh_session",
    "CommandBuilder",
    "build_ssh_command",
    "UserResolver",
    "hint_ssh_log",
]
