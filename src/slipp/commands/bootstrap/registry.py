"""Registry authentication bootstrap commands."""

import os
import shlex
from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import resolve_host_or_exit
from slipp.services.ssh import SSHService, hint_ssh_log

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
    ssh_config = resolve_host_or_exit(project=project)

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
        # Token is piped over the SSH channel's stdin, never appearing in the
        # remote command line (where it would be visible via `ps`/process lists)
        cmd = (
            f"docker login {shlex.quote(registry_url)} "
            f"-u {shlex.quote(user)} --password-stdin"
        )
        result = ssh.execute(cmd, stdin_data=token)

        if result.ok:
            output.success(f"{registry_name} authentication configured")
        else:
            output.error("Authentication failed")
            output.hint(result.text.strip())
            hint_ssh_log()
            raise typer.Exit(1)


@registry_app.command(name="ghcr")
def ghcr_command(
    project: Annotated[
        str | None, typer.Option("--project", "-p", help="Project name")
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
        project=project,
        user=user,
        token=token,
        token_env_var="GITHUB_TOKEN",
    )


@registry_app.command(name="dockerhub")
def dockerhub_command(
    project: Annotated[
        str | None, typer.Option("--project", "-p", help="Project name")
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
        project=project,
        user=user,
        token=token,
        token_env_var="DOCKER_TOKEN",
    )
