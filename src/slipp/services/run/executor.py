"""Run profile execution service.

Extracts profile execution orchestration from run.py into a service.
Handles the complex workflow of vault loading, tunnel setup, Caddy proxy, and command execution.
"""

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from slipp import output
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
class ExecutionResult:
    """Result of profile execution."""

    exit_code: int


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

    def load_vault_secrets(self, vaults: list[str]) -> dict[str, str]:
        """Load secrets from vault(s) into environment dict.

        Args:
            vaults: List of vault project names

        Returns:
            Environment variables from the vaults

        Raises:
            DuplicateEnvVarError: If duplicate env vars found across vaults
            VaultDecryptError: If vault decryption fails
        """
        with vault_password_file(confirm=False) as pw_file:
            env = merge_vault_envs(vaults, pw_file)
            output.success(f"Loaded {len(env)} env vars from {', '.join(vaults)}")
            return env

    def setup_tunnels(self, tunnels: TunnelConfig) -> TunnelManager:
        """Setup SSH tunnels.

        Args:
            tunnels: Tunnel configuration

        Returns:
            TunnelManager owning the started tunnels

        Raises:
            TunnelError: If tunnel setup fails
        """
        tunnel_manager = TunnelManager()

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
                    output.success(f"Tunnel: localhost:{local_port} → {domain}")

            for spec in tunnels.in_:
                container_spec = parse_container_tunnel_in(spec)
                if container_spec:
                    runtime, container, remote_port, local_port, host_spec = (
                        container_spec
                    )
                    host = resolve_tunnel_host(host_spec)
                    tunnel_manager.start_container_tunnel_in(
                        runtime, container, remote_port, local_port, host
                    )
                    output.success(
                        f"Tunnel: localhost:{local_port} ← {container}:{remote_port}@{host_spec}"
                    )
                else:
                    service, remote_port, host_spec = parse_tunnel_in(spec)
                    host = resolve_tunnel_host(host_spec)
                    tunnel_manager.start_tunnel_in(service, remote_port, host)
                    output.success(
                        f"Tunnel: localhost:{remote_port} ← {service}@{host_spec}"
                    )

            return tunnel_manager

        except TunnelError:
            tunnel_manager.cleanup()
            raise

    def setup_caddy_routes(
        self,
        tunnel_out_specs: list[str],
        caddy_proxies: dict[str, CaddyProxy],
        auth: tuple[str, str] | None = None,
    ) -> None:
        """Setup Caddy dev proxy routes for tunnel-out specs.

        Args:
            tunnel_out_specs: List of tunnel-out specs
            caddy_proxies: Dict to populate with CaddyProxy instances
            auth: Optional (username, bcrypt-hash) for HTTP basic auth on all routes

        Raises:
            CaddyProxyError: If route setup fails
        """
        for spec in tunnel_out_specs:
            local_port, domain, host_spec = parse_tunnel_out(spec)
            host = resolve_tunnel_host(host_spec)

            if host.ansible_host not in caddy_proxies:
                caddy_proxies[host.ansible_host] = CaddyProxy(host)

            proxy = caddy_proxies[host.ansible_host]
            proxy.add_route(domain, local_port, auth=auth)
            suffix = f" (auth: {auth[0]})" if auth else ""
            output.success(f"Route: {domain} → :{local_port}{suffix}")

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
            output.success(
                f"Route: {route.from_domain}{route.from_path} → {route.to_host}"
            )

    def execute(self, profile: RunProfile) -> ExecutionResult:
        """Execute profile, return result.

        Args:
            profile: Run profile configuration

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
                output.info("Loading vault secrets...")
                env = self.load_vault_secrets(profile.vaults)

            if profile.env:
                cli_env = parse_env_vars(profile.env)
                env = {**env, **cli_env}

            if profile.tunnels and (profile.tunnels.out or profile.tunnels.in_):
                output.info("Setting up tunnels...")
                tunnel_manager = self.setup_tunnels(profile.tunnels)

                if profile.tunnels.out:
                    output.info("Adding Caddy routes...")
                    auth = None
                    if profile.tunnels.auth:
                        username, password_hash = profile.tunnels.auth.split(":", 1)
                        auth = (username, password_hash)
                    self.setup_caddy_routes(
                        profile.tunnels.out, caddy_proxies, auth=auth
                    )

            if profile.proxy:
                output.info("Adding proxy routes...")
                self.setup_proxy_routes(profile.proxy, caddy_proxies)

            exit_code = run_command(profile.cmd, env=env)

            return ExecutionResult(exit_code=exit_code)

        except KeyboardInterrupt:
            return ExecutionResult(exit_code=130)

        finally:
            for proxy in caddy_proxies.values():
                proxy.cleanup()
            if tunnel_manager:
                tunnel_manager.cleanup()
