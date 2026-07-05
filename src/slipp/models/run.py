"""Run profile models for dev environment orchestration.

This module provides Pydantic models for run profiles stored in
slipp.yaml under `runs:`.
"""

from pydantic import BaseModel, Field


class ProxyRoute(BaseModel):
    """Proxy route for path-based Caddy routing.

    Attributes:
        from_: Source domain/path (e.g., 'matrix.example.com/api')
        to: Target localhost:port/path (e.g., 'localhost:5173/api')
        host: Remote host to configure
    """

    from_: str = Field(..., alias="from", description="Source domain/path")
    to: str = Field(..., description="Target localhost:port/path")
    host: str = Field(..., description="Remote host to configure")

    model_config = {"populate_by_name": True}

    @property
    def from_domain(self) -> str:
        """Return the domain from the 'from' field."""
        return self.from_.split("/", 1)[0]

    @property
    def from_path(self) -> str:
        """Return the path from the 'from' field."""
        parts = self.from_.split("/", 1)
        return "/" + parts[1] if len(parts) > 1 else "/"

    @property
    def to_host(self) -> str:
        """Return the host:port from the 'to' field."""
        return self.to.split("/", 1)[0]

    @property
    def to_path(self) -> str:
        """Return the path from the 'to' field."""
        parts = self.to.split("/", 1)
        return "/" + parts[1] if len(parts) > 1 else "/"


class TunnelConfig(BaseModel):
    """SSH tunnel configuration.

    Attributes:
        out: Reverse tunnels (expose local to remote) - format: local_port:domain@host
        in_: Forward tunnels (pull remote to local) - format: service:port@host
        auth: HTTP basic auth for tunnel-out Caddy routes - format: user:<bcrypt-hash>
    """

    out: list[str] = Field(default_factory=list)
    in_: list[str] = Field(default_factory=list, alias="in")
    auth: str | None = Field(
        default=None, description="HTTP basic auth as user:<bcrypt-hash>"
    )

    model_config = {"populate_by_name": True}


class RunProfile(BaseModel):
    """Single run profile configuration.

    Attributes:
        cmd: Command to execute
        vaults: List of vault project names to inject as env vars
        env: Environment variables as KEY=VALUE strings
        tunnels: SSH tunnel configuration
        proxy: Proxy route configurations
        acme_email: Email for Let's Encrypt certificate registration
    """

    cmd: str = Field(..., description="Command to execute")
    vaults: list[str] = Field(default_factory=list)
    env: list[str] = Field(
        default_factory=list, description="Environment variables (KEY=VALUE)"
    )
    tunnels: TunnelConfig | None = None
    proxy: list[ProxyRoute] = Field(default_factory=list)
    acme_email: str | None = Field(
        default=None, description="Email for ACME/Let's Encrypt"
    )
