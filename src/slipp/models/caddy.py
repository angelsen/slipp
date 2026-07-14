"""Caddy reverse proxy configuration models with Pydantic v2 validation."""

from pydantic import BaseModel, Field


class CaddySite(BaseModel):
    """Caddy site configuration for a service.

    Represents a single reverse proxy configuration.

    Attributes:
        domain: Domain or subdomain
        upstream_port: Backend port
        path_prefix: Path routing (default: /)
    """

    domain: str = Field(description="Domain or subdomain")
    upstream_port: int = Field(description="Backend port")
    path_prefix: str = Field(default="/", description="Path routing")


class CaddyConfig(BaseModel):
    """Caddy role configuration.

    Configuration for Caddy reverse proxy setup.

    Attributes:
        sites: List of site configurations
        auto_https: Enable automatic HTTPS (default: True)
        sites_dir: Site configs directory (default: /etc/caddy/sites)
    """

    sites: list[CaddySite] = Field(default_factory=list)
    auto_https: bool = Field(default=True, description="Enable automatic HTTPS")
    sites_dir: str = Field(
        default="/etc/caddy/sites", description="Site configs directory"
    )
