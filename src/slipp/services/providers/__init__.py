"""Provider resolution helpers.

Single entry point for getting an authenticated Gigahost client, and for
resolving which configured provider manages a given domain's DNS zone.
"""

from slipp.services.providers.config import ProviderConfigService
from slipp.services.providers.dns import DNSProvider, DNSRecord, DNSZone, sync_dns
from slipp.services.providers.domains import register_domain_interactive
from slipp.services.providers.gigahost import GigahostClient
from slipp.services.providers.provision import provision_and_bootstrap, provision_server
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
    "ProviderConfigService",
    "get_gigahost_client",
    "provision_and_bootstrap",
    "provision_server",
    "register_domain_interactive",
    "resolve_dns_provider",
    "sync_dns",
]
