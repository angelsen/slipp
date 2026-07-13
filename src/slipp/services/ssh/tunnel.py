"""SSH tunnel manager for dev environment orchestration.

Manages SSH tunnels for:
- Reverse tunnels (tunnel-out): Expose local port to remote
- Forward tunnels (tunnel-in): Pull remote service to local
- Container tunnels (tunnel-in): Pull Docker/Podman container service to local
"""

import re
import shlex
import socket
import subprocess
import time

from slipp.models.host import AnsibleHost
from slipp.services.ssh.client import SSHService
from slipp.services.ssh.command import build_ssh_command, build_vps_command
from slipp.utils.errors import (
    SSHAuthenticationError,
    SSHCommandError,
    SSHConnectionError,
    TunnelError,
)

# Pattern for container tunnel specs: docker://container:port:local@host
CONTAINER_TUNNEL_PATTERN = re.compile(r"^(docker|podman)://([^:]+):(\d+):(\d+)@(.+)$")


def parse_tunnel_out(spec: str) -> tuple[int, str, str]:
    """Parse tunnel-out spec: 'local_port:domain@host'.

    Args:
        spec: Tunnel spec string like '5173:auth.metria.no@metria'

    Returns:
        Tuple of (local_port, domain, host_spec)

    Raises:
        TunnelError: If spec is invalid
    """
    try:
        port_part, rest = spec.split(":", 1)
        domain, host = rest.rsplit("@", 1)
        return int(port_part), domain, host
    except ValueError as e:
        raise TunnelError(
            f"Invalid tunnel-out spec: {spec}\n"
            f"Expected format: local_port:domain@host (e.g., 5173:auth.metria.no@metria)"
        ) from e


def parse_tunnel_in(spec: str) -> tuple[str, int, str]:
    """Parse tunnel-in spec: 'service:port@host'.

    Args:
        spec: Tunnel spec string like 'postgres:5432@metria'

    Returns:
        Tuple of (service, port, host_spec)

    Raises:
        TunnelError: If spec is invalid
    """
    try:
        service, rest = spec.split(":", 1)
        port_str, host = rest.rsplit("@", 1)
        return service, int(port_str), host
    except ValueError as e:
        raise TunnelError(
            f"Invalid tunnel-in spec: {spec}\n"
            f"Expected format: service:port@host (e.g., postgres:5432@metria)"
        ) from e


def parse_container_tunnel_in(spec: str) -> tuple[str, str, int, int, str] | None:
    """Parse container tunnel-in spec: 'docker://container:port:local@host'.

    Args:
        spec: Tunnel spec string like 'docker://matrix-synapse:8008:8008@metria'

    Returns:
        Tuple of (runtime, container, remote_port, local_port, host_spec)
        or None if spec doesn't match container format
    """
    match = CONTAINER_TUNNEL_PATTERN.match(spec)
    if not match:
        return None
    runtime, container, remote_port, local_port, host_spec = match.groups()
    return runtime, container, int(remote_port), int(local_port), host_spec


