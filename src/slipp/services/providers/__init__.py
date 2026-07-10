"""Provider resolution helpers.

Single entry point for getting an authenticated Gigahost client, and for
resolving which configured provider manages a given domain's DNS zone.
"""

from slipp.services.providers.config import ProviderConfigService
from slipp.services.providers.dns import DNSProvider, DNSRecord, DNSZone, sync_dns
from slipp.services.providers.domains import register_domain_interactive
from slipp.services.providers.gigahost import GigahostClient
from slipp.services.providers.pangolin import PangolinClient
from slipp.services.providers.provision import (
    install_server,
    provision_and_bootstrap,
    provision_server,
    resolve_server,
)
from slipp.services.providers.state import ProvisionStateService
from slipp.utils.errors import DNSSyncError, ProviderNotConfiguredError


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
    return PangolinClient(config.session_cookie, org=config.org, base_url=config.base_url)


def resolve_dns_provider(domain: str) -> DNSProvider:
    """Find which configured provider manages this domain's zone.

    Raises:
        ProviderNotConfiguredError: If no provider is configured at all.
        DNSSyncError: If no configured provider manages this domain's zone.
    """
    client = get_gigahost_client()
    if client.find_zone(domain) is not None:
        return client

    raise DNSSyncError(f"No configured provider manages a zone for: {domain}")


__all__ = [
    "DNSProvider",
    "DNSRecord",
    "DNSZone",
    "GigahostClient",
    "PangolinClient",
    "ProviderConfigService",
    "get_gigahost_client",
    "get_pangolin_client",
    "provision_and_bootstrap",
    "provision_server",
    "install_server",
    "resolve_server",
    "ProvisionStateService",
    "register_domain_interactive",
    "resolve_dns_provider",
    "sync_dns",
]
