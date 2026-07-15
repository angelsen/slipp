"""Orchestrated deploy - slipp up composes provision -> hub -> domain -> launch -> dns -> deploy."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from slipp import output
from slipp.commands.common import (
    confirm_or_fail,
    run_deploy_or_exit,
    sync_wg_manage_after_deploy,
)
from slipp.commands.dns import sync_and_report
from slipp.commands.provision import provision_or_exit
from slipp.constants import (
    DEFAULT_ENV,
    DEFAULT_SERVICE_USER,
    DEFAULT_SSH_USER,
    DnsMode,
)
from slipp.services.config import LocalConfigService
from slipp.services.deploy import DeployOverrides
from slipp.services.launch import build_context_for_provisioned_host, run_full_pipeline
from slipp.services.providers import (
    GigahostClient,
    ProviderConfigService,
    ensure_domain_registered,
    get_gigahost_client,
)
from slipp.services.providers.wg_deploy import make_hub as make_wg_deploy_hub
from slipp.utils.errors import LaunchError, ProviderError


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

    make_wg_deploy_hub(name, ip, wg_deploy.repo_path)

    output.success(f"{ip} is now a wg-manage hub")


def _resolve_ip(
    step: _StepCounter,
    host: str | None,
    name: str,
    get_client: Callable[[], GigahostClient],
) -> tuple[str, str]:
    """Provision a new server, or use --host as-is. Returns (ip, ssh_user)."""
    if host:
        output.info(f"Using existing host: {host}")
        output.hint(
            f"Assuming SSH user '{DEFAULT_SSH_USER}' -- edit inventory if different"
        )
        return host, DEFAULT_SSH_USER

    step("Provisioning server...")
    ip = provision_or_exit(get_client(), name)
    return ip, DEFAULT_SERVICE_USER


def _resolve_domain(
    step: _StepCounter, get_client: Callable[[], GigahostClient], domain: str | None
) -> str:
    """Register/verify --domain if given, else prompt for one."""
    if not domain:
        return output.prompt("App domain")

    step(f"Checking domain {domain}...")
    try:
        ensure_domain_registered(get_client(), domain)
    except ProviderError as e:
        output.error(f"Domain registration failed: {e}")
        raise typer.Exit(1) from e
    return domain


def _run_launch_and_dns(
    step: _StepCounter,
    ip: str,
    ssh_user: str,
    resolved_domain: str,
    environment: str,
    name: str,
    dns: DnsMode,
    get_client: Callable[[], GigahostClient],
) -> None:
    """Generate and run the launch pipeline, then sync (or skip) DNS."""
    step("Generating Ansible project...")
    context = build_context_for_provisioned_host(
        output_dir=Path.cwd(),
        environment=environment,
        project_name=name,
        ip=ip,
        ssh_user=ssh_user,
        resolved_domain=resolved_domain,
    )
    try:
        run_full_pipeline(context)
    except LaunchError as e:
        output.error(f"Launch failed: {e}")
        raise typer.Exit(1) from e

    if dns == DnsMode.manual:
        step("DNS sync skipped (--dns manual)")
        output.hint(f"Point {resolved_domain} A record to {ip}")
    else:
        step(f"Syncing DNS for {resolved_domain}...")
        sync_and_report(get_client(), resolved_domain, ip)


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

    try:
        ip, ssh_user = _resolve_ip(step, host, name, get_client)

        if hub:
            _make_hub(step, name, ip)

        resolved_domain = _resolve_domain(step, get_client, domain)

        _run_launch_and_dns(
            step, ip, ssh_user, resolved_domain, environment, name, dns, get_client
        )
    finally:
        if _client is not None:
            _client.close()

    step("Deploying...")
    project_root = LocalConfigService.resolve_root()
    run_deploy_or_exit(
        project_root,
        name,
        environment,
        tags=None,
        skip_tags=None,
        overrides=DeployOverrides(),
    )

    sync_wg_manage_after_deploy(project_root, name)

    output.success("slipp up complete")
