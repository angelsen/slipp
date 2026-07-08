"""Provider configuration models (~/.config/slipp/providers.yaml).

This module defines the on-disk shape of configured infrastructure
providers (API keys, cached account info). Kept separate from
services/providers/dns.py, which holds the DNS-specific Protocol and
wire models shared across provider implementations.
"""

from pydantic import BaseModel, Field


class GigahostConfig(BaseModel):
    """Gigahost provider configuration.

    Attributes:
        api_key: Personal API key, format flux_live_<64 hex chars>
        account_name: Cached account display name (from GET /account)
        account_id: Cached customer ID (from GET /account)
    """

    api_key: str = Field(..., min_length=1, description="flux_live_* API key")
    account_name: str | None = None
    account_id: int | None = None


class ProvidersConfig(BaseModel):
    """Root config for ~/.config/slipp/providers.yaml.

    Attributes:
        gigahost: Gigahost provider config, if configured
    """

    gigahost: GigahostConfig | None = None
