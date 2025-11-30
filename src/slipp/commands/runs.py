"""Run profile management commands.

Follows the design principle: plural commands = manage resources.
Provides CRUD operations for run profiles.
"""

from typing import Annotated

import typer

from slipp import output
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
        output.hint('Create one with: ac run <name> --cmd "..."')
        return

    output.blank()
    output.text("Saved profiles:")
    output.blank()

    for name, profile in profiles.items():
        output.text(f"  {name}:")
        output.text(f"    cmd: {profile.cmd}")
        if profile.vaults:
            output.text(f"    vaults: {', '.join(profile.vaults)}")
        if profile.tunnels:
            if profile.tunnels.out:
                for t in profile.tunnels.out:
                    output.text(f"    tunnel-out: {t}")
            if profile.tunnels.in_:
                for t in profile.tunnels.in_:
                    output.text(f"    tunnel-in: {t}")
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
    except ProfileNotFoundError:
        output.error(f"Profile '{name}' not found")
        profiles = service.list_profiles()
        if profiles:
            output.hint(f"Available profiles: {', '.join(profiles.keys())}")
        raise typer.Exit(1)
