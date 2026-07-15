"""Execute commands on VPS or in containers.

Commands layer: args → service → output.
Business logic delegated to UserResolver and the ssh.command builders.
"""

from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import (
    find_service_or_exit,
    resolve_host_or_exit,
)
from slipp.services.ssh import (
    SSHService,
    build_container_command,
    build_vps_command,
    hint_ssh_log,
    resolve_user,
)


def exec_command(
    first: Annotated[
        str, typer.Argument(help="Command to execute (or service if two args)")
    ],
    second: Annotated[
        str | None, typer.Argument(help="Command when service specified")
    ] = None,
    user: Annotated[
        str | None,
        typer.Option(
            "--user", "-u", help="Override user (e.g., root, postgres, www-data)"
        ),
    ] = None,
) -> None:
    """Execute a command on VPS or in a container."""
    if second is None:
        command, service_name = first, None
    else:
        service_name, command = first, second

    ssh_config = resolve_host_or_exit(service=service_name, command="exec")

    with SSHService(ssh_config) as ssh:
        service = None
        if service_name:
            service = find_service_or_exit(
                ssh_config, service_name, include_system=False
            )

        resolved_user = resolve_user(ssh, service, user, ssh_config.ansible_user)

        if service and service.runtime.is_container():
            exec_cmd = build_container_command(
                service.name, command, resolved_user, service.runtime
            )
            context_msg = f"container {service.name}"
        else:
            exec_cmd = build_vps_command(
                resolved_user, command, ssh_config.ansible_user
            )
            context_msg = "VPS"

        output.blank()
        output.info(
            f"Executing on {ssh_config.ansible_host} ({context_msg}, as {resolved_user})"
        )
        output.info(f"Command: {command}")
        output.blank()

        # Prompt before running rather than after failing (only leading
        # sudo is rewritten for password piping; embedded sudo is a non-goal)
        if exec_cmd.startswith("sudo "):
            ssh.ensure_sudo("Executing command")

        result = ssh.execute(exec_cmd)
        ssh.check_sudo(result, "Executing command")

        if result.text.strip():
            output.stdout(result.text)
        else:
            output.info("(no output)")

        if not result.ok:
            output.blank()
            output.error(f"Command failed (exit {result.exit_code})")

            if SSHService.is_permission_denied(result):
                output.blank()
                output.hint("Hint: Try running as root: slipp exec -u root ...")

            hint_ssh_log()

            raise typer.Exit(result.exit_code)

        output.blank()
        output.success("Command completed successfully")
