"""Execute commands on VPS or in containers.

Commands layer: args → service → output.
Business logic delegated to UserResolver and CommandBuilder services.
"""

import typer

from slipp import output
from slipp.commands.common import find_service_or_exit, resolve_host_or_exit
from slipp.models.service import Runtime
from slipp.services.ssh import CommandBuilder, SSHService, UserResolver
from slipp.utils.errors import SlippError


def exec_command(
    ctx: typer.Context,
    first: str = typer.Argument(
        ..., help="Command to execute (or service if two args)"
    ),
    second: str | None = typer.Argument(None, help="Command when service specified"),
    user: str | None = typer.Option(
        None, "--user", "-u", help="Override user (e.g., root, postgres, www-data)"
    ),
):
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

        user_resolver = UserResolver(ssh)
        resolution = user_resolver.resolve(service, user, ssh_config.ansible_user)

        if resolution.warning:
            output.warning(resolution.warning)

        if service and Runtime(service.runtime).is_container():
            exec_cmd = CommandBuilder.container_command(
                service.name, command, resolution.user, service.runtime
            )
            context_msg = f"container {service.name}"
        else:
            exec_cmd = CommandBuilder.vps_command(
                resolution.user, command, ssh_config.ansible_user
            )
            context_msg = "VPS"

        output.blank()
        output.info(
            f"Executing on {ssh_config.ansible_host} ({context_msg}, as {resolution.user})"
        )
        output.info(f"Command: {command}")
        output.blank()

        try:
            cmd_output = ssh.execute(exec_cmd)

            if cmd_output.strip():
                output.stdout(cmd_output)
            else:
                output.info("(no output)")

            output.blank()
            output.success("Command completed successfully")

        except SlippError as e:
            output.blank()
            output.error("Command failed")

            error_str = str(e)
            if "Permission denied" in error_str or "not permitted" in error_str:
                output.blank()
                output.hint("Hint: Try running as root: slipp exec -u root ...")

            raise typer.Exit(1)