def is_port_in_use(port: int) -> bool:
    """Check if a local port is in use.

    Args:
        port: Port number to check

    Returns:
        True if port is in use
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


def _spawn_ssh_tunnel(
    forward_args: list[str], host: AnsibleHost, error_context: str
) -> subprocess.Popen[bytes]:
    """Spawn a background SSH tunnel process and verify it started.

    Args:
        forward_args: SSH forwarding flags (e.g. ["-R", "5173:localhost:5173"])
        host: Remote host to tunnel to
        error_context: Description prefixed to the error if the tunnel fails to start

    Returns:
        The spawned subprocess

    Raises:
        TunnelError: If the tunnel process exits immediately
    """
    cmd = build_ssh_command(
        host,
        flags=[
            *forward_args,
            "-N",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ServerAliveInterval=30",
        ],
    )

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    # Poll instead of a single fixed sleep: exits fast on quick failures and
    # tolerates slow SSH handshakes, requiring 1s of continuous life before
    # declaring the tunnel up (bounded by a 3s deadline either way).
    deadline = time.monotonic() + 3.0
    alive_since: float | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            raise TunnelError(f"{error_context}\n{stderr}")
        if alive_since is None:
            alive_since = time.monotonic()
        elif time.monotonic() - alive_since >= 1.0:
            break
        time.sleep(0.1)

    # Tunnel is confirmed up -- stop reserving the stderr pipe for the rest
    # of its (potentially hours-long) life so it can't fill and block ssh.
    if proc.stderr:
        proc.stderr.close()

    return proc


class TunnelManager:
    """Manages SSH tunnel processes.

    Handles starting and cleaning up SSH tunnels for dev environments.
    """

    def __init__(self) -> None:
        self.processes: list[subprocess.Popen[bytes]] = []

    def start_tunnel_out(self, local_port: int, host: AnsibleHost) -> None:
        """Start reverse tunnel: expose local port to remote.

        Creates: ssh -R remote_port:localhost:local_port user@host -N

        Args:
            local_port: Local port to expose
            host: Remote host to tunnel to

        Raises:
            TunnelError: If tunnel fails to start
        """
        proc = _spawn_ssh_tunnel(
            ["-R", f"{local_port}:localhost:{local_port}"],
            host,
            f"Tunnel-out failed to start: localhost:{local_port} → {host.ansible_host}",
        )
        self.processes.append(proc)

    def start_tunnel_in(
        self, service: str, remote_port: int, host: AnsibleHost
    ) -> None:
        """Start forward tunnel: pull remote service to local.

        Creates: ssh -L local_port:service:remote_port user@host -N

        Args:
            service: Remote service name/IP
            remote_port: Remote port
            host: Remote host to tunnel through

        Raises:
            TunnelError: If tunnel fails to start or local port in use
        """
        if is_port_in_use(remote_port):
            raise TunnelError(
                f"Local port {remote_port} already in use\n"
                f"Hint: Stop the local service or use a different port"
            )

        proc = _spawn_ssh_tunnel(
            ["-L", f"{remote_port}:{service}:{remote_port}"],
            host,
            f"Tunnel-in failed to start: {service}:{remote_port} via {host.ansible_host}",
        )
        self.processes.append(proc)

    def start_container_tunnel_in(
        self,
        runtime: str,
        container: str,
        remote_port: int,
        local_port: int,
        host: AnsibleHost,
    ) -> None:
        """Start forward tunnel to Docker/Podman container.

        Resolves container IP via inspect, then creates standard SSH forward.

        Args:
            runtime: Container runtime ('docker' or 'podman')
            container: Container name
            remote_port: Port inside container
            local_port: Local port to bind
            host: Remote host to tunnel through

        Raises:
            TunnelError: If tunnel fails to start or container not found
        """
        if is_port_in_use(local_port):
            raise TunnelError(
                f"Local port {local_port} already in use\n"
                f"Hint: Stop the local service or use a different port"
            )

        # Resolve container IP via SSH, escalating to root for docker/podman
        # socket access. Add space separator to handle containers on
        # multiple networks.
        inspect_cmd = build_vps_command(
            "root",
            f"{runtime} inspect -f "
            f'"{{{{range.NetworkSettings.Networks}}}}{{{{.IPAddress}}}} {{{{end}}}}" '
            f"{shlex.quote(container)}",
            host.ansible_user,
        )

        try:
            with SSHService(host) as ssh:
                result = (
                    ssh.execute(inspect_cmd)
                    .check(f"Failed to inspect container '{container}'")
                    .stdout.strip()
                    .strip('"')
                )
                # Take first IP if container is on multiple networks
                container_ip = result.split()[0] if result.split() else ""
        except (SSHConnectionError, SSHAuthenticationError, SSHCommandError) as e:
            raise TunnelError(
                f"Failed to get IP for container '{container}' on {host.ansible_host}\n"
                f"{e}"
            ) from e
        if not container_ip or not container_ip[0].isdigit():
            raise TunnelError(
                f"Could not resolve IP for container '{container}'\n"
                f"Got: {result[:100] if result else '(empty)'}\n"
                f"Hint: Make sure the container is running and docker is accessible"
            )

        # Start SSH forward to container IP
        proc = _spawn_ssh_tunnel(
            ["-L", f"{local_port}:{container_ip}:{remote_port}"],
            host,
            f"Container tunnel failed to start: {container}:{remote_port} via {host.ansible_host}\n"
            f"Container IP: {container_ip}",
        )
        self.processes.append(proc)

    def cleanup(self) -> None:
        """Terminate all tunnel processes."""
        for proc in self.processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

        self.processes.clear()

    def __enter__(self) -> "TunnelManager":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.cleanup()
