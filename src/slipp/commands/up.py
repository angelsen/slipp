"""Orchestrated deploy - slipp up composes provision -> hub -> domain -> launch -> dns -> deploy."""

from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import confirm_or_fail, sync_wg_manage_after_deploy
from slipp.commands.dns import sync_and_report
from slipp.commands.provision import provision_or_exit
from slipp.constants import (
    DEFAULT_ENV,
    DEFAULT_SERVICE_USER,
    DEFAULT_SSH_PORT,
    DEFAULT_SSH_USER,
    DnsMode,
)
from slipp.models.deployment import DeploymentHostConfig, InventoryConfig
from slipp.models.service import Runtime
from slipp.services import wg_manage
from slipp.services.config import LocalConfigService
from slipp.services.deploy import run_deploy
from slipp.services.launch import FullContext, run_full_pipeline
from slipp.services.providers import (
    GigahostClient,
    ProviderConfigService,
    ensure_domain_registered,
    get_gigahost_client,
)
from slipp.utils.errors import DeployError, LaunchError, ProviderError


class _StepCounter:
    """Numbered progress output shared across the up flow's stages."""

    def __init__(self) -> None:
        self._n = 1

    def __call__(self, message: str) -> None:
        output.info(f"{self._n}. {message}")
        self._n += 1


def _make_hub(step: _StepCounter, name: str, ip: str) -> None:
    """Shell out to wg-deploy's scripts/new-host.sh to hub-ify the host.

    Interactive: ansible-vault may prompt for the vault password (no
    stdout/stderr capture, so the prompt reaches the terminal). A non-zero
    exit -- or a "no" at the confirm -- aborts `up` before launch, since
    launch's `--proxy auto` probe depends on the host actually being a hub.

    Raises:
        typer.Exit: If wg-deploy isn't configured or the user declines.
        WgManageError: If new-host.sh exits non-zero (top-level handler
            reports it).
    """
    wg_deploy = ProviderConfigService.get_wg_deploy()
    if not wg_deploy:
        output.error("wg-deploy is not configured")
        output.hint("Run: slipp providers add wg-deploy")
        raise typer.Exit(1)

    step(f"Making {ip} a wg-manage hub via {wg_deploy.repo_path}...")

    confirm_or_fail(
        f"Run scripts/new-host.sh {name} {ip} in {wg_deploy.repo_path}?",
        decline_message="Hub-ification declined -- aborting (launch needs a hub)",
    )

    wg_manage.make_hub(name, ip, wg_deploy.repo_path)

    output.success(f"{ip} is now a wg-manage hub")


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
    dns: Annotated[DnsMode, typer.Option("--dns", help="DNS handling")] = DnsMode.auto,
    environment: Annotated[
        str, typer.Option("--env", "-e", help="Environment name")
    ] = DEFAULT_ENV,
    hub: Annotated[
        bool,
        typer.Option(
            "--hub",
            help="Make the host a wg-manage hub (via a configured wg-deploy "
            "checkout) before launch, so --proxy auto finds it",
        ),
    ] = False,
) -> None:
    """Provision, register domain, launch, sync DNS, and deploy -- in one command."""
    _client: GigahostClient | None = None

    def get_client() -> GigahostClient:
        nonlocal _client
        if _client is None:
            _client = get_gigahost_client()
        return _client

    step = _StepCounter()

    if host:
        ip = host
        output.info(f"Using existing host: {ip}")
        ssh_user = DEFAULT_SSH_USER
        output.hint(
            f"Assuming SSH user '{DEFAULT_SSH_USER}' -- edit inventory if different"
        )
    else:
        step("Provisioning server...")
        ip = provision_or_exit(get_client(), name)
        ssh_user = DEFAULT_SERVICE_USER

    if hub:
        _make_hub(step, name, ip)

    resolved_domain = domain
    if resolved_domain:
        step(f"Checking domain {resolved_domain}...")
        try:
            ensure_domain_registered(get_client(), resolved_domain)
        except ProviderError as e:
            output.error(f"Domain registration failed: {e}")
            raise typer.Exit(1)

    if not resolved_domain:
        resolved_domain = output.prompt("App domain")

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
                    ansible_port=DEFAULT_SSH_PORT,
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
        sync_and_report(get_client(), resolved_domain, ip)

    step("Deploying...")
    project_root = LocalConfigService.resolve_root()
    try:
        result = run_deploy(project_root, name, environment, tags=None, skip_tags=None)
    except DeployError as e:
        output.error(str(e))
        raise typer.Exit(1)

    if result.exit_code != 0:
        raise typer.Exit(result.exit_code)

    sync_wg_manage_after_deploy(project_root, name)

    output.success("slipp up complete")
