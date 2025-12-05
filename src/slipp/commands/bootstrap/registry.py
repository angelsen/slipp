"""Registry authentication bootstrap commands."""

import os
from typing import Annotated

import typer

from slipp import output
from slipp.services.config import HostResolver
from slipp.services.ssh import SSHService
from slipp.utils.errors import HostNotFoundError

registry_app = typer.Typer(name="registry", help="Setup container registry auth on VPS")


def _bootstrap_registry(
    registry_url: str,
    registry_name: str,
    host: str | None,
    user: str | None,
    token: str | None,
    token_env_var: str,
) -> None:
    """Common registry bootstrap logic."""
    resolver = HostResolver()

    try:
        if host:
            ssh_config = resolver.by_project(host)
        else:
            ssh_config = resolver.current()
    except HostNotFoundError as e:
        output.error(str(e))
        output.hint("Specify --host <project> or run from project directory")
        raise typer.Exit(1)

    if not user:
        user = output.prompt(f"{registry_name} username")

    if not token:
        token = os.environ.get(token_env_var)
        if not token:
            token = output.prompt_password(f"{registry_name} token")

    if not user or not token:
        output.error("Username and token required")
        raise typer.Exit(1)

    target = f"{ssh_config.ansible_user}@{ssh_config.ansible_host}"
    output.info(f"Setting up {registry_name} auth on {target}")

    with SSHService(ssh_config) as ssh:
        # Use stdin to avoid token in process list
        cmd = f"echo '{token}' | docker login {registry_url} -u {user} --password-stdin"
        result = ssh.execute(cmd)

        if "Login Succeeded" in result or "Authenticating" in result:
            output.success(f"{registry_name} authentication configured")
        else:
            output.error("Authentication failed")
            output.hint(result.strip())
            raise typer.Exit(1)


@registry_app.command(name="ghcr")
def ghcr_command(
    host: Annotated[
        str | None, typer.Option("--host", help="Target host/project")
    ] = None,
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
        host=host,
        user=user,
        token=token,
        token_env_var="GITHUB_TOKEN",
    )


@registry_app.command(name="dockerhub")
def dockerhub_command(
    host: Annotated[
        str | None, typer.Option("--host", help="Target host/project")
    ] = None,
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
        host=host,
        user=user,
        token=token,
        token_env_var="DOCKER_TOKEN",
    )
