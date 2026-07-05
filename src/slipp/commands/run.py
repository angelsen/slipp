"""Execute run profiles for dev environment orchestration.

Follows the design principle: singular command = action.
Profile management is in runs.py.
"""

import shlex
from typing import Annotated

import typer

from slipp import output
from slipp.models.run import ProxyRoute, RunProfile, TunnelConfig
from slipp.services.run import RunProfileExecutor, RunProfileService
from slipp.services.run.proxy import parse_proxy_spec


RUN_CONTEXT_SETTINGS = {"allow_extra_args": True, "ignore_unknown_options": True}


def run_command(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Profile name or command")],
    cmd: Annotated[
        str | None, typer.Option("--cmd", help="Command (creates/updates profile)")
    ] = None,
    env: Annotated[
        list[str], typer.Option("--env", help="Environment variable KEY=VALUE")
    ] = [],
    vault: Annotated[list[str], typer.Option("--vault", help="Vault project(s)")] = [],
    tunnel_out: Annotated[
        list[str], typer.Option("--tunnel-out", help="Reverse tunnel")
    ] = [],
    tunnel_in: Annotated[
        list[str], typer.Option("--tunnel-in", help="Forward tunnel")
    ] = [],
    proxy: Annotated[
        list[str], typer.Option("--proxy", help="Proxy route (from@host -> to)")
    ] = [],
) -> None:
    """Execute a run profile.

    Supports saved profiles, creating/updating profiles with --cmd,
    and merging runtime options. Pass-through args append to saved commands.

    Args:
        ctx: Typer context for capturing pass-through arguments.
        name: Profile name to execute or create.
        cmd: Command to execute (creates/updates profile if provided).
        env: Environment variables to add (KEY=VALUE format).
        vault: Vault project(s) to include.
        tunnel_out: Reverse tunnels to add (local_port:domain@host).
        tunnel_in: Forward tunnels to add (service:port@host).
        proxy: Proxy routes to add (from@host -> to).

    Raises:
        typer.Exit: If profile not found and --cmd not provided.
    """
    service = RunProfileService()
    executor = RunProfileExecutor()

    if cmd:
        profile = _build_profile(
            cmd, list(env), list(vault), list(tunnel_out), list(tunnel_in), list(proxy)
        )
        _save_profile(name, profile)
        _execute_profile(executor, profile)

    elif service.profile_exists(name):
        profile = service.get_profile(name)
        merged = _merge_runtime_options(
            profile,
            list(env),
            list(vault),
            list(tunnel_out),
            list(tunnel_in),
            list(proxy),
        )

        if ctx.args:
            quoted_args = [shlex.quote(arg) for arg in ctx.args]
            extended_cmd = f"{merged.cmd} {' '.join(quoted_args)}"
            merged = merged.model_copy(update={"cmd": extended_cmd})

        _execute_profile(executor, merged)

    else:
        output.error(f"Profile '{name}' not found")
        output.hint("Use 'slipp runs list' to see saved profiles")
        output.hint('Or create with: slipp run <name> --cmd "..."')
        raise typer.Exit(1)


def _execute_profile(executor: RunProfileExecutor, profile: RunProfile) -> None:
    """Execute profile and propagate the command's exit code."""
    result = executor.execute(profile)
    if result.exit_code != 0:
        raise typer.Exit(result.exit_code)


def _build_profile(
    cmd: str,
    env: list[str],
    vaults: list[str],
    tunnel_out: list[str],
    tunnel_in: list[str],
    proxy: list[str],
) -> RunProfile:
    """Build a RunProfile from command options."""
    tunnels = None
    if tunnel_out or tunnel_in:
        tunnels = TunnelConfig.model_validate({"out": tunnel_out, "in": tunnel_in})

    proxy_routes = []
    for spec in proxy:
        from_url, to_url, host = parse_proxy_spec(spec)
        proxy_routes.append(
            ProxyRoute(**{"from": from_url, "to": to_url, "host": host})
        )

    return RunProfile(
        cmd=cmd, env=env, vaults=vaults, tunnels=tunnels, proxy=proxy_routes
    )


def _save_profile(name: str, profile: RunProfile) -> None:
    """Save profile and display appropriate message."""
    service = RunProfileService()
    is_update = service.profile_exists(name)
    service.save_profile(name, profile)

    if is_update:
        output.info(f"Updated profile '{name}'")
    else:
        output.info(f"Saved profile '{name}'")


def _merge_runtime_options(
    profile: RunProfile,
    env: list[str],
    vault: list[str],
    tunnel_out: list[str],
    tunnel_in: list[str],
    proxy: list[str],
) -> RunProfile:
    """Merge runtime options with saved profile (not persisted).

    Runtime options are added to saved values, not replacing them:
    - env: Appended (CLI values override profile values for same key at execution)
    - vault: Added if not already present
    - tunnels: Added to existing tunnels
    - proxy: Added to existing proxy routes
    """
    if not any([env, vault, tunnel_out, tunnel_in, proxy]):
        return profile

    merged_env = list(profile.env) + list(env)
    merged_vaults = list(profile.vaults) + [v for v in vault if v not in profile.vaults]

    merged_tunnels = profile.tunnels
    if tunnel_out or tunnel_in:
        existing_out = merged_tunnels.out if merged_tunnels else []
        existing_in = merged_tunnels.in_ if merged_tunnels else []
        merged_tunnels = TunnelConfig.model_validate(
            {
                "out": list(existing_out) + list(tunnel_out),
                "in": list(existing_in) + list(tunnel_in),
            }
        )

    merged_proxy = list(profile.proxy)
    if proxy:
        for spec in proxy:
            from_url, to_url, host = parse_proxy_spec(spec)
            merged_proxy.append(
                ProxyRoute(**{"from": from_url, "to": to_url, "host": host})
            )

    return RunProfile(
        cmd=profile.cmd,
        env=merged_env,
        vaults=merged_vaults,
        tunnels=merged_tunnels,
        proxy=merged_proxy,
        acme_email=profile.acme_email,
    )
