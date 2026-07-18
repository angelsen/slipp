"""Provider configuration models (~/.config/slipp/providers.yaml).

This module defines the on-disk shape of configured infrastructure
providers (API keys, cached account info). Kept separate from
services/providers/dns.py, which holds the DNS-specific Protocol and
wire models shared across provider implementations.
"""

from pydantic import BaseModel, Field

from slipp.models.types import PathStr


class GigahostConfig(BaseModel):
    """Gigahost provider configuration.

    Attributes:
        api_key: Personal API key, format flux_live_<64 hex chars>
        account_name: Cached account display name (from GET /account)
    """

    api_key: str = Field(..., min_length=1, description="flux_live_* API key")
    account_name: str | None = None


class PangolinConfig(BaseModel):
    """Pangolin provider configuration.

    Attributes:
        session_cookie: Value of the p_session_token dashboard session
            cookie. Stopgap until Pangolin's Integration API (Bearer-token
            auth) is reachable -- see services/providers/pangolin.py.
        org: Pangolin org slug. No default -- there's no universal
            Pangolin instance, this is always the caller's own.
        base_url: Pangolin REST API base URL for the caller's own
            instance. No default, same reasoning as org.
    """

    session_cookie: str = Field(..., min_length=1, description="p_session_token value")
    org: str = Field(..., min_length=1, description="Pangolin org slug")
    base_url: str = Field(
        ...,
        min_length=1,
        description="Pangolin API base URL, e.g. https://pangolin.example.com/api/v1",
    )


class WgDeployConfig(BaseModel):
    """wg-deploy provider configuration.

    Attributes:
        repo_path: Path to a wg-deploy checkout, used to shell out to
            scripts/new-host.sh for hub-ification (`slipp up --hub`).
    """

    repo_path: PathStr


class ProvidersConfig(BaseModel):
    """Root config for ~/.config/slipp/providers.yaml.

    Attributes:
        gigahost: Gigahost provider config, if configured
        pangolin: Pangolin provider config, if configured
        wg_deploy: wg-deploy provider config, if configured
    """

    gigahost: GigahostConfig | None = None
    pangolin: PangolinConfig | None = None
    wg_deploy: WgDeployConfig | None = None
