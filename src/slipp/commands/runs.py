"""Run profile management commands.

Follows the design principle: plural commands = manage resources.
Provides CRUD operations for run profiles.
"""

import json
from typing import Annotated

import typer

from slipp import output
from slipp.constants import OutputFormat
from slipp.services.run import RunProfileService
from slipp.utils.errors import ProfileNotFoundError


runs_app = typer.Typer(
    name="runs",
    help="Manage run profiles",
)


@runs_app.command(name="list")
def list_profiles() -> None:
    """List all saved run profiles."""
    profiles = RunProfileService().list_profiles()

    if not profiles:
        output.info("No profiles saved")
        output.hint('Create one with: slipp run <name> --cmd "..."')
        return

    if output.get_output_format() == OutputFormat.json:
        data = [
            {"name": name, **profile.model_dump(by_alias=True, exclude_none=True)}
            for name, profile in profiles.items()
        ]
        output.stdout(json.dumps(data, indent=2))
        return

    output.blank()
    output.task("Saved profiles")
    output.blank()

    for name, profile in profiles.items():
        output.bullet(f"{name}:")
        output.kv("cmd", profile.cmd, indent=1)
        if profile.vaults:
            output.kv("vaults", ", ".join(profile.vaults), indent=1)
        if profile.tunnels:
            if profile.tunnels.out:
                for t in profile.tunnels.out:
                    output.kv("tunnel-out", t, indent=1)
            if profile.tunnels.in_:
                for t in profile.tunnels.in_:
                    output.kv("tunnel-in", t, indent=1)
        if profile.proxy:
            for route in profile.proxy:
                output.kv(
                    "proxy", f"{route.from_}@{route.host} -> {route.to}", indent=1
                )
        output.blank()


@runs_app.command(name="remove")
def remove_profile(
    name: Annotated[str, typer.Argument(help="Profile name to remove")],
) -> None:
    """Remove a saved run profile."""
    service = RunProfileService()

    try:
        service.delete_profile(name)
        output.success(f"Removed profile '{name}'")
    except ProfileNotFoundError as e:
        output.error(str(e))
        profiles = service.list_profiles()
        if profiles:
            output.hint(f"Available profiles: {', '.join(profiles.keys())}")
        raise typer.Exit(1)
