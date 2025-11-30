"""Run command - dev environment orchestration.

Follows the design principle: singular command = action.
Executes run profiles. Profile management is in runs.py.

Supports:
- Saved profiles: `ac run dev`
- Create/update profiles: `ac run dev --cmd "npm run dev"`
- Runtime env merging: `ac run dev --env EXTRA=val`
- Pass-through args: `ac run python script.py` (appends to saved cmd)
"""

import shlex
from typing import Annotated

import typer

from slipp import output
from slipp.models.run import RunProfile, TunnelConfig
from slipp.services.run import RunProfileExecutor, RunProfileService
from slipp.utils.errors import ConfigError


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
) -> None:
    """Execute a run profile."""
    service = RunProfileService()
    executor = RunProfileExecutor()

    if cmd:
        profile = _build_profile(
            cmd, list(env), list(vault), list(tunnel_out), list(tunnel_in)
        )
        _save_profile(name, profile)
        _execute_profile(executor, profile, name)

    elif service.profile_exists(name):
        profile = service.get_profile(name)
        merged = _merge_runtime_options(
            profile, list(env), list(vault), list(tunnel_out), list(tunnel_in)
        )

        if ctx.args:
            quoted_args = [shlex.quote(arg) for arg in ctx.args]
            extended_cmd = f"{merged.cmd} {' '.join(quoted_args)}"
            merged = merged.model_copy(update={"cmd": extended_cmd})

        _execute_profile(executor, merged, name)

    else:
        output.error(f"Profile '{name}' not found")
        output.hint("Use 'ac runs list' to see saved profiles")
        output.hint('Or create with: ac run <name> --cmd "..."')
        raise typer.Exit(1)


def _execute_profile(
    executor: RunProfileExecutor, profile: RunProfile, name: str
) -> None:
    """Execute profile with error handling."""
    try:
        executor.execute(profile, name)
    except ConfigError as e:
        output.error(str(e))
        raise typer.Exit(1)


def _build_profile(
    cmd: str,
    env: list[str],
    vaults: list[str],
    tunnel_out: list[str],
    tunnel_in: list[str],
) -> RunProfile:
    """Build a RunProfile from command options."""
    tunnels = None
    if tunnel_out or tunnel_in:
        tunnels = TunnelConfig.model_validate({"out": tunnel_out, "in": tunnel_in})

    return RunProfile(cmd=cmd, env=env, vaults=vaults, tunnels=tunnels)


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
) -> RunProfile:
    """Merge runtime options with saved profile (not persisted).

    Runtime options are added to saved values, not replacing them:
    - env: Appended (CLI values override profile values for same key at execution)
    - vault: Added if not already present
    - tunnels: Added to existing tunnels
    """
    if not any([env, vault, tunnel_out, tunnel_in]):
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

    return RunProfile(
        cmd=profile.cmd,
        env=merged_env,
        vaults=merged_vaults,
        tunnels=merged_tunnels,
        acme_email=profile.acme_email,
    )
