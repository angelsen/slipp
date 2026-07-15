"""Provider management commands - slipp providers add/list/remove."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from slipp import output
from slipp.constants import Provider
from slipp.models.provider import GigahostConfig, PangolinConfig, WgDeployConfig
from slipp.services.providers import ProviderConfigService
from slipp.services.providers.gigahost import GigahostClient
from slipp.services.providers.pangolin import PangolinClient
from slipp.services.providers.wg_deploy import verify_repo as verify_wg_deploy_repo
from slipp.utils.errors import ProviderError

providers_app = typer.Typer(
    name="providers",
    help="Manage infrastructure providers",
)


@providers_app.command(name="add")
def add_provider(
    name: Annotated[Provider, typer.Argument(help="Provider name")],
) -> None:
    """Configure and verify an infrastructure provider."""
    _PROVIDER_ADDERS[name]()


def _fail_verification(error: ProviderError) -> NoReturn:
    """Report a provider verification failure and exit."""
    output.error(f"Verification failed: {error}")
    raise typer.Exit(1)


def _add_gigahost() -> None:
    """Prompt for, verify, and save a Gigahost API key."""
    api_key = output.prompt_password("Gigahost API key (flux_live_...)")

    with GigahostClient(api_key) as client:
        try:
            account = client.get_account()
        except ProviderError as e:
            _fail_verification(e)

        account_name = account.get("cust_name")

        ProviderConfigService.set_gigahost(
            GigahostConfig(api_key=api_key, account_name=account_name)
        )

        output.success(f"Gigahost configured for account: {account_name}")

        try:
            servers = client.list_servers()
            zones = client.list_zones()
            output.kv("servers", len(servers), indent=1)
            output.kv("domains", len(zones), indent=1)
        except ProviderError:
            # Account verified fine; a secondary listing call failing shouldn't
            # undo the successful "add".
            pass


def _add_pangolin() -> None:
    """Prompt for, verify, and save a Pangolin session cookie.

    Stopgap auth until Pangolin's Integration API is reachable -- see
    services/providers/pangolin.py.
    """
    cookie = output.prompt_password("Pangolin session cookie (p_session_token value)")

    # Build the config first so org/base_url come from PangolinConfig's own
    # field defaults (the single source of truth), not a second hardcoded
    # copy in the client.
    config = PangolinConfig(session_cookie=cookie)
    with PangolinClient(cookie, org=config.org, base_url=config.base_url) as client:
        try:
            sites = client.list_sites()
        except ProviderError as e:
            _fail_verification(e)

    ProviderConfigService.set_pangolin(config)

    output.success("Pangolin configured")
    output.kv("sites", len(sites), indent=1)


def _add_wg_deploy() -> None:
    """Prompt for, verify, and save a wg-deploy repo path.

    Verification is a shape check (playbook.yml + scripts/new-host.sh
    present) -- there's no API to call, wg-deploy is a local checkout that
    `slipp up --hub` shells out to.
    """
    raw_path = output.prompt("wg-deploy repo path")
    repo_path = Path(raw_path).expanduser().resolve()

    try:
        verify_wg_deploy_repo(repo_path)
    except ProviderError as e:
        output.error(str(e))
        output.hint("Expected playbook.yml and scripts/new-host.sh in this directory")
        raise typer.Exit(1)

    ProviderConfigService.set_wg_deploy(WgDeployConfig(repo_path=repo_path))

    output.success(f"wg-deploy configured: {repo_path}")


_PROVIDER_ADDERS: dict[Provider, Callable[[], None]] = {
    Provider.gigahost: _add_gigahost,
    Provider.pangolin: _add_pangolin,
    Provider.wg_deploy: _add_wg_deploy,
}


@providers_app.command(name="list")
def list_providers() -> None:
    """List configured infrastructure providers."""
    config = ProviderConfigService.load()

    rows = []
    if config.gigahost:
        rows.append(
            {"provider": "gigahost", "account": config.gigahost.account_name or "-"}
        )
    if config.pangolin:
        rows.append({"provider": "pangolin", "account": config.pangolin.org})
    if config.wg_deploy:
        rows.append(
            {"provider": "wg-deploy", "account": str(config.wg_deploy.repo_path)}
        )

    output.empty_or_table(
        rows,
        "No providers configured",
        hint_msg="Add one with: slipp providers add gigahost",
    )


_PROVIDER_CONFIG_ATTR: dict[Provider, str] = {
    Provider.gigahost: "gigahost",
    Provider.pangolin: "pangolin",
    Provider.wg_deploy: "wg_deploy",
}

_PROVIDER_REMOVERS: dict[Provider, Callable[[], None]] = {
    Provider.gigahost: ProviderConfigService.remove_gigahost,
    Provider.pangolin: ProviderConfigService.remove_pangolin,
    Provider.wg_deploy: ProviderConfigService.remove_wg_deploy,
}


@providers_app.command(name="remove")
def remove_provider(
    name: Annotated[Provider, typer.Argument(help="Provider name to remove")],
) -> None:
    """Remove a configured provider."""
    config = ProviderConfigService.load()

    if not getattr(config, _PROVIDER_CONFIG_ATTR[name]):
        output.warning(f"{name} is not configured")
        return

    _PROVIDER_REMOVERS[name]()
    output.success(f"Removed {name} provider")
