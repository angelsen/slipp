"""Orchestrated deploy - slipp up composes provision -> domain -> launch -> dns -> deploy."""

from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.commands.deploy import deploy_command
from slipp.services.providers import provision_and_bootstrap, register_domain_interactive
from slipp.constants import DEFAULT_ENV
from slipp.models.deployment import DeploymentHostConfig, InventoryConfig
from slipp.models.service import Runtime
from slipp.services.launch import FullContext, run_full_pipeline
from slipp.services.providers import get_gigahost_client, sync_dns
from slipp.utils.errors import (
    BootstrapError,
    LaunchError,
    ProviderError,
    SSHConnectionError,
)

VALID_DNS_MODES = ["auto", "manual"]


class _StepCounter:
    """Numbered progress output shared across the up flow's stages."""

    def __init__(self) -> None:
        self._n = 1

    def __call__(self, message: str) -> None:
        output.info(f"{self._n}. {message}")
        self._n += 1


def up_command(
    name: Annotated[str, typer.Argument(help="Project name")],
    host: Annotated[
        str | None,
        typer.Option("--host", help="Use an existing host IP (skips provisioning)"),
    ] = None,
    domain: Annotated[
        str | None,
        typer.Option(
            "--domain", help="Domain to register (if available) and deploy to"
        ),
    ] = None,
    dns: Annotated[
        str, typer.Option("--dns", help="DNS handling: auto (default) or manual")
    ] = "auto",
    environment: Annotated[
        str, typer.Option("--env", "-e", help="Environment name")
    ] = DEFAULT_ENV,
) -> None:
    """Provision, register domain, launch, sync DNS, and deploy -- in one command."""
    if dns not in VALID_DNS_MODES:
        output.error(f"--dns must be one of: {', '.join(VALID_DNS_MODES)}")
        raise typer.Exit(1)

    client = get_gigahost_client()
    step = _StepCounter()

    if host:
        ip = host
        output.info(f"Using existing host: {ip}")
        ssh_user = "root"
        output.hint("Assuming SSH user 'root' -- edit inventory if different")
    else:
        step("Provisioning server...")
        try:
            ip, _srv_id = provision_and_bootstrap(client, name)
        except ProviderError as e:
            output.error(f"Provisioning failed: {e}")
            raise typer.Exit(1)
        except (SSHConnectionError, BootstrapError) as e:
            output.error(f"Bootstrap failed: {e}")
            output.hint(
                "Server is provisioned -- retry with: slipp bootstrap account <ip>"
            )
            raise typer.Exit(1)
        ssh_user = "slipp"

    resolved_domain = domain
    if resolved_domain:
        step(f"Checking domain {resolved_domain}...")
        try:
            available, reason = client.check_domain(resolved_domain)
            if available:
                register_domain_interactive(client, resolved_domain)
                output.success(f"Registered {resolved_domain}")
            else:
                output.info(
                    f"{resolved_domain} already registered"
                    + (f": {reason}" if reason else "")
                )
        except ProviderError as e:
            output.error(f"Domain registration failed: {e}")
            raise typer.Exit(1)

    if not resolved_domain:
        resolved_domain = typer.prompt("App domain")

    step("Generating Ansible project...")
    context = FullContext(
        output_dir=Path.cwd(),
        dry_run=False,
        environment=environment,
        project_dirs=[Path.cwd()],
        project_name=name,
        inventory_config=InventoryConfig(
            hosts={
                environment: DeploymentHostConfig(
                    inventory_hostname=environment,
                    ansible_host=ip,
                    ansible_user=ssh_user,
                    ansible_port=22,
                    app_domain=resolved_domain,
                    admin_email=f"admin@{resolved_domain}",
                    runtime=Runtime.DOCKER,
                )
            }
        ),
    )
    try:
        run_full_pipeline(context)
    except LaunchError as e:
        output.error(f"Launch failed: {e}")
        raise typer.Exit(1)

    if dns == "manual":
        step("DNS sync skipped (--dns manual)")
        output.hint(f"Point {resolved_domain} A record to {ip}")
    else:
        step(f"Syncing DNS for {resolved_domain}...")
        try:
            if client.find_zone(resolved_domain) is None:
                client.create_zone(resolved_domain)
            changes = sync_dns(client, resolved_domain, ip)
        except ProviderError as e:
            output.error(f"DNS sync failed: {e}")
            raise typer.Exit(1)

        if changes:
            for change in changes:
                output.success(change)
        else:
            output.info("DNS already up to date")

    step("Deploying...")
    deploy_command(target=environment)

    output.success(f"slipp up complete -- https://{resolved_domain}")


__all__ = ["up_command"]
