"""Run profile execution service.

Extracts profile execution orchestration from run.py into a service.
Handles the complex workflow of vault loading, tunnel setup, Caddy proxy, and command execution.
"""

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from slipp.models.run import ProxyRoute, RunProfile, TunnelConfig
from slipp.services.run.caddy import CaddyProxy
from slipp.services.ssh import (
    TunnelManager,
    parse_container_tunnel_in,
    parse_tunnel_in,
    parse_tunnel_out,
    resolve_tunnel_host,
)
from slipp.services.vault import (
    merge_vault_envs,
    vault_password_file,
)
from slipp.utils.errors import (
    CaddyProxyError,
    ConfigError,
    ProfileExecutionError,
    TunnelError,
)


def parse_env_vars(env_list: list[str]) -> dict[str, str]:
    """Parse KEY=VALUE strings into dict.

    Args:
        env_list: List of env var strings in KEY=VALUE format

    Returns:
        Dict mapping keys to values

    Raises:
        ConfigError: If env var format is invalid (missing =)
    """
    result: dict[str, str] = {}
    for entry in env_list:
        if "=" not in entry:
            raise ConfigError(f"Invalid env format: '{entry}' (expected KEY=VALUE)")
        key, value = entry.split("=", 1)
        if not key:
            raise ConfigError(f"Invalid env format: '{entry}' (KEY cannot be empty)")
        result[key] = value
    return result


@dataclass
class CaddyCheckResult:
    """Result of Caddy requirements check."""

    hosts_checked: int
    missing_hosts: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.missing_hosts) == 0


@dataclass
class VaultLoadResult:
    """Result of vault secrets loading."""

    env_vars: dict[str, str]
    count: int


@dataclass
class TunnelSetupResult:
    """Result of tunnel setup."""

    tunnel_count: int
    tunnel_out_details: list[tuple[int, str, str]]  # (local_port, domain, host)
    tunnel_in_details: list[tuple[str, int, str]]  # (service, port, host)


@dataclass
class CaddyRouteResult:
    """Result of Caddy route setup."""

    route_count: int
    routes: list[tuple[str, int]]  # (domain, local_port)


@dataclass
class ExecutionResult:
    """Result of profile execution."""

    exit_code: int
    interrupted: bool = False
    error: str | None = None


def run_command(
    cmd: str, cwd: Path | None = None, env: dict[str, str] | None = None
) -> int:
    """Run command, letting Ctrl+C propagate naturally.

    Args:
        cmd: Shell command to execute
        cwd: Working directory
        env: Environment variables to merge

    Returns:
        Exit code from command
    """
    full_env = {**os.environ, **(env or {})}
    process = subprocess.Popen(cmd, shell=True, cwd=cwd, env=full_env)
    return process.wait()


