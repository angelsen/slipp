"""Execute run profiles for dev environment orchestration.

Follows the design principle: singular command = action.
Profile management is in runs.py.
"""

from typing import Annotated

import typer

from slipp import output
from slipp.models.run import RunProfile
from slipp.services.run import (
    RunProfileService,
    append_extra_args,
    build_profile,
    execute_profile,
    merge_runtime_options,
)
from slipp.services.ssh import hint_ssh_log


RUN_CONTEXT_SETTINGS = {"allow_extra_args": True, "ignore_unknown_options": True}


def run_command(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Profile name or command")],
    cmd: Annotated[
        str | None, typer.Option("--cmd", help="Command (creates/updates profile)")
    ] = None,
    env: Annotated[
        list[str] | None, typer.Option("--env", help="Environment variable KEY=VALUE")
    ] = None,
    vault: Annotated[
        list[str] | None, typer.Option("--vault", help="Vault project(s)")
    ] = None,
    tunnel_out: Annotated[
        list[str] | None, typer.Option("--tunnel-out", help="Reverse tunnel")
    ] = None,
    tunnel_in: Annotated[
        list[str] | None, typer.Option("--tunnel-in", help="Forward tunnel")
    ] = None,
    proxy: Annotated[
        list[str] | None, typer.Option("--proxy", help="Proxy route (from@host -> to)")
    ] = None,
    tunnel_auth: Annotated[
        str | None,
        typer.Option(
            "--tunnel-auth", help="HTTP basic auth for tunnel-out routes (user:pass)"
        ),
    ] = None,
) -> None:
    """Execute a run profile, or create/update one with --cmd."""
    service = RunProfileService()
    env = env or []
    vault = vault or []
    tunnel_out = tunnel_out or []
    tunnel_in = tunnel_in or []
    proxy = proxy or []

    if cmd:
        profile = build_profile(
            cmd, env, vault, tunnel_out, tunnel_in, proxy, tunnel_auth
        )
        _save_profile(service, name, profile)
        _run_profile(append_extra_args(profile, ctx.args))

    elif service.profile_exists(name):
        profile = service.get_profile(name)
        merged = merge_runtime_options(
            profile, env, vault, tunnel_out, tunnel_in, proxy, tunnel_auth
        )

        _run_profile(append_extra_args(merged, ctx.args))

    else:
        output.error(f"Profile '{name}' not found")
        output.hint("Use 'slipp runs list' to see saved profiles")
        output.hint('Or create with: slipp run <name> --cmd "..."')
        raise typer.Exit(1)


def _run_profile(profile: RunProfile) -> None:
    """Execute profile and propagate the command's exit code."""
    exit_code = execute_profile(profile)
    if exit_code != 0:
        hint_ssh_log()
        raise typer.Exit(exit_code)


def _save_profile(service: RunProfileService, name: str, profile: RunProfile) -> None:
    """Save profile and display appropriate message."""
    is_update = service.profile_exists(name)
    service.save_profile(name, profile)

    if is_update:
        output.info(f"Updated profile '{name}'")
    else:
        output.info(f"Saved profile '{name}'")
