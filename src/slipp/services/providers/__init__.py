"""Provider resolution helpers.

Single entry point for getting authenticated provider clients.
"""

from slipp.services.providers.config import ProviderConfigService
from slipp.services.providers.dns import DNSProvider, sync_dns
from slipp.services.providers.domains import (
    ensure_domain_registered,
    register_domain_interactive,
)
from slipp.services.providers.gigahost import GigahostClient
from slipp.services.providers.pangolin import PangolinClient
from slipp.services.providers.provision import (
    install_server,
    provision_and_bootstrap,
    resolve_server,
)
from slipp.utils.errors import ProviderNotConfiguredError


def get_gigahost_client() -> GigahostClient:
    """Get an authenticated Gigahost client.

    Raises:
        ProviderNotConfiguredError: If no Gigahost API key is configured.
    """
    config = ProviderConfigService.get_gigahost()
    if not config:
        raise ProviderNotConfiguredError(
            "Gigahost not configured. Run: slipp providers add gigahost"
        )
    return GigahostClient(config.api_key)


def get_pangolin_client() -> PangolinClient:
    """Get an authenticated Pangolin client.

    Raises:
        ProviderNotConfiguredError: If no Pangolin session cookie is configured.
    """
    config = ProviderConfigService.get_pangolin()
    if not config:
        raise ProviderNotConfiguredError(
            "Pangolin not configured. Run: slipp providers add pangolin"
        )
    return PangolinClient(
        config.session_cookie, org=config.org, base_url=config.base_url
    )


__all__ = [
    "DNSProvider",
    "GigahostClient",
    "PangolinClient",
    "ProviderConfigService",
    "get_gigahost_client",
    "get_pangolin_client",
    "provision_and_bootstrap",
    "install_server",
    "resolve_server",
    "ensure_domain_registered",
    "register_domain_interactive",
    "sync_dns",
]