class RunProfileExecutor:
    """Execute run profiles with tunnels, vault, and Caddy proxy.

    This service orchestrates the complex workflow of:
    1. Loading vault secrets into environment
    2. Setting up SSH tunnels (forward and reverse)
    3. Configuring Caddy dev proxy routes
    4. Running the command with proper signal handling
    5. Cleaning up resources on completion/failure

    Note: This service does not produce output. It returns structured results
    that callers can use to display appropriate messages.
    """

    def check_caddy_requirements(self, tunnel_out_specs: list[str]) -> CaddyCheckResult:
        """Check Caddy dev proxy is installed on all tunnel-out hosts.

        Args:
            tunnel_out_specs: List of tunnel-out specs (e.g., "5173:auth.metria.no@metria")

        Returns:
            CaddyCheckResult with check status
        """
        hosts_to_check: dict[str, str] = {}
        for spec in tunnel_out_specs:
            _, _, host_spec = parse_tunnel_out(spec)
            host = resolve_tunnel_host(host_spec)
            if host.ansible_host not in hosts_to_check:
                hosts_to_check[host.ansible_host] = host_spec

        missing: list[str] = []
        for ansible_host, host_spec in hosts_to_check.items():
            host = resolve_tunnel_host(host_spec)
            proxy = CaddyProxy(host)

            if not proxy.is_installed():
                missing.append(host_spec)

        return CaddyCheckResult(
            hosts_checked=len(hosts_to_check),
            missing_hosts=missing,
        )

    def load_vault_secrets(self, vaults: list[str]) -> VaultLoadResult:
        """Load secrets from vault(s) into environment dict.

        Args:
            vaults: List of vault project names

        Returns:
            VaultLoadResult with environment variables

        Raises:
            DuplicateEnvVarError: If duplicate env vars found across vaults
            VaultDecryptError: If vault decryption fails
        """
        with vault_password_file(confirm=False) as pw_file:
            env = merge_vault_envs(vaults, pw_file)
        return VaultLoadResult(env_vars=env, count=len(env))

    def setup_tunnels(
        self, tunnels: TunnelConfig
    ) -> tuple[TunnelManager, TunnelSetupResult]:
        """Setup SSH tunnels.

        Args:
            tunnels: Tunnel configuration

        Returns:
            Tuple of (TunnelManager, TunnelSetupResult)

        Raises:
            TunnelError: If tunnel setup fails
        """
        tunnel_manager = TunnelManager()
        tunnel_out_details: list[tuple[int, str, str]] = []
        tunnel_in_details: list[tuple[str, int, str]] = []

        # Track created tunnels: (port, host) -> first domain (for logging)
        created_tunnels: dict[tuple[int, str], str] = {}

        try:
            for spec in tunnels.out:
                local_port, domain, host_spec = parse_tunnel_out(spec)
                host = resolve_tunnel_host(host_spec)

                tunnel_key = (local_port, host.ansible_host)
                if tunnel_key not in created_tunnels:
                    tunnel_manager.start_tunnel_out(local_port, domain, host)
                    created_tunnels[tunnel_key] = domain

                tunnel_out_details.append((local_port, domain, host.ansible_host))

            for spec in tunnels.in_:
                container_spec = parse_container_tunnel_in(spec)
                if container_spec:
                    runtime, container, remote_port, local_port, host_spec = container_spec
                    host = resolve_tunnel_host(host_spec)
                    tunnel_manager.start_container_tunnel_in(
                        runtime, container, remote_port, local_port, host
                    )
                    tunnel_in_details.append(
                        (f"{runtime}://{container}", local_port, host.ansible_host)
                    )
                else:
                    service, remote_port, host_spec = parse_tunnel_in(spec)
                    host = resolve_tunnel_host(host_spec)
                    tunnel_manager.start_tunnel_in(service, remote_port, host)
                    tunnel_in_details.append((service, remote_port, host.ansible_host))

            result = TunnelSetupResult(
                tunnel_count=len(tunnel_manager.processes),
                tunnel_out_details=tunnel_out_details,
                tunnel_in_details=tunnel_in_details,
            )
            return tunnel_manager, result

        except TunnelError:
            tunnel_manager.cleanup()
            raise

    def setup_caddy_routes(
        self,
        tunnel_out_specs: list[str],
        caddy_proxies: dict[str, CaddyProxy],
    ) -> CaddyRouteResult:
        """Setup Caddy dev proxy routes for tunnel-out specs.

        Args:
            tunnel_out_specs: List of tunnel-out specs
            caddy_proxies: Dict to populate with CaddyProxy instances

        Returns:
            CaddyRouteResult with route details

        Raises:
            CaddyProxyError: If route setup fails
        """
        routes: list[tuple[str, int]] = []

        for spec in tunnel_out_specs:
            local_port, domain, host_spec = parse_tunnel_out(spec)
            host = resolve_tunnel_host(host_spec)

            if host.ansible_host not in caddy_proxies:
                caddy_proxies[host.ansible_host] = CaddyProxy(host)

            proxy = caddy_proxies[host.ansible_host]
            proxy.add_route(domain, local_port)
            routes.append((domain, local_port))

        return CaddyRouteResult(route_count=len(routes), routes=routes)

    def setup_proxy_routes(
        self,
        proxy_routes: list[ProxyRoute],
        caddy_proxies: dict[str, CaddyProxy],
    ) -> None:
        """Setup proxy routes, resolving host for each route.

        Args:
            proxy_routes: List of proxy routes to configure
            caddy_proxies: Dict to populate with CaddyProxy instances

        Raises:
            CaddyProxyError: If route setup fails
        """
        for route in proxy_routes:
            host = resolve_tunnel_host(route.host)

            if host.ansible_host not in caddy_proxies:
                caddy_proxies[host.ansible_host] = CaddyProxy(host)

            proxy = caddy_proxies[host.ansible_host]
            proxy.add_proxy_route(
                route.from_domain,
                route.from_path,
                route.to_host,
                route.to_path,
            )

    def execute(self, profile: RunProfile, name: str) -> ExecutionResult:
        """Execute profile, return result.

        Args:
            profile: Run profile configuration
            name: Profile name (for display)

        Returns:
            ExecutionResult with exit code and status

        Raises:
            ProfileExecutionError: If Caddy requirements not met
            ConfigError: If env var format is invalid
            DuplicateEnvVarError: If duplicate env vars found
            VaultDecryptError: If vault decryption fails
            TunnelError: If tunnel setup fails
            CaddyProxyError: If Caddy route setup fails
        """
        if profile.tunnels and profile.tunnels.out:
            check_result = self.check_caddy_requirements(profile.tunnels.out)
            if not check_result.success:
                raise ProfileExecutionError(
                    f"Dev proxy not installed on: {', '.join(check_result.missing_hosts)}\n"
                    f"Run: slipp bootstrap <host> proxy --email <email>"
                )

        env: dict[str, str] = {}
        tunnel_manager: TunnelManager | None = None
        caddy_proxies: dict[str, CaddyProxy] = {}

        try:
            if profile.vaults:
                vault_result = self.load_vault_secrets(profile.vaults)
                env = vault_result.env_vars

            if profile.env:
                cli_env = parse_env_vars(profile.env)
                env = {**env, **cli_env}

            if profile.tunnels and (profile.tunnels.out or profile.tunnels.in_):
                tunnel_manager, _ = self.setup_tunnels(profile.tunnels)

                if profile.tunnels.out:
                    self.setup_caddy_routes(profile.tunnels.out, caddy_proxies)

            if profile.proxy:
                self.setup_proxy_routes(profile.proxy, caddy_proxies)

            exit_code = run_command(profile.cmd, env=env)

            return ExecutionResult(exit_code=exit_code)

        except KeyboardInterrupt:
            return ExecutionResult(exit_code=130, interrupted=True)

        except (TunnelError, CaddyProxyError):
            for proxy in caddy_proxies.values():
                proxy.cleanup()
            if tunnel_manager:
                tunnel_manager.cleanup()
            raise

        finally:
            for proxy in caddy_proxies.values():
                proxy.cleanup()
            if tunnel_manager:
                tunnel_manager.cleanup()

    def cleanup(
        self,
        caddy_proxies: dict[str, CaddyProxy],
        tunnel_manager: TunnelManager | None,
    ) -> None:
        """Cleanup Caddy routes and tunnels.

        Args:
            caddy_proxies: Dict of CaddyProxy instances to cleanup
            tunnel_manager: TunnelManager to cleanup (if set)
        """
        for proxy in caddy_proxies.values():
            proxy.cleanup()

        if tunnel_manager:
            tunnel_manager.cleanup()
