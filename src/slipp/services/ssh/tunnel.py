"""SSH tunnel manager for dev environment orchestration.

Manages SSH tunnels for:
- Reverse tunnels (tunnel-out): Expose local port to remote
- Forward tunnels (tunnel-in): Pull remote service to local
- Container tunnels (tunnel-in): Pull Docker/Podman container service to local
"""

import re
import socket
import subprocess
import time
from dataclasses import dataclass

from slipp.models.host import AnsibleHost
from slipp.services.config import HostResolver
from slipp.services.ssh.client import SSHService
from slipp.utils.errors import HostNotFoundError, TunnelError

# Pattern for container tunnel specs: docker://container:port:local@host
CONTAINER_TUNNEL_PATTERN = re.compile(
    r"^(docker|podman)://([^:]+):(\d+):(\d+)@(.+)$"
)


@dataclass
class TunnelSpec:
    """Parsed tunnel specification."""

    local_port: int
    remote_target: str  # domain for out, service for in
    remote_port: int
    host: AnsibleHost


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


def resolve_tunnel_host(host_spec: str) -> AnsibleHost:
    """Resolve host spec to AnsibleHost.

    Supports:
    - Project name from registry (e.g., 'metria')
    - Direct IP/hostname (e.g., '192.168.1.1')

    Args:
        host_spec: Project name or IP/hostname

    Returns:
        AnsibleHost for the target
    """
    resolver = HostResolver()

    try:
        return resolver.by_project(host_spec)
    except HostNotFoundError:
        pass

    return AnsibleHost(
        inventory_hostname=host_spec,
        ansible_host=host_spec,
        ansible_user="root",
    )


def is_port_in_use(port: int) -> bool:
    """Check if a local port is in use.

    Args:
        port: Port number to check

    Returns:
        True if port is in use
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


class TunnelManager:
    """Manages SSH tunnel processes.

    Handles starting and cleaning up SSH tunnels for dev environments.
    """

    def __init__(self) -> None:
        self.processes: list[subprocess.Popen[bytes]] = []
        self._tunnel_info: list[str] = []  # For display

    def start_tunnel_out(self, local_port: int, domain: str, host: AnsibleHost) -> None:
        """Start reverse tunnel: expose local port to remote.

        Creates: ssh -R remote_port:localhost:local_port user@host -N

        Args:
            local_port: Local port to expose
            domain: Domain name (for logging, Caddy will use this later)
            host: Remote host to tunnel to

        Raises:
            TunnelError: If tunnel fails to start
        """
        cmd = [
            "ssh",
            "-R",
            f"{local_port}:localhost:{local_port}",
            "-N",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ServerAliveInterval=30",
            f"{host.ansible_user}@{host.ansible_host}",
        ]

        if host.ansible_port != 22:
            cmd.extend(["-p", str(host.ansible_port)])

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        time.sleep(1.5)
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            raise TunnelError(
                f"Tunnel-out failed to start: localhost:{local_port} → {host.ansible_host}\n"
                f"{stderr}"
            )

        self.processes.append(proc)
        self._tunnel_info.append(
            f"out: localhost:{local_port} → {host.ansible_host}:{local_port} ({domain})"
        )

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

        cmd = [
            "ssh",
            "-L",
            f"{remote_port}:{service}:{remote_port}",
            "-N",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ServerAliveInterval=30",
            f"{host.ansible_user}@{host.ansible_host}",
        ]

        if host.ansible_port != 22:
            cmd.extend(["-p", str(host.ansible_port)])

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        time.sleep(1.5)
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            raise TunnelError(
                f"Tunnel-in failed to start: {service}:{remote_port} via {host.ansible_host}\n"
                f"{stderr}"
            )

        self.processes.append(proc)
        self._tunnel_info.append(
            f"in: {service}:{remote_port} → localhost:{remote_port}"
        )

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

        # Resolve container IP via SSH (use root for docker access)
        # Add space separator to handle containers on multiple networks
        root_host = host.model_copy(update={"ansible_user": "root"})
        inspect_cmd = (
            f'{runtime} inspect -f '
            f'"{{{{range.NetworkSettings.Networks}}}}{{{{.IPAddress}}}} {{{{end}}}}" '
            f'{container}'
        )

        try:
            with SSHService(root_host) as ssh:
                result = ssh.execute(inspect_cmd).strip().strip('"')
                # Take first IP if container is on multiple networks
                container_ip = result.split()[0] if result.split() else ""
        except Exception as e:
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
        cmd = [
            "ssh",
            "-L",
            f"{local_port}:{container_ip}:{remote_port}",
            "-N",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ServerAliveInterval=30",
            f"{host.ansible_user}@{host.ansible_host}",
        ]

        if host.ansible_port != 22:
            cmd.extend(["-p", str(host.ansible_port)])

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        time.sleep(1.5)
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            raise TunnelError(
                f"Container tunnel failed to start: {container}:{remote_port} via {host.ansible_host}\n"
                f"Container IP: {container_ip}\n"
                f"{stderr}"
            )

        self.processes.append(proc)
        self._tunnel_info.append(
            f"in: {runtime}://{container}:{remote_port} → localhost:{local_port}"
        )

    def get_tunnel_info(self) -> list[str]:
        """Get human-readable tunnel info for display."""
        return self._tunnel_info

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
        self._tunnel_info.clear()

    def __enter__(self) -> "TunnelManager":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.cleanup()
