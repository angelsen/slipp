"""Provider management commands - slipp providers add/list/remove."""

from typing import Annotated

import typer

from slipp import output
from slipp.models.provider import GigahostConfig, PangolinConfig
from slipp.services.providers import ProviderConfigService
from slipp.services.providers.gigahost import GigahostClient
from slipp.services.providers.pangolin import PangolinClient
from slipp.utils.errors import ProviderError

providers_app = typer.Typer(
    name="providers",
    help="Manage infrastructure providers",
)

SUPPORTED_PROVIDERS = ["gigahost", "pangolin"]


@providers_app.command(name="add")
def add_provider(
    name: Annotated[
        str, typer.Argument(help="Provider name (gigahost, pangolin)")
    ],
) -> None:
    """Configure and verify an infrastructure provider."""
    if name not in SUPPORTED_PROVIDERS:
        output.error(f"Unknown provider '{name}'")
        output.hint(f"Supported providers: {', '.join(SUPPORTED_PROVIDERS)}")
        raise typer.Exit(1)

    if name == "pangolin":
        _add_pangolin()
        return

    api_key = output.prompt_password("Gigahost API key (flux_live_...)")

    client = GigahostClient(api_key)
    try:
        account = client.get_account()
    except ProviderError as e:
        output.error(f"Verification failed: {e}")
        raise typer.Exit(1)

    account_name = account.get("cust_name")
    account_id = account.get("cust_id")

    ProviderConfigService.set_gigahost(
        GigahostConfig(
            api_key=api_key, account_name=account_name, account_id=account_id
        )
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
    client = PangolinClient(cookie, org=config.org, base_url=config.base_url)
    try:
        sites = client.list_sites()
    except ProviderError as e:
        output.error(f"Verification failed: {e}")
        raise typer.Exit(1)

    ProviderConfigService.set_pangolin(config)

    output.success("Pangolin configured")
    output.kv("sites", len(sites), indent=1)


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

    if not rows:
        output.info("No providers configured")
        output.hint("Add one with: slipp providers add gigahost")
        return

    output.table(rows)


@providers_app.command(name="remove")
def remove_provider(
    name: Annotated[str, typer.Argument(help="Provider name to remove")],
) -> None:
    """Remove a configured provider."""
    if name not in SUPPORTED_PROVIDERS:
        output.error(f"Unknown provider '{name}'")
        raise typer.Exit(1)

    config = ProviderConfigService.load()

    if name == "pangolin":
        if not config.pangolin:
            output.warning("Pangolin is not configured")
            return
        ProviderConfigService.remove_pangolin()
        output.success("Removed pangolin provider")
        return

    if not config.gigahost:
        output.warning("Gigahost is not configured")
        return

    ProviderConfigService.remove_gigahost()
    output.success("Removed gigahost provider")
