"""Run profile execution.

Handles the complex workflow of vault loading, tunnel setup, Caddy proxy, and command execution.
"""

import os
import subprocess
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path

from slipp import output
from slipp.models.host import AnsibleHost
from slipp.models.run import ProxyRoute, RunProfile, TunnelConfig
from slipp.services.config import HostResolver
from slipp.services.run.caddy import CaddyProxy
from slipp.services.ssh import (
    TunnelManager,
    parse_container_tunnel_in,
    parse_tunnel_in,
    parse_tunnel_out,
)
from slipp.services.vault import (
    merge_vault_envs,
    vault_password_file,
)
from slipp.utils.errors import (
    ConfigError,
    HostNotFoundError,
    ProfileExecutionError,
    SSHAuthenticationError,
    SSHConnectionError,
    TunnelError,
)


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
    except (ConfigError, HostNotFoundError):
        pass

    output.warning(
        f"'{host_spec}' isn't a registered project, assuming slipp@{host_spec}"
    )
    return AnsibleHost(
        inventory_hostname=host_spec,
        ansible_host=host_spec,
        ansible_user="slipp",
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
class ResolvedTunnelOut:
    """Pre-parsed tunnel-out spec with resolved host."""

    local_port: int
    domain: str
    host_spec: str
    host: AnsibleHost


def resolve_tunnel_out_specs(specs: list[str]) -> list[ResolvedTunnelOut]:
    """Parse and resolve tunnel-out specs once for reuse across methods."""
    resolved: list[ResolvedTunnelOut] = []
    for spec in specs:
        local_port, domain, host_spec = parse_tunnel_out(spec)
        host = resolve_tunnel_host(host_spec)
        resolved.append(ResolvedTunnelOut(local_port, domain, host_spec, host))
    return resolved


@dataclass
class CaddyCheckResult:
    """Result of Caddy requirements check."""

    missing_hosts: list[str] = field(default_factory=list)
    unreachable_hosts: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.missing_hosts and not self.unreachable_hosts


def run_shell_command(
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
    # shell=True is deliberate: `cmd` is the user's own dev command from their
    # local run profile (e.g. "npm run dev"), run locally as themselves --
    # same trust boundary as typing it at a shell prompt.
    process = subprocess.Popen(cmd, shell=True, cwd=cwd, env=full_env)
    return process.wait()


def _check_caddy_requirements(
    resolved: list[ResolvedTunnelOut],
    caddy_proxies: dict[str, CaddyProxy],
    stack: ExitStack,
) -> CaddyCheckResult:
    """Check Caddy dev proxy is installed on all tunnel-out hosts.

    Populates `caddy_proxies` with the checked instances (via
    `_get_or_create_proxy`, deduped by host) so `_setup_caddy_routes`
    reuses the same SSH connection instead of opening a second one per
    host. Safe to cache even on a failed check: `execute_profile` aborts
    before route setup whenever any host is missing/unreachable.
    """
    missing: list[str] = []
    unreachable: list[str] = []
    checked: set[str] = set()

    for r in resolved:
        if r.host.ansible_host in checked:
            continue
        checked.add(r.host.ansible_host)

        proxy = _get_or_create_proxy(r.host, caddy_proxies, stack)
        try:
            if not proxy.is_installed():
                missing.append(r.host_spec)
        except (SSHConnectionError, SSHAuthenticationError) as e:
            unreachable.append(f"{r.host_spec}: {e}")

    return CaddyCheckResult(
        missing_hosts=missing,
        unreachable_hosts=unreachable,
    )


def _load_vault_secrets(vaults: list[str]) -> dict[str, str]:
    """Load secrets from vault(s) into environment dict.

    Args:
        vaults: List of vault project names

    Returns:
        Environment variables from the vaults

    Raises:
        VaultError: If duplicate env vars found across vaults
        VaultDecryptError: If vault decryption fails
    """
    with vault_password_file(confirm=False) as pw_file:
        env = merge_vault_envs(vaults, pw_file)
        output.success(f"Loaded {len(env)} env vars from {', '.join(vaults)}")
        return env


def _setup_tunnels(
    tunnels: TunnelConfig,
    resolved_out: list[ResolvedTunnelOut],
) -> TunnelManager:
    """Setup SSH tunnels."""
    tunnel_manager = TunnelManager()

    created_tunnels: set[tuple[int, str]] = set()

    try:
        for r in resolved_out:
            tunnel_key = (r.local_port, r.host.ansible_host)
            if tunnel_key not in created_tunnels:
                tunnel_manager.start_tunnel_out(r.local_port, r.host)
                created_tunnels.add(tunnel_key)
                output.success(f"Tunnel: localhost:{r.local_port} → {r.domain}")

        for spec in tunnels.in_:
            container_spec = parse_container_tunnel_in(spec)
            if container_spec:
                runtime, container, remote_port, local_port, host_spec = container_spec
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

    except (TunnelError, KeyboardInterrupt):
        tunnel_manager.cleanup()
        raise


def _get_or_create_proxy(
    host: AnsibleHost,
    caddy_proxies: dict[str, CaddyProxy],
    stack: ExitStack,
) -> CaddyProxy:
    """Get the cached CaddyProxy for this host, or create and cache one."""
    if host.ansible_host not in caddy_proxies:
        caddy_proxies[host.ansible_host] = stack.enter_context(CaddyProxy(host))
    return caddy_proxies[host.ansible_host]


def _setup_caddy_routes(
    resolved: list[ResolvedTunnelOut],
    caddy_proxies: dict[str, CaddyProxy],
    stack: ExitStack,
    auth: tuple[str, str] | None = None,
) -> None:
    """Setup Caddy dev proxy routes for pre-resolved tunnel-out specs."""
    for r in resolved:
        proxy = _get_or_create_proxy(r.host, caddy_proxies, stack)
        proxy.add_route(r.domain, r.local_port, auth=auth)
        suffix = f" (auth: {auth[0]})" if auth else ""
        output.success(f"Route: {r.domain} → :{r.local_port}{suffix}")


def _setup_proxy_routes(
    proxy_routes: list[ProxyRoute],
    caddy_proxies: dict[str, CaddyProxy],
    stack: ExitStack,
) -> None:
    """Setup proxy routes, resolving host for each route.

    Args:
        proxy_routes: List of proxy routes to configure
        caddy_proxies: Dict to populate with CaddyProxy instances
        stack: ExitStack that owns cleanup for any CaddyProxy created here

    Raises:
        CaddyProxyError: If route setup fails
    """
    for route in proxy_routes:
        host = resolve_tunnel_host(route.host)
        proxy = _get_or_create_proxy(host, caddy_proxies, stack)
        proxy.add_proxy_route(
            route.from_domain,
            route.from_path,
            route.to_host,
            route.to_path,
        )
        output.success(f"Route: {route.from_domain}{route.from_path} → {route.to_host}")


def execute_profile(profile: RunProfile) -> int:
    """Execute profile, return the command's exit code (130 on Ctrl+C).

    Args:
        profile: Run profile configuration

    Raises:
        ProfileExecutionError: If Caddy requirements not met
        ConfigError: If env var format is invalid
        VaultError: If duplicate env vars found
        VaultDecryptError: If vault decryption fails
        TunnelError: If tunnel setup fails
        CaddyProxyError: If Caddy route setup fails
    """
    resolved_out: list[ResolvedTunnelOut] = []
    if profile.tunnels and profile.tunnels.out:
        resolved_out = resolve_tunnel_out_specs(profile.tunnels.out)

    env: dict[str, str] = {}
    caddy_proxies: dict[str, CaddyProxy] = {}

    try:
        with ExitStack() as stack:
            if resolved_out:
                check_result = _check_caddy_requirements(
                    resolved_out, caddy_proxies, stack
                )
                if not check_result.success:
                    messages = []
                    if check_result.missing_hosts:
                        messages.append(
                            f"Dev proxy not installed on: {', '.join(check_result.missing_hosts)}\n"
                            f"Run: slipp bootstrap <host> proxy --email <email>"
                        )
                    if check_result.unreachable_hosts:
                        messages.append(
                            "Could not reach: "
                            + "; ".join(check_result.unreachable_hosts)
                            + "\nCheck SSH access/keys before bootstrapping"
                        )
                    raise ProfileExecutionError("\n".join(messages))

            if profile.vaults:
                output.info("Loading vault secrets...")
                env = _load_vault_secrets(profile.vaults)

            if profile.env:
                cli_env = parse_env_vars(profile.env)
                env = {**env, **cli_env}

            if profile.tunnels and (resolved_out or profile.tunnels.in_):
                output.info("Setting up tunnels...")
                stack.enter_context(_setup_tunnels(profile.tunnels, resolved_out))

                if resolved_out:
                    output.info("Adding Caddy routes...")
                    auth = None
                    if profile.tunnels.auth:
                        username, password_hash = profile.tunnels.auth.split(":", 1)
                        auth = (username, password_hash)
                    _setup_caddy_routes(resolved_out, caddy_proxies, stack, auth=auth)

            if profile.proxy:
                output.info("Adding proxy routes...")
                _setup_proxy_routes(profile.proxy, caddy_proxies, stack)

            return run_shell_command(profile.cmd, env=env)

    except KeyboardInterrupt:
        return 130
