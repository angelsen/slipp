"""SSH and remote execution services.

This package provides services for SSH connections, tunnels, and remote execution.
"""

from slipp.services.ssh.client import SSHService
from slipp.services.ssh.command import CommandBuilder
from slipp.services.ssh.session import InteractiveSessionManager
from slipp.services.ssh.tunnel import (
    TunnelManager,
    TunnelSpec,
    is_port_in_use,
    parse_tunnel_in,
    parse_tunnel_out,
    resolve_tunnel_host,
)
from slipp.services.ssh.user import UserResolution, UserResolver

__all__ = [
    "SSHService",
    "TunnelManager",
    "TunnelSpec",
    "parse_tunnel_in",
    "parse_tunnel_out",
    "resolve_tunnel_host",
    "is_port_in_use",
    "InteractiveSessionManager",
    "CommandBuilder",
    "UserResolver",
    "UserResolution",
]
