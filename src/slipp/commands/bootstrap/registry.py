"""Registry authentication bootstrap commands."""

from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import ProjectOption, resolve_host_or_exit
from slipp.services.bootstrap import bootstrap_registry_auth
from slipp.services.ssh import hint_ssh_log
from slipp.utils.errors import BootstrapError

registry_app = typer.Typer(name="registry", help="Setup container registry auth on VPS")


def _bootstrap_registry(
    registry_url: str,
    registry_name: str,
    project: str | None,
    user: str | None,
    token: str | None,
    token_env_var: str,
) -> None:
    """Common registry bootstrap logic."""
    ssh_config = resolve_host_or_exit(project=project, command="bootstrap registry")

    try:
        bootstrap_registry_auth(
            ssh_config,
            registry_url=registry_url,
            registry_name=registry_name,
            user=user,
            token=token,
            token_env_var=token_env_var,
        )
    except BootstrapError as e:
        output.error(f"{registry_name} authentication failed")
        output.hint(str(e))
        hint_ssh_log()
        raise typer.Exit(1)

    output.success(f"{registry_name} authentication configured")


@registry_app.command(name="ghcr")
def ghcr_command(
    project: ProjectOption = None,
    user: Annotated[
        str | None, typer.Option("--user", "-u", help="GitHub username")
    ] = None,
    token: Annotated[
        str | None, typer.Option("--token", "-t", help="GitHub PAT")
    ] = None,
) -> None:
    """Setup GitHub Container Registry auth on VPS."""
    _bootstrap_registry(
        registry_url="ghcr.io",
        registry_name="GHCR",
        project=project,
        user=user,
        token=token,
        token_env_var="GITHUB_TOKEN",
    )


@registry_app.command(name="dockerhub")
def dockerhub_command(
    project: ProjectOption = None,
    user: Annotated[
        str | None, typer.Option("--user", "-u", help="Docker Hub username")
    ] = None,
    token: Annotated[
        str | None, typer.Option("--token", "-t", help="Docker Hub token")
    ] = None,
) -> None:
    """Setup Docker Hub auth on VPS."""
    _bootstrap_registry(
        registry_url="docker.io",
        registry_name="Docker Hub",
        project=project,
        user=user,
        token=token,
        token_env_var="DOCKER_TOKEN",
    )
