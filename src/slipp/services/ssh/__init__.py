"""SSH and remote execution services.

This package provides services for SSH connections, tunnels, and remote execution.
"""

from slipp.services.ssh.client import SSHService
from slipp.services.ssh.command import CommandBuilder
from slipp.services.ssh.session import InteractiveSessionManager
from slipp.services.ssh.tunnel import (
    TunnelManager,
    parse_container_tunnel_in,
    parse_tunnel_in,
    parse_tunnel_out,
    resolve_tunnel_host,
)
from slipp.services.ssh.user import UserResolution, UserResolver

__all__ = [
    "SSHService",
    "TunnelManager",
    "parse_container_tunnel_in",
    "parse_tunnel_in",
    "parse_tunnel_out",
    "resolve_tunnel_host",
    "InteractiveSessionManager",
    "CommandBuilder",
    "UserResolver",
    "UserResolution",
]
