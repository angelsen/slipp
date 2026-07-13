"""Container registry auth bootstrap for slipp bootstrap registry."""

import os
import shlex

from slipp import output
from slipp.models.host import AnsibleHost
from slipp.services.ssh import SSHService
from slipp.utils.errors import BootstrapError


def _detect_container_cli(ssh: SSHService) -> str:
    """Find the container CLI on the remote host, preferring podman.

    Args:
        ssh: Connected SSH session.

    Returns:
        "podman" or "docker".

    Raises:
        BootstrapError: If neither binary is on PATH.
    """
    result = ssh.execute("command -v podman || command -v docker")
    if not result.ok or not result.stdout.strip():
        raise BootstrapError(
            "No container runtime found on host (checked podman, docker)"
        )
    return "podman" if "podman" in result.stdout else "docker"


def bootstrap_registry_auth(
    ssh_config: AnsibleHost,
    *,
    registry_url: str,
    registry_name: str,
    user: str | None,
    token: str | None,
    token_env_var: str,
) -> None:
    """Configure container registry auth on a VPS via `podman login`/`docker login`.

    Detects which container CLI is installed on the host (preferring podman)
    and authenticates with that. Resolves missing credentials by checking
    token_env_var, then prompting.

    Args:
        ssh_config: Target host configuration.
        registry_url: Registry hostname (e.g. ghcr.io).
        registry_name: Human-readable registry name for prompts/messages.
        user: Registry username, or None to prompt.
        token: Registry token, or None to resolve from token_env_var/prompt.
        token_env_var: Environment variable to check for the token.

    Raises:
        BootstrapError: If credentials are missing, no container runtime is
            found, or login fails.
    """
    if not user:
        user = output.prompt(f"{registry_name} username")

    if not token:
        token = os.environ.get(token_env_var)
        if not token:
            token = output.prompt_password(f"{registry_name} token")

    if not user or not token:
        raise BootstrapError("Username and token required")

    output.info(f"Setting up {registry_name} auth on {ssh_config.ssh_target}")

    with SSHService(ssh_config) as ssh:
        cli = _detect_container_cli(ssh)

        # Token is piped over the SSH channel's stdin, never appearing in the
        # remote command line (where it would be visible via `ps`/process lists)
        cmd = (
            f"{cli} login {shlex.quote(registry_url)} "
            f"-u {shlex.quote(user)} --password-stdin"
        )
        result = ssh.execute(cmd, stdin_data=token)

        if not result.ok:
            raise BootstrapError(result.text.strip() or "Authentication failed")
